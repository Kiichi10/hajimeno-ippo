#!/usr/bin/env python3
"""
pipeline.py — 最初の一歩 ワンショットパイプライン

台本テキストから完成動画まで一気通貫で実行する。

Usage:
  python pipeline.py <episode_id> [--skip-audio] [--skip-stock]

  episode_id: エピソード名（例: "ep001_compound_interest"）

前提:
  - episodes/{episode_id}/script.txt が存在すること
  - AivisSpeech が起動していること (http://127.0.0.1:10101)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from generate_audio import generate as generate_audio
from generate_panels import generate as generate_panels
from build_scene_plan import build_plan
from fetch_stock_video import fetch_video
from render_faceless import render


def run_pipeline(episode_id: str, skip_audio: bool = False, skip_stock: bool = False):
    start_time = time.time()
    episode_dir = PROJECT_ROOT / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)

    script_path = episode_dir / "script.txt"
    if not script_path.exists():
        print(f"ERROR: {script_path} not found")
        print(f"Create the script file first, then run this pipeline.")
        return False

    print(f"{'='*60}")
    print(f"最初の一歩 — Pipeline: {episode_id}")
    print(f"{'='*60}")

    # ── Phase 1: Audio Generation ──
    if not skip_audio:
        print(f"\n▶ Phase 1: Audio Generation")
        ok = generate_audio(str(episode_dir))
        if not ok:
            print("✗ Audio generation failed")
            return False
    else:
        print(f"\n▶ Phase 1: Audio Generation [SKIPPED]")

    # ── Phase 2: Panel Generation ──
    print(f"\n▶ Phase 2: Panel Generation")
    panels = generate_panels(str(episode_dir))

    # ── Phase 3: Scene Plan ──
    print(f"\n▶ Phase 3: Scene Plan Generation")
    plan = build_plan(str(episode_dir))

    # Apply generated panel paths to scene plan
    panel_map = {p["scene_index"]: p["panel_path"] for p in panels}
    for scene in plan["scenes"]:
        idx = scene["line_index"]
        if idx in panel_map:
            scene["visual_type"] = "animated_panel"
            scene["template"] = os.path.relpath(panel_map[idx], PROJECT_ROOT)

    # ── Phase 4: Stock Video Fetch ──
    if not skip_stock:
        print(f"\n▶ Phase 4: Stock Video Fetch")
        stock_dir = episode_dir / "stock"
        stock_dir.mkdir(exist_ok=True)

        for scene in plan["scenes"]:
            if scene["visual_type"] == "stock_overlay":
                query = scene.get("stock_query", "finance")
                local_path = fetch_video(query)
                if local_path:
                    scene["stock_video"] = os.path.relpath(local_path, PROJECT_ROOT)
                else:
                    print(f"  [WARN] No stock video for '{query}', using fallback")
                    # Try generic fallback
                    fallback = fetch_video("money finance")
                    if fallback:
                        scene["stock_video"] = os.path.relpath(fallback, PROJECT_ROOT)
                    else:
                        # Convert to static panel as last resort
                        scene["visual_type"] = "static_panel"
                        scene["image"] = "templates/animated/closing.html"

        # Update scene_plan.json with stock paths
        plan_path = episode_dir / "scene_plan.json"
        with open(plan_path, "w") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"  Updated: {plan_path}")
    else:
        print(f"\n▶ Phase 4: Stock Video Fetch [SKIPPED]")

    # ── Phase 5: Render ──
    print(f"\n▶ Phase 5: Video Rendering")
    result = render(str(episode_dir))

    # ── Summary ──
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    if result:
        print(f"✓ Pipeline complete in {elapsed:.0f}s")
        print(f"  Output: {result}")
    else:
        print(f"✗ Pipeline failed after {elapsed:.0f}s")
    print(f"{'='*60}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="最初の一歩 — 動画パイプライン")
    parser.add_argument("episode_id", help="エピソードID (例: ep001_compound_interest)")
    parser.add_argument("--skip-audio", action="store_true", help="音声生成をスキップ")
    parser.add_argument("--skip-stock", action="store_true", help="ストック動画取得をスキップ")
    args = parser.parse_args()

    result = run_pipeline(args.episode_id, args.skip_audio, args.skip_stock)
    sys.exit(0 if result else 1)
