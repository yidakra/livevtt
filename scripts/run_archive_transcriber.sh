#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/ubuntu/livevtt"
INPUT_ROOT="${INPUT_ROOT:-/mnt/vod/srv/storage/transcoded}"
LOG_FILE="${LOG_FILE:-logs/archive_transcriber_two_phase.log}"
MANIFEST_FILE="${MANIFEST_FILE:-logs/archive_transcriber_manifest.jsonl}"
WORKERS="${WORKERS:-4}"
GPUS="${GPUS:-0,1}"
# 150 audio-minutes, not the tool's 220 default: that default was sized against
# the 31 GB this host had before the 2026-08-31 re-provision cut it to 28 GB.
# Peak RSS is ~13.5 GB floor + 0.44 GB + 0.055 GB per audio-minute in flight.
TRANSCRIBE_MINUTES_BUDGET="${TRANSCRIBE_MINUTES_BUDGET:-150}"
# Weekly, not the tool's 24 h default: a full rescan of this archive is a
# ~13-hour NFS find, so a daily expiry spends half of every day scanning.
# Weekly bounds how long new arrivals can wait: ~40 videos accumulate per week
# at observed rates (1,219 over the 31 weeks the stale cache hid them), which
# is a few hours of GPU work per rescan.
SCAN_CACHE_MAX_AGE_HOURS="${SCAN_CACHE_MAX_AGE_HOURS:-168}"
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
  --transcribe-minutes-budget "$TRANSCRIBE_MINUTES_BUDGET"
  --scan-cache-max-age-hours "$SCAN_CACHE_MAX_AGE_HOURS"
)

if [[ -n "$GPUS" ]]; then
  cmd+=(--gpus "$GPUS")
fi

exec "${cmd[@]}"
