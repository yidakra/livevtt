#!/bin/bash
# Convenience script to start archive_transcriber in a tmux session

SESSION_NAME="transcriber"

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "⚠️  Session '$SESSION_NAME' already exists!"
    echo "   Options:"
    echo "   1. Attach to it:  tmux attach -t $SESSION_NAME"
    echo "   2. Kill it first: tmux kill-session -t $SESSION_NAME"
    exit 1
fi

echo "🚀 Starting archive_transcriber in tmux session '$SESSION_NAME'"
echo "   You can detach with: Ctrl+B, then D"
echo "   You can reattach with: tmux attach -t $SESSION_NAME"
echo ""

# Create logs directory
mkdir -p logs

# Start tmux session with the command
tmux new-session -s "$SESSION_NAME" -d "source .venv/bin/activate && python src/python/tools/archive_transcriber.py --progress --force 2>&1 | tee logs/transcriber_$(date +%Y%m%d_%H%M%S).log"

# Attach to the session
tmux attach -t "$SESSION_NAME"
