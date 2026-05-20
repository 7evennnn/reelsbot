"""
ingest.py
Downloads a Reel/TikTok/YouTube Short via yt-dlp.
Returns the local file path.
"""
import shutil
import subprocess
import os
import uuid
import re

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "videos")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)





def get_duration(url: str) -> int:
    """Returns video duration in seconds without downloading it."""
    ytdlp_path = shutil.which("yt-dlp") or "yt-dlp"
    result = subprocess.run(
        [ytdlp_path, "--print", "duration", "--no-download", url],
        capture_output=True, text=True
    )
    return int(result.stdout.strip() or 0)
    
def is_supported_url(url: str) -> bool:
    patterns = [
        r"instagram\.com/(reel|p|tv)/",
        r"tiktok\.com/",
        r"youtube\.com/shorts/",
        r"youtu\.be/",
        r"twitter\.com/.+/status/",
        r"x\.com/.+/status/",
    ]
    return any(re.search(p, url) for p in patterns)




def download_reel(url: str) -> str:
    if not is_supported_url(url):
        raise ValueError(f"Unsupported URL: {url}")

    ytdlp_path = shutil.which("yt-dlp")
    print(f"[ingest] yt-dlp path: {ytdlp_path}")
    if not ytdlp_path:
        raise RuntimeError("yt-dlp not found in PATH")

    before = set(os.listdir(DOWNLOAD_DIR))
    output_template = os.path.join(DOWNLOAD_DIR, "%(title)s [%(id)s].%(ext)s")

    cmd = [
        ytdlp_path,   # ← use full path instead of "yt-dlp"
        "--merge-output-format", "mp4",
        "--output", output_template,
        url,
    ]
    # ... rest stays the same

    print(f"[ingest] Downloading: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr}")

    # Find whichever new .mp4 appeared
    after = set(os.listdir(DOWNLOAD_DIR))
    new_files = [f for f in (after - before) if f.endswith(".mp4")]

    if not new_files:
        raise FileNotFoundError(f"yt-dlp succeeded but no .mp4 found.\nAll new files: {after - before}")

    full_path = os.path.join(DOWNLOAD_DIR, new_files[0])
    print(f"[ingest] Downloaded to: {full_path}")
    return full_path


def cleanup_video(path: str):
    """Delete video file after processing to save disk space."""
    try:
        os.remove(path)
        print(f"[ingest] Cleaned up: {path}")
    except FileNotFoundError:
        pass
