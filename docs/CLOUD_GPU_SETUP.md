# Cloud GPU Processing Guide

This guide explains how to use cloud GPUs (like H100) to accelerate your archive transcription while keeping the video archive on your local server.

## Architecture Overview

```
┌──────────────────────────────────────────────┐
│   LOCAL SERVER (Current A2 machine)         │
│                                              │
│   1. Scan video archive (local disk)        │
│   2. Extract audio with FFmpeg (CPU)        │
│      Video: ~100MB → Audio: ~3MB (33x)      │
│   3. Send audio → Cloud GPU                  │
│   4. Receive VTT/TTML ← Cloud GPU            │
│   5. Save outputs locally                    │
│   6. Generate SMIL manifests                 │
└──────────────────────────────────────────────┘
                     ↕️
         (Only ~3MB audio + ~50KB results)
                     ↕️
┌──────────────────────────────────────────────┐
│   CLOUD GPU SERVER (H100 PCIe on RunPod)    │
│                                              │
│   - Faster-Whisper inference only           │
│   - 10-15x faster than A2                   │
│   - Returns transcription results           │
└──────────────────────────────────────────────┘
```

## Why This Works

**Bandwidth requirements:**
- Typical 10-minute 1080p video chunk: **100 MB**
- Extracted 16kHz mono WAV audio: **~3 MB** (33x smaller)
- VTT output text files: **~30 KB** (3300x smaller)

**Result:** Instead of uploading TBs of video, you only transfer a few GBs of audio files.

## Setup Instructions

### Step 1: Prepare Cloud GPU Instance

#### Option A: RunPod (Recommended)

1. Go to https://www.runpod.io/
2. Create an account
3. Deploy a **Pytorch** or **CUDA** template with:
   - GPU: **H100 PCIe** (cheapest at ~$2/hour)
   - Storage: 50GB (just for models)
   - Expose port: **8000**

4. SSH into the instance and install dependencies:
```bash
# Install Python packages
pip install faster-whisper fastapi uvicorn[standard]

# Copy your remote_whisper_server.py
# (Upload via RunPod's file manager or git clone)

# Start the server
python remote_whisper_server.py
```

5. Note the exposed endpoint URL (e.g., `http://12.34.56.78:8000`)

#### Option B: Other Providers

Similar process on:
- **Hyperstack**: $2.40/hour H100 PCIe
- **DataCrunch**: $1.99/hour H100 PCIe
- **Lambda Labs**: Good for longer rentals

### Step 2: Configure Local Server

On your current server with the video archive:

```bash
# Install new dependencies
poetry install

# Test connection to cloud GPU
curl http://YOUR_CLOUD_GPU_IP:8000/health
# Should return: {"status": "healthy", "models_loaded": 2}
```

### Step 3: Run Archive Transcription

```bash
poetry run python src/python/tools/archive_transcriber_remote.py \
  --remote-url http://YOUR_CLOUD_GPU_IP:8000 \
  --workers 4 \
  --progress \
  /mnt/vod/srv/storage/transcoded/
```

**Key parameters:**
- `--remote-url`: Your cloud GPU server endpoint
- `--workers 4`: Process 4 files in parallel (adjust based on GPU memory)
- `--progress`: Show progress bar

## Performance Expectations

### With H100 PCIe @ $2.50/hour

**Processing speed per worker:**
- 10-minute video: ~30-45 seconds total (extract + transcribe + translate)
- Breakdown:
  - Audio extraction (local): 5-10s
  - Network transfer: 2-5s (depends on your upload speed)
  - Whisper inference (H100): 15-20s
  - Result download: <1s

**With 4 parallel workers:**
- ~150-200 videos per hour
- Cost per video: ~$0.0125-0.015

**Total archive completion:**
- 10,000 videos: ~50-70 hours = **2-3 days** @ ~$125-175
- 50,000 videos: ~250-350 hours = **10-14 days** @ ~$625-875

Compare to: **Several months** on A2 with same cost in electricity.

## Network Requirements

**Upload bandwidth needed:**
- 4 workers × 3MB audio / 45 seconds = ~0.5 Mbps sustained
- **Minimum:** 5 Mbps upload (comfortable)
- **Recommended:** 10+ Mbps upload

Check your upload speed:
```bash
# Test upload to cloud GPU
dd if=/dev/zero bs=1M count=100 | ssh user@cloud_gpu "cat > /dev/null"
```

## Cost Optimization Tips

### 1. Use Spot Instances
- RunPod Spot: Save 50-70% (may get interrupted)
- Good for batch processing (can resume)

### 2. Process in Batches
Stop and start cloud GPU between sessions:
```bash
# Process 1000 files
--max-files 1000

# Stop cloud GPU when done
# Resume later from where you left off (uses manifest)
```

### 3. Increase Workers
If H100 has capacity (check GPU memory):
```bash
# Try 6-8 workers for better GPU utilization
--workers 8
```

Monitor GPU usage:
```bash
# On cloud GPU
watch -n 1 nvidia-smi
```

### 4. Use INT8 Quantization
Faster with minimal quality loss:
```bash
--compute-type int8_float16
```

## Alternative Approaches

### Option B: SSH + rsync (No API)

If you prefer simpler setup without running a server:

1. **On cloud GPU:** Just install faster-whisper
2. **Transfer files with rsync:**
```bash
# Sync audio files to cloud
rsync -avz /tmp/audio_batch/ user@cloudgpu:/workspace/audio/

# Run whisper on cloud
ssh user@cloudgpu "cd /workspace && python process_batch.py"

# Download results
rsync -avz user@cloudgpu:/workspace/output/ /local/output/
```

### Option C: Cloud Storage (For Very Large Archives)

If your upload speed is good (100+ Mbps):

1. Upload archive to cloud storage (S3/GCS)
2. Run entire pipeline on cloud GPU
3. Download only the VTT/TTML results

**When to use:**
- Fast internet connection
- Archive <10TB
- Want to avoid managing local processing

## Monitoring and Debugging

### Check Remote GPU Status
```bash
curl http://YOUR_CLOUD_GPU:8000/health
```

### Monitor Processing Speed
```bash
# Local server - watch the logs
tail -f logs/archive_transcriber_manifest.jsonl
```

### GPU Utilization (on cloud)
```bash
# Should show ~80-100% GPU utilization with multiple workers
nvidia-smi dmon -s u
```

### Network Bandwidth
```bash
# Monitor upload usage (local server)
iftop -i eth0
```

## Troubleshooting

### Connection Timeout
- Check firewall rules on cloud GPU
- Ensure port 8000 is exposed in RunPod settings
- Try increasing timeout: `--timeout 900` in requests

### GPU Out of Memory
- Reduce `--workers` (try 2-3 instead of 4)
- Use `--compute-type int8_float16`
- Process smaller batch sizes

### Slow Upload Speed
- Compress audio more: `--sample-rate 8000` (may reduce quality)
- Reduce workers to match bandwidth
- Consider spot instances with better network

## Security Considerations

1. **Use SSH Tunnel** for production:
```bash
# Create secure tunnel
ssh -L 8000:localhost:8000 user@cloudgpu

# Then use local URL
--remote-url http://localhost:8000
```

2. **Add API authentication** in `remote_whisper_server.py`:
```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/transcribe")
async def transcribe(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # Validate token
    ...
```

3. **Use VPN** if processing sensitive content

## Summary

**Recommended Setup:**
- Cloud GPU: **H100 PCIe** on RunPod ($2-2.50/hour)
- Workers: **4-6 parallel**
- Expected speedup: **10-15x vs A2**
- Completion time: **2-14 days** (vs months)
- Total cost: **$125-875** depending on archive size

**Key advantages:**
✅ Keep video archive local (no massive uploads)
✅ Only GPU processing moved to cloud
✅ Pay only for actual GPU time
✅ Easy to stop/resume processing
✅ Can use spot instances for 50-70% savings
