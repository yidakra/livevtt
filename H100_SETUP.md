# H100 RunPod Transcription Guide

## ⚠️ WARNING: Not Recommended

**Cost**: ~$6,162 to complete all videos
**Local A2**: $0 and works fine
**Verdict**: Only use if time is critical

## What Went Wrong ($40 Wasted)

Our H100 testing revealed:
- **0 VTT files created** from 888 videos
- Root cause: Missing debug logging + no validation
- Base64 encoding adds 33% overhead
- SSH tunnel instability caused failures

## Fixes Applied

Modified `archive_transcriber_serverless.py`:
1. ✅ Validates API returns segments (lines 318-321)
2. ✅ Verifies VTT files exist after write (lines 327-331)
3. ✅ Logs success confirmations at INFO level (line 324)

## Setup (If You Must)

### 1. SSH Tunnel with Keep-Alive
```bash
ssh -f -N -L 8001:localhost:8000 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o TCPKeepAlive=yes \
    -i ~/.ssh/id_ed25519rp \
    root@<pod-ip> -p <ssh-port>
```

### 2. Verify H100 Server
```bash
curl -s http://localhost:8001/health
# Should return: {"status":"healthy"}
```

### 3. Run with Verbose Logging (CRITICAL!)
```bash
export H100_URL='http://localhost:8001'

python3 src/python/tools/archive_transcriber_serverless.py \
    --endpoint-id dummy \
    --api-key dummy \
    --workers 3 \
    --reverse \
    --verbose \
    > logs/h100_run.log 2>&1
```

**MUST use `--verbose`** or you won't see failures!

### 4. Monitor Success
```bash
# Watch for confirmations
tail -f logs/h100_run.log | grep "VTT files written successfully"

# Count successes
grep -c "VTT files written successfully" logs/h100_run.log
```

## Troubleshooting

**No VTT files?**
```bash
grep "returned no segments\|VTT files not created" logs/h100_run.log
```

**SSH tunnel died?**
Restart gunicorn on H100:
```bash
ssh -i ~/.ssh/id_ed25519rp root@<ip> -p <port> \
    "pkill -9 -f gunicorn && \
     python3 -m gunicorn -w 6 -b 0.0.0.0:8000 --timeout 900 --daemon h100_server:app"
```

## Script Comparison

**`archive_transcriber_serverless.py`** (what you used - wrong choice):
- For RunPod serverless endpoints using `/v2/{endpoint}/run` API
- Base64-encodes audio in JSON (33% overhead)
- You hacked it to work with H100 via `H100_URL` env var
- Wrong script for a persistent HTTP server!

**`archive_transcriber_remote.py`** (what you should have used):
- For direct HTTP servers using `/transcribe` endpoint
- Raw audio via multipart/form-data (no overhead)
- Designed for servers running `remote_whisper_server.py`
- Would have avoided 33% base64 overhead

**Recommendation**: Use `archive_transcriber_remote.py` next time!
