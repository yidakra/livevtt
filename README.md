# LiveVTT

LiveVTT is a tool for live transcription of streaming audio/video content, providing real-time subtitles in WebVTT format.

## Description

LiveVTT allows you to transcribe live audio/video streams and generate WebVTT subtitles. It supports various features such as model selection, CUDA utilization, silence filtering, parallel transcription/translation, and more.

## Usage

```bash
livevtt -u <URL> [-s] [-l <BIND_ADDRESS>] [-p <BIND_PORT>] [-m <MODEL>] [-b <BEAM_SIZE>] [-c <USE_CUDA>] [-t] [-bt] [-vf <VAD_FILTER>] [-la <LANGUAGE>] [-ua <USER_AGENT>]
```

### Arguments

- `-u, --url`: URL of the live audio/video stream (defaults to TV Rain stream).
- `-s, --hard-subs`: Set if you want the subtitles to be baked into the stream itself.
- `-l, --bind-address`: The IP address to bind to (defaults to 127.0.0.1).
- `-p, --bind-port`: The port to bind to (defaults to 8000).
- `-m, --model`: Whisper model to use (defaults to large).
- `-b, --beam-size`: Beam size to use (defaults to 5).
- `-c, --use-cuda`: Use CUDA where available. Defaults to true.
- `-t, --transcribe`: If set, transcribes in the original language instead of translating to English.
- `-bt, --both-tracks`: Enable parallel transcription and translation (provides both original language and English subtitles).
- `-vf, --vad-filter`: Whether to utilize the Silero VAD model to try and filter out silences. Defaults to false.
- `-la, --language`: The original language of the stream, if known/not multilingual. Can be left unset.
- `-ua, --user-agent`: User agent to use to retrieve playlists/stream chunks (defaults to 'VLC/3.0.18 LibVLC/3.0.18').

### Subtitle Modes

The script supports three subtitle modes:

1. **Translation Only** (default):
   ```bash
   python3 main.py -la ru
   ```
   - Translates the source language to English
   - Single English subtitle track available

2. **Transcription Only**:
   ```bash
   python3 main.py -la ru -t
   ```
   - Transcribes in the original language
   - Single subtitle track in the source language

3. **Parallel Transcription and Translation**:
   ```bash
   python3 main.py -la ru -bt
   ```
   - Provides both transcription and translation
   - Two subtitle tracks available:
     * Original language transcription
     * English translation
   - Switch between tracks in your HLS player

## Accessing Transcribed Stream

Once the program is running, you can access the transcribed and/or translated stream at:

```
http://127.0.0.1:8000/playlist.m3u8
```

This URL may vary based on the bind address and port provided via the command-line options.

## Installation

Note that the minimum target Python version for this script is **Python 3.10** at present. You will also need to ensure that you have the **ffmpeg** package installed on your system.

1. Clone the repository:

   ```bash
   git clone https://github.com/Psychotropos/livevtt.git
   ```

2. Navigate to the directory:

   ```bash
   cd livevtt
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Docker Installation

### Prerequisites
- Docker installed on your system
- For GPU support: NVIDIA GPU with installed drivers and NVIDIA Container Toolkit

### Building the Docker Image

```bash
docker build -t livevtt .
```

### Running with Docker

1. CPU mode with translation:
```bash
docker run -p 8000:8000 livevtt -la ru -c false -l 0.0.0.0
```

2. CPU mode with transcription:
```bash
docker run -p 8000:8000 livevtt -la ru -c false -t -l 0.0.0.0
```

3. CPU mode with both tracks:
```bash
docker run -p 8000:8000 livevtt -la ru -c false -bt -l 0.0.0.0
```

4. GPU mode (requires NVIDIA Container Toolkit):
```bash
docker run --gpus all -p 8000:8000 livevtt -la ru -l 0.0.0.0
```

Note: When running in Docker, always use `-l 0.0.0.0` to bind to all interfaces if you want to access the service from outside the container.

### Running with Docker Compose

Use Docker Compose for a more declarative way to run the application. Edit the command array in docker-compose.yml to match your desired configuration:

```bash
docker compose up --build
```

## Examples

1. Translate Russian stream to English (default):
   ```bash
   livevtt -la ru
   ```

2. Transcribe Russian stream in Russian:
   ```bash
   livevtt -la ru -t
   ```

3. Generate both Russian transcription and English translation:
   ```bash
   livevtt -la ru -bt
   ```

4. Use a smaller model with reduced beam size (faster but less accurate):
   ```bash
   livevtt -la ru -m medium -b 1
   ```

5. Embed subtitles directly in video:
   ```bash
   livevtt -la ru -s
   ```

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
