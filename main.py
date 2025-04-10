import argparse
import asyncio
import logging

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

CHUNK_LIST_BASE_URI = None
BASE_PLAYLIST_SER = None
CHUNK_LIST_SER = None
SUB_LIST_SER = None

TARGET_BUFFER_SECS = 60
MAX_TARGET_BUFFER_SECS = 120

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
        elif self.path in translated_chunk_paths:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Content-Length', str(os.path.getsize(translated_chunk_paths[self.path])))
            self.end_headers()

            with open(translated_chunk_paths[self.path], 'rb') as f:
                shutil.copyfileobj(f, self.wfile)

            return
        elif self.path in chunk_to_vtt:
            response_content = bytes(chunk_to_vtt[self.path], 'utf-8')

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


def http_listener(server_address: Tuple[str, int]):
    logger.info(f'Web server now listening on {server_address}...')
    server = ThreadingHTTPServer(server_address, HTTPHandler)
    server.serve_forever()


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


async def transcribe_chunk(args: argparse.Namespace, model: WhisperModel, chunk_dir: str, segment_uri: str,
                           chunk_name: str) -> Tuple[str, str]:
    ts_probe_proc = await asyncio.create_subprocess_exec('ffprobe', '-i', chunk_name, '-show_entries',
                                                         'stream=start_time', '-loglevel', 'quiet',
                                                         '-select_streams', 'a:0', '-of',
                                                         'csv=p=0', stdout=asyncio.subprocess.PIPE)
    ts_probe_stdout, _ = await ts_probe_proc.communicate()
    start_ts = timedelta(seconds=float(ts_probe_stdout.splitlines()[0]))

    loop = asyncio.get_running_loop()
    segments, _ = await loop.run_in_executor(None,
                                             lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                      vad_filter=args.vad_filter,
                                                                      language=args.language,
                                                                      task='transcribe' if args.transcribe else 'translate'))

    if args.hard_subs:
        async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.srt') as srt_file:
            srt_content = segments_to_srt(segments, start_ts)
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
    else:
        vtt_uri = os.path.splitext(segment_uri)[0] + '.vtt'
        chunk_to_vtt[vtt_uri] = segments_to_webvtt(segments, start_ts)
        return segment_uri, chunk_name


async def main():
    check_bindeps_present()

    parser = argparse.ArgumentParser(prog='livevtt')
    parser.add_argument('-u', '--url', default='https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8',
                        help='URL of the HLS stream (defaults to TVRain stream)')
    parser.add_argument('-s', '--hard-subs', action='store_true',
                        help='Set if you want the subtitles to be baked into the stream itself')
    parser.add_argument('-l', '--bind-address', type=str, help='The IP address to bind to '
                                                               '(defaults to 127.0.0.1)', default='127.0.0.1')
    parser.add_argument('-p', '--bind-port', type=int, help='The port to bind to (defaults to 8000)',
                        default=8000)
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

    args = parser.parse_args()

    threading.Thread(target=http_listener, daemon=True, args=((args.bind_address, args.bind_port),)).start()

    device = 'cuda' if args.use_cuda else 'cpu'
    compute_type = 'auto'

    logger.info(f'Using {device} as the device type for the model')

    model = WhisperModel(args.model, device=device, compute_type=compute_type)

    base_playlist = m3u8.load(args.url)
    highest_bitrate_stream = sorted(base_playlist.playlists, key=lambda x: x.stream_info.bandwidth, reverse=True)[0]
    base_playlist.playlists = PlaylistList([highest_bitrate_stream])

    http_base_url = f'http://{args.bind_address}:{args.bind_port}/'

    modified_base_playlist = copy.deepcopy(base_playlist)
    modified_base_playlist.playlists[0].uri = os.path.join(http_base_url, 'chunklist.m3u8')

    if not args.hard_subs:
        # Use the language argument for the subtitle track label, default to English if not specified
        subtitle_lang = args.language or 'en'
        subtitle_name = {
            'en': 'English',
            'ru': 'Russian',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish',
            'it': 'Italian',
            'pt': 'Portuguese',
            'nl': 'Dutch',
            'ja': 'Japanese',
            'zh': 'Chinese',
            'ko': 'Korean',
        }.get(subtitle_lang.lower(), subtitle_lang.capitalize())
        
        subtitle_list = m3u8.Media(uri=os.path.join(http_base_url, 'subs.m3u8'), type='SUBTITLES', group_id='Subtitle',
                                   language=subtitle_lang, name=subtitle_name,
                                   forced='NO', autoselect='NO')
        modified_base_playlist.add_media(subtitle_list)
        modified_base_playlist.playlists[0].media += [subtitle_list]

    global BASE_PLAYLIST_SER
    BASE_PLAYLIST_SER = bytes(modified_base_playlist.dumps(), 'ascii')

    session = aiohttp.ClientSession(headers={'User-Agent': args.user_agent})

    async with aiofiles.tempfile.TemporaryDirectory() as chunk_dir:
        prev_cwd = os.getcwd()
        os.chdir(chunk_dir)

        try:
            while True:
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
                    segment.uri = os.path.join(http_base_url, segment_name)

                global CHUNK_LIST_SER
                CHUNK_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                if not args.hard_subs:
                    for segment in chunk_list.segments:
                        subtitle_name = os.path.splitext(segment.uri)[0] + '.vtt'
                        segment.uri = subtitle_name

                    global SUB_LIST_SER
                    SUB_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                translated_chunk_paths.update(chunks_to_translate)

                await asyncio.sleep(sleep_duration)
        finally:
            os.chdir(prev_cwd)


if __name__ == '__main__':
    asyncio.run(main())
