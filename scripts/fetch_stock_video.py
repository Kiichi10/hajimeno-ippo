#!/usr/bin/env python3
"""
fetch_stock_video.py — Pixabayストック動画取得

キーワードから適切なストック動画をダウンロードしてキャッシュする。
"""

import json
import os
import subprocess
import sys
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def load_config():
    with open(PROJECT_ROOT / "config.json") as f:
        return json.load(f)


_used_videos = set()  # Track used videos within a session to avoid reuse


def fetch_video(query: str, min_duration: int = 8) -> str | None:
    """
    Pixabay APIから動画を検索し、キャッシュディレクトリにダウンロードする。
    同セッション内で同じ動画が使われないようにトラッキングする。
    """
    config = load_config()
    cache_dir = PROJECT_ROOT / config["stock_video"]["cache_dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check cache - but skip already-used videos
    cache_key = hashlib.md5(query.encode()).hexdigest()[:12]
    cached = list(cache_dir.glob(f"{cache_key}_*.mp4"))
    for c in cached:
        if str(c) not in _used_videos:
            _used_videos.add(str(c))
            return str(c)

    # Get API key from environment or .env
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("PIXABAY_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"')
                    break

    if not api_key:
        # Try parent workspace .env
        for env_path in [
            Path("/Users/kiichi/Documents/VS Code/日本はこれで委員会/.env"),
            Path("/Users/kiichi/Documents/VS Code/エイミー先生の時事ニュース/.env"),
        ]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("PIXABAY_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"')
                        break
            if api_key:
                break

    if not api_key:
        print("[ERROR] PIXABAY_API_KEY not found")
        return None

    # Search API
    import urllib.request
    import urllib.parse

    search_url = (
        f"https://pixabay.com/api/videos/"
        f"?key={api_key}"
        f"&q={urllib.parse.quote(query)}"
        f"&per_page=5"
    )

    try:
        with urllib.request.urlopen(search_url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[ERROR] Pixabay API search failed: {e}")
        return None

    hits = data.get("hits", [])
    if not hits:
        print(f"[WARN] No results for query: {query}")
        return None

    # Try each hit until we find one not already used
    for hit_idx, hit in enumerate(hits):
        vid_url = hit.get("videos", {}).get("medium", {}).get("url")
        if not vid_url:
            vid_url = hit.get("videos", {}).get("small", {}).get("url")
        if not vid_url:
            continue

        safe_query = query.replace(" ", "_").replace("+", "_")[:20]
        output_path = str(cache_dir / f"{cache_key}_{hit_idx}_{safe_query}.mp4")

        # Skip if this specific file is already used
        if output_path in _used_videos:
            continue

        # If already cached, use it
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            _used_videos.add(output_path)
            return output_path

        # Download
        r = subprocess.run(
            ["curl", "-L", "-H", "Referer: https://pixabay.com/",
             "-H", "User-Agent: Mozilla/5.0", "-o", output_path, vid_url],
            capture_output=True, timeout=30
        )

        if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            _used_videos.add(output_path)
            print(f"  ✓ Downloaded: {output_path} ({os.path.getsize(output_path)/(1024*1024):.1f}MB)")
            return output_path
        else:
            if os.path.exists(output_path):
                os.remove(output_path)

    print(f"  ✗ No usable video for: {query}")
    return None


def fetch_multiple(queries: list[str]) -> dict[str, str]:
    """複数クエリを一括取得。{query: local_path} を返す"""
    results = {}
    for q in queries:
        path = fetch_video(q)
        if path:
            results[q] = path
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_stock_video.py <query> [query2] ...")
        sys.exit(1)

    for query in sys.argv[1:]:
        result = fetch_video(query)
        if result:
            print(f"  {query} → {result}")
        else:
            print(f"  {query} → FAILED")
