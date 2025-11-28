# H100 Setup Guide

## 1. Rent H100 GPU on RunPod

1. Go to RunPod console
2. Click "Deploy" → "GPU Cloud"
3. Search for **H100 80GB**
4. Configure:
   - **Container Disk**: 50GB minimum
   - **Template**: PyTorch 2.1 or Ubuntu + CUDA
   - **Expose HTTP Ports**: `8000`
   - **Start pod**

5. Note the **Public IP** and **Port** (e.g., `123.45.67.89:8000`)

## 2. Connect via SSH

```bash
ssh root@<pod-ip> -p <ssh-port>
```

## 3. Install Dependencies

```bash
# Update system
apt-get update && apt-get install -y ffmpeg

# Install Python packages
pip install flask faster-whisper
```

## 4. Upload Server Code

Copy `h100_server.py` to the H100:

```bash
# From your local machine
scp -P <ssh-port> h100_server.py root@<pod-ip>:/root/
```

## 5. Start the Server

On the H100:

```bash
cd /root
python3 h100_server.py
```

The server will:
- Pre-load `large-v3-turbo` and `large-v3` models (takes 2-3 minutes)
- Start listening on port 8000
- Accept transcription requests

## 6. Update Local Script

On your local machine, update the endpoint to point to your H100:

```bash
# In .env file or environment
export RUNPOD_ENDPOINT_ID="dummy"  # Can be any value
export H100_URL="http://<pod-public-ip>:<port>"
```

Then run the transcriber:

```bash
python3 src/python/tools/archive_transcriber_serverless.py \
  --endpoint-id dummy \
  --api-key dummy \
  --workers 3 \
  --quick-start \
  --reverse
```

The script will now send audio to your H100 instead of RunPod serverless!

## 7. Monitor Progress

Watch the H100 server logs to see transcription progress:

```bash
# On H100
tail -f <server-output>
```

## Cost Estimate

- **H100 80GB**: ~$2.89/hour on-demand
- **Total for 142K videos**: ~19 hours = **~$55-60**
- Much cheaper than the $135 we originally estimated (that was for a different GPU tier)

## Troubleshooting

- **Connection refused**: Check firewall rules and exposed ports
- **CUDA errors**: Ensure the pod has GPU access (`nvidia-smi`)
- **Out of memory**: Reduce `--workers` on local machine
