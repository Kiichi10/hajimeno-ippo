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
    # Each keyword maps to multiple query candidates to avoid reuse
    stock_keywords = {
        "人生": ["life journey sunset", "road path future", "person walking forward"],
        "未来": ["future city lights", "sunrise horizon", "child growing up"],
        "時間": ["clock time passing", "hourglass sand", "calendar pages"],
        "不安": ["worried thinking person", "rain window lonely", "crossroads decision"],
        "働": ["office work desk", "businessman typing", "modern workplace"],
        "怖": ["fear courage dark", "nervous hands", "looking down cliff"],
        "教": ["classroom education", "teacher blackboard", "library books studying"],
        "努力": ["training determination", "climbing mountain", "running athlete"],
        "始め": ["starting line race", "first step door", "new beginning sunrise"],
        "一歩": ["first step walking", "footprint sand", "door opening light"],
        "お金": ["money coins gold", "piggy bank coins", "wallet cash payment"],
        "貯金": ["piggy bank savings", "coins jar saving", "money growing plant"],
        "投資": ["stock market chart", "trading screen data", "investment growth"],
        "証券": ["stock exchange floor", "financial documents", "broker office"],
        "口座": ["banking application", "smartphone finance app", "online banking"],
        "NISA": ["japan finance tax", "savings account growth", "financial planning"],
        "税金": ["tax documents calculator", "government building", "receipt payment"],
        "利益": ["profit chart up", "success celebration", "growing graph"],
        "損": ["loss red chart", "falling graph market", "risk warning sign"],
        "暴落": ["stock crash red", "market panic sell", "financial crisis"],
        "回復": ["recovery growth green", "phoenix rising", "spring flowers bloom"],
        "バフェット": ["warren buffett wise", "old man thinking", "investment legend"],
        "老後": ["retirement elderly couple", "senior relaxing", "pension life"],
        "格差": ["inequality gap rich poor", "two paths diverge", "balance scale unfair"],
        "自由": ["freedom nature open", "bird flying sky", "beach relaxation"],
        "夢": ["dream clouds sky", "stars night wish", "imagination creative"],
        "完璧": ["perfection imperfect", "puzzle missing piece", "good enough thumbs up"],
        "大事": ["important key point", "spotlight focus", "heart hands care"],
        "動": ["action movement start", "running shoes ready", "button press click"],
        "申し込": ["application form sign", "click button screen", "registration online"],
        "国": ["government policy japan", "national flag building", "public institution"],
        "制度": ["system structure plan", "blueprint design", "organization chart"],
    }

    # Find all matching queries, pick one that hasn't been used recently
    candidates = []
    for keyword, queries in stock_keywords.items():
        if keyword in text:
            candidates.extend(queries)

    if not candidates:
        candidates = ["finance money business", "economy global market", "modern city aerial"]

    # Use line index to rotate through candidates
    best_query = candidates[index % len(candidates)]

    # Extract key message (not full narration text)
    overlay_main = extract_key_message(text)

    return {
        "visual_type": "stock_overlay",
        "stock_query": best_query,
        "overlay_text": overlay_main,
        "overlay_sub": "",
        "description": f"ストック+テキスト: {text[:30]}",
    }


def extract_key_message(text: str) -> str:
    """
    ナレーション全文からキーメッセージだけを抽出する。
    字幕ではなく、その場面のテーマを短く表現する。

    例:
      "学校では教わらない。親も教えてくれない。だから「わからない」のは当たり前だ。"
      → "誰も教えてくれなかった"

      "過去100年間、世界経済は何度も暴落した。でも、一度も回復しなかったことはない。"
      → "暴落しても、必ず回復する"
    """
    # カギ括弧の中身があればそれがキーメッセージ
    import re
    quoted = re.findall(r'「(.+?)」', text)
    if quoted:
        # 最も長いカギ括弧内容を使う
        best = max(quoted, key=len)
        if len(best) <= 20:
            return best

    # 句点で分割して最も短い文（＝要点）を取る
    sentences = [s.strip() for s in text.replace("。", "。\n").split("\n") if s.strip()]

    if len(sentences) == 1:
        # 一文だけなら20文字に切り詰め
        s = sentences[0].rstrip("。")
        if len(s) > 20:
            # 最後の句読点まで
            for sep in ["。", "、"]:
                idx = s.rfind(sep, 0, 20)
                if idx > 0:
                    return s[:idx]
            return s[:20]
        return s

    # 複数文: 最も「結論的」な文を選ぶ
    # 「〜だ」「〜ある」「〜ない」で終わる短い文を優先
    candidates = []
    for s in sentences:
        s = s.rstrip("。")
        if not s:
            continue
        score = 0
        if len(s) <= 20:
            score += 3
        elif len(s) <= 30:
            score += 1
        # 結論的な語尾
        if s.endswith(("だ", "ある", "ない", "いい", "いる")):
            score += 2
        # 否定は強い
        if "ない" in s:
            score += 1
        candidates.append((score, s))

    candidates.sort(key=lambda x: -x[0])
    best = candidates[0][1] if candidates else sentences[-1].rstrip("。")

    if len(best) > 25:
        best = best[:25]
    return best


def build_plan(episode_dir: str) -> dict:
    episode_dir = Path(episode_dir)
    config = load_config()

    # Read script — format: "ナレーション | キーメッセージ" or "ナレーション" (no key msg)
    script_path = episode_dir / "script.txt"
    with open(script_path) as f:
        raw_lines = [l.strip() for l in f.readlines() if l.strip()]

    lines = []
    key_messages = []
    for raw in raw_lines:
        if " | " in raw:
            narration, key_msg = raw.split(" | ", 1)
            lines.append(narration.strip())
            key_messages.append(key_msg.strip())
        else:
            lines.append(raw)
            key_messages.append(None)

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

        # Apply manually written key message if available
        if key_messages[i]:
            scene_info["overlay_text"] = key_messages[i]
            scene_info["overlay_sub"] = ""

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
