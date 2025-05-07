import argparse
import asyncio
import logging
import signal
import socket
import json
import os.path

import aiofiles.tempfile
import aiohttp
import faster_whisper
import m3u8
import os
import sys
import shutil
import copy
import threading

from datetime import timedelta, datetime
from typing import Iterable, Tuple
from faster_whisper import WhisperModel
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from faster_whisper.utils import available_models
from m3u8 import PlaylistList, SegmentList

translated_chunk_paths = {}
chunk_to_vtt = {}
chunk_to_vtt_trans = {}  # New dictionary for translated subtitles
chunk_to_vtt_orig = {}   # New dictionary for transcribed subtitles

CHUNK_LIST_BASE_URI = None
BASE_PLAYLIST_SER = None
CHUNK_LIST_SER = None
SUB_LIST_SER = None
SUB_LIST_TRANS_SER = None  # New global for translated subtitles playlist
SUB_LIST_ORIG_SER = None   # New global for transcribed subtitles playlist

TARGET_BUFFER_SECS = 60
MAX_TARGET_BUFFER_SECS = 120

FILTER_DICT = {}  # Dictionary of strings to filter out
FILTER_FILE = 'filter.json'  # File to store filter words

if sys.version_info < (3, 10):
    print(f'This script needs to be ran under Python 3.10 at minimum.')
    sys.exit(1)

logger = logging.getLogger('livevtt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
                    handlers=[logging.StreamHandler()])


def segments_to_srt(segments: Iterable[faster_whisper.transcribe.Segment], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S,%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S,%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)]
    return '\n\n'.join(segment_chunks)


def segments_to_webvtt(segments: Iterable[faster_whisper.transcribe.Segment], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S.%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S.%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)]
    return 'WEBVTT\n\n' + '\n\n'.join(segment_chunks)


class HTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        response_content = None
        if self.path == '/playlist.m3u8':
            response_content = BASE_PLAYLIST_SER
        elif self.path == '/chunklist.m3u8':
            response_content = CHUNK_LIST_SER
        elif self.path == '/subs.m3u8':
            response_content = SUB_LIST_SER
        elif self.path == '/subs.trans.m3u8':
            response_content = SUB_LIST_TRANS_SER
        elif self.path == '/subs.orig.m3u8':
            response_content = SUB_LIST_ORIG_SER
        elif self.path in translated_chunk_paths:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Content-Length', str(os.path.getsize(translated_chunk_paths[self.path])))
            self.end_headers()

            with open(translated_chunk_paths[self.path], 'rb') as f:
                shutil.copyfileobj(f, self.wfile)

            return
        elif self.path in chunk_to_vtt or self.path in chunk_to_vtt_trans or self.path in chunk_to_vtt_orig:
            vtt_content = chunk_to_vtt.get(self.path) or chunk_to_vtt_trans.get(self.path) or chunk_to_vtt_orig.get(self.path)
            response_content = bytes(vtt_content, 'utf-8')

        self.send_response(200 if response_content else 404)

        if self.path.endswith('.m3u8'):
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        elif self.path.endswith('.vtt'):
            self.send_header('Content-Type', 'text/vtt')

        if response_content:
            self.send_header('Content-Length', str(len(response_content)))

        self.end_headers()
        if response_content:
            self.wfile.write(response_content)


def http_listener(server_address: Tuple[str, int], stop_event: threading.Event):
    logger.info(f'Web server now listening on {server_address}...')
    server = ThreadingHTTPServer(server_address, HTTPHandler)
    server.timeout = 1  # Set timeout to allow checking stop_event
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()
    logger.info("HTTP server stopped")


def normalise_chunk_uri(chunk_uri: str) -> str:
    chunk_uri = os.path.splitext(chunk_uri)[0] + '.ts'
    chunk_uri = chunk_uri.replace('../', '').replace('./', '')
    return '/' + chunk_uri


def check_bindeps_present():
    required_binaries = ('ffmpeg', 'ffprobe')
    for required_binary in required_binaries:
        if not shutil.which(required_binary):
            logger.error(
                f"{required_binary} binary not found. Check your platform PATH and ensure that you've installed the required packages.")
            sys.exit(1)


async def download_chunk(session: aiohttp.ClientSession, base_uri: str, segment: m3u8.Segment, chunk_dir: str):
    chunk_url = os.path.join(base_uri, segment.uri)
    chunk_uri = normalise_chunk_uri(segment.uri)
    if chunk_uri not in translated_chunk_paths:
        logger.info(f'Downloading segment {chunk_uri}...')
        try:
            async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.ts') as chunk_fp:
                async with session.get(chunk_url, raise_for_status=True) as response:
                    async for chunk in response.content.iter_chunked(16384):
                        await chunk_fp.write(chunk)

                    await chunk_fp.close()
        except aiohttp.ClientError as e:
            logger.error(f'Failed to download chunk {chunk_uri}, stream may skip...', exc_info=e)
            raise e
        else:
            logger.info(f'Downloaded segment {chunk_uri}')

    return chunk_fp.name


def load_filter_dict():
    global FILTER_DICT
    try:
        if os.path.exists(FILTER_FILE):
            with open(FILTER_FILE, 'r', encoding='utf-8') as f:
                FILTER_DICT = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load filter dictionary: {e}")


def should_filter_segment(text: str) -> bool:
    """Return True if segment should be filtered out based on content."""
    if not FILTER_DICT:
        return False
    text = text.lower()
    return any(word.lower() in text for word in FILTER_DICT.get('filter_words', []))


async def transcribe_chunk(args: argparse.Namespace, model: WhisperModel, chunk_dir: str, segment_uri: str,
                           chunk_name: str) -> Tuple[str, str]:
    ts_probe_proc = await asyncio.create_subprocess_exec('ffprobe', '-i', chunk_name, '-show_entries',
                                                         'stream=start_time', '-loglevel', 'quiet',
                                                         '-select_streams', 'a:0', '-of',
                                                         'csv=p=0', stdout=asyncio.subprocess.PIPE)
    ts_probe_stdout, _ = await ts_probe_proc.communicate()
    start_ts = timedelta(seconds=float(ts_probe_stdout.splitlines()[0]))

    loop = asyncio.get_running_loop()
    
    # Run transcription and translation in parallel if both_tracks is enabled
    if args.both_tracks:
        # Transcribe in source language
        segments_orig, _ = await loop.run_in_executor(None,
                                                     lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                           vad_filter=args.vad_filter,
                                                                           language=args.language,
                                                                           task='transcribe'))
        # Translate to English
        segments_trans, _ = await loop.run_in_executor(None,
                                                      lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                            vad_filter=args.vad_filter,
                                                                            language=args.language,
                                                                            task='translate'))
        
        # Filter segments
        segments_orig = [seg for seg in segments_orig if not should_filter_segment(seg.text)]
        segments_trans = [seg for seg in segments_trans if not should_filter_segment(seg.text)]
        
        if not args.hard_subs:
            vtt_uri = os.path.splitext(segment_uri)[0]
            if segments_orig:  # Only add if there are segments after filtering
                chunk_to_vtt_orig[vtt_uri + '.orig.vtt'] = segments_to_webvtt(segments_orig, start_ts)
            if segments_trans:  # Only add if there are segments after filtering
                chunk_to_vtt_trans[vtt_uri + '.trans.vtt'] = segments_to_webvtt(segments_trans, start_ts)
            return segment_uri, chunk_name
    else:
        # Original behavior with filtering
        segments, _ = await loop.run_in_executor(None,
                                             lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                      vad_filter=args.vad_filter,
                                                                      language=args.language,
                                                                      task='transcribe' if args.transcribe else 'translate'))
        
        # Filter segments
        segments = [seg for seg in segments if not should_filter_segment(seg.text)]
        
        if not args.hard_subs:
            vtt_uri = os.path.splitext(segment_uri)[0] + '.vtt'
            if segments:  # Only add if there are segments after filtering
                chunk_to_vtt[vtt_uri] = segments_to_webvtt(segments, start_ts)
            return segment_uri, chunk_name

    if args.hard_subs:
        # Original hard subs logic with filtering
        async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.srt') as srt_file:
            segments_to_use = segments if not args.both_tracks else segments_trans
            segments_to_use = [seg for seg in segments_to_use if not should_filter_segment(seg.text)]
            
            srt_content = segments_to_srt(segments_to_use, start_ts)
            if not srt_content:
                return segment_uri, chunk_name

            await srt_file.write(bytes(srt_content, 'utf-8'))
            await srt_file.close()
            chunk_fp_name_split = os.path.splitext(chunk_name)
            translated_chunk_name = chunk_fp_name_split[0] + '_trans' + chunk_fp_name_split[1]

            ffmpeg_sub_proc = await asyncio.create_subprocess_exec('ffmpeg', '-hwaccel', 'auto', '-i', chunk_name,
                                                                   '-copyts',
                                                                   '-muxpreload', '0', '-muxdelay', '0', '-preset',
                                                                   'ultrafast', '-c:a',
                                                                   'copy',
                                                                   '-loglevel', 'quiet', '-vf',
                                                                   f'subtitles={os.path.basename(srt_file.name)}',
                                                                   translated_chunk_name)
            await ffmpeg_sub_proc.communicate()

            os.unlink(chunk_name)
            return segment_uri, translated_chunk_name

    return segment_uri, chunk_name


async def cleanup(session: aiohttp.ClientSession, chunk_dir: str, prev_cwd: str, stop_event: threading.Event):
    logger.info("Cleaning up resources...")
    await session.close()
    os.chdir(prev_cwd)
    try:
        # Clean up any remaining temporary files
        for chunk_path in list(translated_chunk_paths.values()):
            try:
                if os.path.exists(chunk_path):
                    os.unlink(chunk_path)
            except OSError as e:
                logger.warning(f"Failed to remove temporary file {chunk_path}: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        stop_event.set()


def get_local_ip():
    try:
        # Get the local IP by creating a temporary socket connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # Doesn't actually send any data
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


async def main():
    check_bindeps_present()
    load_filter_dict()  # Load filter dictionary at startup
    
    parser = argparse.ArgumentParser(prog='livevtt')
    parser.add_argument('-u', '--url', default='https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8',
                        help='URL of the HLS stream (defaults to TVRain stream)')
    parser.add_argument('-s', '--hard-subs', action='store_true',
                        help='Set if you want the subtitles to be baked into the stream itself')
    parser.add_argument('-l', '--bind-address', type=str, help='The IP address to bind to '
                                                               '(defaults to 127.0.0.1)', default='127.0.0.1')
    parser.add_argument('-p', '--bind-port', type=int, help='The port to bind to (defaults to 8000)',
                        default=8000)
    parser.add_argument('-pl', '--public-address', type=str, help='The public IP address to use in URLs '
                                                               '(defaults to bind-address)',
                        default=None)
    parser.add_argument('-m', '--model', type=str, help='Whisper model to use (defaults to large)',
                        default='large', choices=available_models())
    parser.add_argument('-b', '--beam-size', type=int, help='Beam size to use (defaults to 5)', default=5)
    parser.add_argument('-c', '--use-cuda', type=lambda x: str(x).lower() in ['true', '1', 'yes'],
                        help='Use CUDA where available. Defaults to true', default=True)
    parser.add_argument('-t', '--transcribe', action='store_true',
                        help='If set, transcribes rather than translates the given stream.')
    parser.add_argument('-vf', '--vad-filter', type=lambda x: str(x).lower() in ['true', '1', 'yes'],
                        help='Whether to utilise the Silero VAD model to try and filter out silences. Defaults to false.',
                        default=False)
    parser.add_argument('-la', '--language', type=str, help='The original language of the stream, '
                                                            'if known/not multi-lingual. Can be left unset.')
    parser.add_argument('-ua', '--user-agent', type=str, help='User agent to use to retrieve playlists / '
                                                              'stream chunks.', default='VLC/3.0.18 LibVLC/3.0.18')
    parser.add_argument('-bt', '--both-tracks', action='store_true',
                        help='Enable both transcription and translation tracks')
    parser.add_argument('-f', '--filter-file', type=str, help='Path to JSON file containing words to filter out',
                        default='filter.json')

    args = parser.parse_args()

    stop_event = threading.Event()
    session = aiohttp.ClientSession(headers={'User-Agent': args.user_agent})
    loop = asyncio.get_running_loop()
    
    device = 'cuda' if args.use_cuda else 'cpu'
    compute_type = 'auto'

    logger.info(f'Using {device} as the device type for the model')

    model = WhisperModel(args.model, device=device, compute_type=compute_type)

    base_playlist = m3u8.load(args.url)
    highest_bitrate_stream = sorted(base_playlist.playlists, key=lambda x: x.stream_info.bandwidth, reverse=True)[0]
    base_playlist.playlists = PlaylistList([highest_bitrate_stream])

    # Use actual IP if binding to all interfaces
    public_address = get_local_ip() if args.bind_address == '0.0.0.0' else args.bind_address
    http_base_url = '' # Changed from absolute to relative path

    modified_base_playlist = copy.deepcopy(base_playlist)
    modified_base_playlist.playlists[0].uri = 'chunklist.m3u8' # Removed path join

    if not args.hard_subs:
        if args.both_tracks:
            # Add both subtitle tracks
            subtitle_trans = m3u8.Media(uri='subs.trans.m3u8', # Removed path join
                                      type='SUBTITLES', group_id='Subtitle',
                                      language='en', name='English',
                                      forced='NO', autoselect='NO')
            
            subtitle_orig = m3u8.Media(uri='subs.orig.m3u8', # Removed path join
                                     type='SUBTITLES', group_id='Subtitle',
                                     language=args.language or 'ru', 
                                     name={'en': 'English', 'ru': 'Russian'}.get(args.language or 'ru', 'Original'),
                                     forced='NO', autoselect='NO')
            
            modified_base_playlist.add_media(subtitle_trans)
            modified_base_playlist.add_media(subtitle_orig)
            modified_base_playlist.playlists[0].media += [subtitle_trans, subtitle_orig]
        else:
            # Original single subtitle track logic
            if not args.transcribe:
                subtitle_lang = 'en'
                subtitle_name = 'English'
            else:
                subtitle_lang = args.language or 'en'
            subtitle_name = {
                'en': 'English',
                'ru': 'Russian',
                'nl': 'Dutch',
            }.get(subtitle_lang.lower(), subtitle_lang.capitalize())

            subtitle_list = m3u8.Media(uri='subs.m3u8', # Removed path join
                                     type='SUBTITLES', group_id='Subtitle',
                                   language=subtitle_lang, name=subtitle_name,
                                   forced='NO', autoselect='NO')
            modified_base_playlist.add_media(subtitle_list)
            modified_base_playlist.playlists[0].media += [subtitle_list]

    global BASE_PLAYLIST_SER
    BASE_PLAYLIST_SER = bytes(modified_base_playlist.dumps(), 'ascii')

    # Set up signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(cleanup(session, chunk_dir, prev_cwd, stop_event)))

    http_thread = threading.Thread(target=http_listener, daemon=True, args=((args.bind_address, args.bind_port), stop_event))
    http_thread.start()

    async with aiofiles.tempfile.TemporaryDirectory() as chunk_dir:
        prev_cwd = os.getcwd()
        os.chdir(chunk_dir)

        try:
            while not stop_event.is_set():
                chunk_list = m3u8.load(base_playlist.playlists[0].absolute_uri)

                sleep_duration = chunk_list.target_duration or 10

                if chunk_list.target_duration:
                    if int(MAX_TARGET_BUFFER_SECS / chunk_list.target_duration) < len(chunk_list.segments):
                        chunk_list.segments = SegmentList(
                            chunk_list.segments[-int(TARGET_BUFFER_SECS / chunk_list.target_duration):])
                        chunk_list.media_sequence = chunk_list.segments[0].media_sequence

                        if chunk_list.program_date_time:
                            chunk_list.program_date_time = chunk_list.segments[0].current_program_date_time

                current_segments = [normalise_chunk_uri(segment.uri) for segment in chunk_list.segments]

                for translated_chunk_name, translated_chunk_path in dict(translated_chunk_paths).items():
                    if translated_chunk_name not in current_segments:
                        os.unlink(translated_chunk_path)
                        del translated_chunk_paths[translated_chunk_name]

                if not args.hard_subs:
                    for translated_uri, translated_chunk_path in dict(chunk_to_vtt).items():
                        if os.path.splitext(translated_uri)[0] + '.ts' not in current_segments:
                            del chunk_to_vtt[translated_uri]

                chunks_to_translate = {}

                for i, chunk_name in enumerate(
                        await asyncio.gather(*[download_chunk(session, chunk_list.base_uri, segment, chunk_dir)
                                               for segment in chunk_list.segments], return_exceptions=True)):
                    if isinstance(chunk_name, Exception):
                        continue

                    normalised_segment_uri = current_segments[i]
                    if normalised_segment_uri not in translated_chunk_paths:
                        chunks_to_translate[normalised_segment_uri] = chunk_name

                for segment_uri, chunk_name in await asyncio.gather(*[transcribe_chunk(args, model, chunk_dir,
                                                                                       segment_uri, chunk_name)
                                                                      for segment_uri, chunk_name in
                                                                      chunks_to_translate.items()]):
                    chunks_to_translate[segment_uri] = chunk_name

                for segment in chunk_list.segments:
                    segment_name = normalise_chunk_uri(segment.uri)
                    segment.uri = segment_name.lstrip('/') # Remove leading slash for relative path

                global CHUNK_LIST_SER
                CHUNK_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                if not args.hard_subs:
                    if args.both_tracks:
                        # Create two separate subtitle playlists
                        trans_chunk_list = copy.deepcopy(chunk_list)
                        orig_chunk_list = copy.deepcopy(chunk_list)
                        
                        for segment in trans_chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.trans.vtt'
                            segment.uri = subtitle_name
                            
                        for segment in orig_chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.orig.vtt'
                            segment.uri = subtitle_name

                        global SUB_LIST_TRANS_SER, SUB_LIST_ORIG_SER
                        SUB_LIST_TRANS_SER = bytes(trans_chunk_list.dumps(), 'ascii')
                        SUB_LIST_ORIG_SER = bytes(orig_chunk_list.dumps(), 'ascii')
                    else:
                        # Original single subtitle playlist logic
                        for segment in chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.vtt'
                            segment.uri = subtitle_name

                        global SUB_LIST_SER
                        SUB_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                translated_chunk_paths.update(chunks_to_translate)

                await asyncio.sleep(sleep_duration)
        except asyncio.CancelledError:
            logger.info("Received termination signal")
        finally:
            await cleanup(session, chunk_dir, prev_cwd, stop_event)
            http_thread.join(timeout=5)  # Wait for HTTP server to stop

    # Update filter file path if provided
    global FILTER_FILE
    FILTER_FILE = args.filter_file
    load_filter_dict()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
