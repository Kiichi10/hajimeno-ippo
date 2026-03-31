#!/usr/bin/env python3
"""
build_scene_plan.py — 台本からシーンプラン(scene_plan.json)を生成

台本テキスト + 音声ファイル群から、各セリフに映像タイプを割り当てて
render_faceless.py が消費するJSONを出力する。

Usage:
  python build_scene_plan.py <episode_dir>

episode_dir に以下が必要:
  - script.txt (台本)
  - audio/line_00.wav, line_01.wav, ... (各行の音声)

出力:
  - episode_dir/scene_plan.json
"""

import json
import os
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def load_config():
    with open(PROJECT_ROOT / "config.json") as f:
        return json.load(f)


def get_audio_duration(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def classify_line(text: str, index: int, total: int) -> dict:
    """
    セリフの内容からシーンの映像タイプを推定する。

    返り値:
      {
        "visual_type": "animated_panel" | "stock_overlay" | "static_panel",
        "template": "...",       # animated_panelの場合
        "stock_query": "...",    # stock_overlayの場合
        "overlay_text": "...",
        "overlay_sub": "...",
        ...
      }
    """
    # First line = title card
    if index == 0:
        return {
            "visual_type": "animated_panel",
            "template": "templates/animated/title_card.html",
            "description": "タイトルカード",
        }

    # Last line = closing
    if index == total - 1:
        return {
            "visual_type": "animated_panel",
            "template": "templates/animated/closing.html",
            "description": "クロージング",
        }

    # Lines with numbers/data → animated panel (chart)
    has_numbers = any(c.isdigit() for c in text)
    has_comparison = any(w in text for w in ["比べ", "差", "VS", "一方", "対し"])
    has_percent = "%" in text or "パーセント" in text or "割" in text
    has_growth = any(w in text for w in ["増え", "倍", "成長", "複利", "運用"])

    if has_numbers and (has_percent or has_growth):
        return {
            "visual_type": "animated_panel",
            "template": "templates/animated/bar_chart.html",
            "description": f"データパネル: {text[:30]}",
        }

    if has_comparison and has_numbers:
        return {
            "visual_type": "animated_panel",
            "template": "templates/animated/comparison.html",
            "description": f"比較パネル: {text[:30]}",
        }

    if has_numbers and len(text) < 30:
        return {
            "visual_type": "animated_panel",
            "template": "templates/animated/counter.html",
            "description": f"カウンター: {text[:30]}",
        }

    # Lines with emotional/motivational content → stock video + overlay
    stock_keywords = {
        "人生": "life journey",
        "未来": "future city",
        "時間": "clock time",
        "不安": "worried person",
        "働": "office work",
        "努力": "training hard",
        "始め": "starting line",
        "一歩": "first step walking",
        "お金": "money coins",
        "貯金": "piggy bank savings",
        "投資": "stock market",
        "証券": "stock exchange",
        "バフェット": "warren buffett",
        "老後": "retirement elderly",
        "格差": "inequality gap",
        "自由": "freedom nature",
        "夢": "dream sky",
    }

    best_query = "finance money"
    for keyword, query in stock_keywords.items():
        if keyword in text:
            best_query = query
            break

    # Split long text for overlay
    if len(text) > 25:
        mid = len(text) // 2
        # Find a natural break point near the middle
        for char in ["。", "、", "が", "は", "を", "に", "で", "と"]:
            pos = text.find(char, mid - 10, mid + 10)
            if pos > 0:
                mid = pos + 1
                break
        overlay_main = text[:mid]
        overlay_sub = text[mid:]
    else:
        overlay_main = text
        overlay_sub = ""

    return {
        "visual_type": "stock_overlay",
        "stock_query": best_query,
        "overlay_text": overlay_main,
        "overlay_sub": overlay_sub,
        "description": f"ストック+テキスト: {text[:30]}",
    }


def build_plan(episode_dir: str) -> dict:
    episode_dir = Path(episode_dir)
    config = load_config()

    # Read script
    script_path = episode_dir / "script.txt"
    with open(script_path) as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    # Get audio durations
    audio_dir = episode_dir / "audio"
    gap = config["audio"]["line_gap_sec"]

    scenes = []
    for i, line_text in enumerate(lines):
        wav_path = audio_dir / f"line_{i:02d}.wav"
        if not wav_path.exists():
            print(f"[WARN] Audio not found: {wav_path}")
            continue

        duration = get_audio_duration(str(wav_path)) + gap

        scene_info = classify_line(line_text, i, len(lines))
        scene_info["line_index"] = i
        scene_info["line_text"] = line_text
        scene_info["duration_sec"] = round(duration, 2)

        scenes.append(scene_info)

    plan = {
        "episode_dir": str(episode_dir),
        "total_scenes": len(scenes),
        "total_duration_sec": round(sum(s["duration_sec"] for s in scenes), 2),
        "scenes": scenes,
    }

    # Save
    output_path = episode_dir / "scene_plan.json"
    with open(output_path, "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"Scene plan generated: {output_path}")
    print(f"  {len(scenes)} scenes, {plan['total_duration_sec']:.1f}s total")

    # Summary
    types = {}
    for s in scenes:
        t = s["visual_type"]
        types[t] = types.get(t, 0) + 1
    for t, count in sorted(types.items()):
        print(f"  {t}: {count}")

    return plan


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_scene_plan.py <episode_dir>")
        sys.exit(1)

    build_plan(sys.argv[1])
