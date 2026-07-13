#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/ubuntu/livevtt"
INPUT_ROOT="${INPUT_ROOT:-/mnt/vod/srv/storage/transcoded}"
LOG_FILE="${LOG_FILE:-logs/archive_transcriber_two_phase.log}"
MANIFEST_FILE="${MANIFEST_FILE:-logs/archive_transcriber_manifest.jsonl}"
WORKERS="${WORKERS:-4}"
GPUS="${GPUS:-0,1}"
UV_BIN="${UV_BIN:-/home/ubuntu/.local/bin/uv}"

cd "$REPO_ROOT"
mkdir -p logs

cmd=(
  "$UV_BIN" run python src/python/tools/archive_transcriber.py
  "$INPUT_ROOT"
  --workers "$WORKERS"
  --two-phase
  --trim-silence
  --progress
  --log-file "$LOG_FILE"
  --manifest "$MANIFEST_FILE"
)

if [[ -n "$GPUS" ]]; then
  cmd+=(--gpus "$GPUS")
fi

exec "${cmd[@]}"
