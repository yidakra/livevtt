import subprocess
import argparse


def publish_stream(rtmp_url, video_file=None, duration=60):
    """
    Publish a test video to an RTMP server using ffmpeg.

    Args:
        rtmp_url: The RTMP URL to publish to (e.g., rtmp://localhost/live/myStream)
        video_file: Path to a video file to stream (optional)
        duration: Duration in seconds to stream (default: 60)
    """
    if not video_file:
        # If no video file is provided, use ffmpeg's built-in test source
        cmd = [
            "ffmpeg",
            "-re",  # Read input at native frame rate
            "-f",
            "lavfi",  # Use lavfi input format
            "-i",
            "testsrc=size=640x480:rate=30",  # Test source pattern
            "-f",
            "lavfi",  # Use lavfi for audio too
            "-i",
            "sine=frequency=1000:sample_rate=44100",  # Audio tone
            "-c:v",
            "libx264",  # Video codec
            "-b:v",
            "1000k",  # Video bitrate
            "-c:a",
            "aac",  # Audio codec
            "-b:a",
            "128k",  # Audio bitrate
            "-f",
            "flv",  # Output format
            rtmp_url,  # Output URL
        ]
    else:
        # If a video file is provided, stream it
        cmd = [
            "ffmpeg",
            "-re",  # Read input at native frame rate
            "-i",
            video_file,  # Input file
            "-c:v",
            "libx264",  # Video codec
            "-b:v",
            "1000k",  # Video bitrate
            "-c:a",
            "aac",  # Audio codec
            "-b:a",
            "128k",  # Audio bitrate
            "-f",
            "flv",  # Output format
            rtmp_url,  # Output URL
        ]

    # Add timeout to the command
    if duration > 0:
        cmd = cmd[:1] + ["-t", str(duration)] + cmd[1:]

    print(f"Publishing stream to {rtmp_url}...")
    print(f"Command: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(cmd)

        # Wait for the process to complete
        process.wait()

        if process.returncode == 0:
            print("Stream published successfully.")
        else:
            print(
                f"Error publishing stream. FFmpeg exited with code {process.returncode}"
            )

    except KeyboardInterrupt:
        print("Stream publishing interrupted by user.")
        if process:
            process.terminate()
    except Exception as e:
        print(f"Error publishing stream: {e}")
        if process:
            process.terminate()


def main():
    parser = argparse.ArgumentParser(description="Publish a test RTMP stream")
    parser.add_argument(
        "--url",
        "-u",
        required=True,
        help="RTMP URL (e.g., rtmp://localhost/live/myStream)",
    )
    parser.add_argument("--video", "-v", help="Optional path to video file")
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=60,
        help="Duration in seconds (default: 60)",
    )

    args = parser.parse_args()

    publish_stream(args.url, args.video, args.duration)


if __name__ == "__main__":
    main()
