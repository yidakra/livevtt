#!/usr/bin/env python3
"""Check progress of archive_transcriber from its manifest file."""

import json
import sys
from pathlib import Path
from collections import Counter


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


def check_progress(manifest_path="logs/archive_transcriber_manifest.jsonl"):
    """Read manifest and display progress statistics."""
    manifest_file = Path(manifest_path)

    if not manifest_file.exists():
        print(f"❌ Manifest file not found: {manifest_path}")
        print("   The archive_transcriber may not have been run yet.")
        return

    records = []
    with open(manifest_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        print("📝 Manifest file is empty - processing hasn't started yet.")
        return

    # Count statuses
    status_counts = Counter(r.get("status", "unknown") for r in records)
    total_processed = len(records)
    successful = status_counts.get("success", 0)
    failed = status_counts.get("error", 0)

    # Get latest record
    latest = records[-1]
    latest_time = latest.get("processed_at", "unknown")

    # Calculate processing times
    processing_times = [
        r.get("processing_time", 0) for r in records if r.get("status") == "success"
    ]
    avg_time = sum(processing_times) / len(processing_times) if processing_times else 0

    # Display results
    print("=" * 60)
    print("📊 Archive Transcriber Progress Report")
    print("=" * 60)
    print(f"📁 Manifest: {manifest_path}")
    print(f"🕐 Last update: {latest_time}")
    print()
    print(f"✅ Successful: {successful:>6}")
    print(f"❌ Failed:     {failed:>6}")
    print(f"📦 Total:      {total_processed:>6}")
    print()

    if successful > 0:
        success_rate = (successful / total_processed) * 100
        print(f"📈 Success rate: {success_rate:.1f}%")
        print(f"⏱️  Average processing time: {format_duration(avg_time)}")
        print()

    # Show recent files
    print("📄 Last 5 processed files:")
    print("-" * 60)
    for record in records[-5:]:
        status_icon = "✅" if record.get("status") == "success" else "❌"
        video_path = record.get("video_path", "unknown")
        filename = Path(video_path).name if video_path != "unknown" else "unknown"
        print(f"{status_icon} {filename}")
        if record.get("status") == "error":
            error_msg = record.get("error", "unknown error")
            print(f"   Error: {error_msg[:70]}...")
    print("=" * 60)

    # Show failed files if any
    if failed > 0:
        print()
        print(f"⚠️  Failed files ({failed} total):")
        print("-" * 60)
        for record in records:
            if record.get("status") == "error":
                video_path = record.get("video_path", "unknown")
                filename = (
                    Path(video_path).name if video_path != "unknown" else "unknown"
                )
                error_msg = record.get("error", "unknown error")
                print(f"❌ {filename}")
                print(f"   {error_msg[:70]}")
        print("=" * 60)


if __name__ == "__main__":
    manifest_path = (
        sys.argv[1] if len(sys.argv) > 1 else "logs/archive_transcriber_manifest.jsonl"
    )
    check_progress(manifest_path)
