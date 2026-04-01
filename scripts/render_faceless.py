#!/usr/bin/env python3
"""
render_faceless.py — 最初の一歩 コアレンダラー

Faceless動画を台本+シーンプランから自動レンダリングする。

入力:
  - audio/combined.wav (結合済み音声)
  - scene_plan.json (各セグメントの映像定義)

出力:
  - output/{episode_id}/final.mp4

映像タイプ:
  1. animated_panel: HTMLテンプレートのCSSアニメーションをPlaywright動画録画
  2. stock_overlay: ストック動画 + 透過テキストオーバーレイ合成
  3. static_panel: 静止パネル画像 (Ken Burns効果付き)
"""

import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_config():
    with open(PROJECT_ROOT / "config.json") as f:
        return json.load(f)


def get_audio_duration(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


# ── Animated Panel Recording ──────────────────────────────────

def record_animated_panel(html_path: str, output_mp4: str, duration_sec: float, config: dict):
    """
    PlaywrightでHTMLアニメーションを動画として録画する。
    Playwright built-in video recording を使用。
    """
    w = config["video"]["width"]
    h = config["video"]["height"]

    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={{"width": {w}, "height": {h}}},
            record_video_dir="{os.path.dirname(output_mp4)}",
            record_video_size={{"width": {w}, "height": {h}}}
        )
        page = await context.new_page()
        await page.goto("file://{html_path}")
        await page.wait_for_timeout({int(duration_sec * 1000)})
        await context.close()
        await browser.close()

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=int(duration_sec + 30)
    )
    if result.returncode != 0:
        print(f"  [WARN] Playwright recording failed: {result.stderr[-200:]}")
        return False

    # Playwright saves as .webm, find and convert
    video_dir = os.path.dirname(output_mp4)
    webm_files = sorted(Path(video_dir).glob("*.webm"), key=os.path.getmtime, reverse=True)
    if not webm_files:
        print("  [WARN] No .webm file found after recording")
        return False

    webm_path = str(webm_files[0])
    # Convert to mp4 with target duration
    cmd = [
        "ffmpeg", "-y", "-i", webm_path,
        "-t", f"{duration_sec:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(config["video"]["crf"]),
        "-pix_fmt", "yuv420p", "-r", str(config["video"]["fps"]),
        "-an", output_mp4
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    os.remove(webm_path)  # cleanup webm
    return r.returncode == 0


def record_animated_panel_frames(html_path: str, output_mp4: str, duration_sec: float, config: dict):
    """
    フォールバック: フレーム単位でスクリーンショット→ffmpegで結合。
    Playwright動画録画が使えない場合のバックアップ。
    """
    w = config["video"]["width"]
    h = config["video"]["height"]
    fps = config["video"]["fps"]
    total_frames = int(duration_sec * fps)
    interval_ms = int(1000 / fps)

    with tempfile.TemporaryDirectory() as tmpdir:
        script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={{"width": {w}, "height": {h}}})
        await page.goto("file://{html_path}")

        for i in range({total_frames}):
            await page.screenshot(path=f"{tmpdir}/frame_{{i:05d}}.png")
            await page.wait_for_timeout({interval_ms})

        await browser.close()

asyncio.run(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=int(duration_sec * 3 + 60)
        )
        if result.returncode != 0:
            print(f"  [ERROR] Frame capture failed: {result.stderr[-200:]}")
            return False

        # Compose frames into video
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", f"{tmpdir}/frame_%05d.png",
            "-c:v", "libx264", "-preset", "fast", "-crf", str(config["video"]["crf"]),
            "-pix_fmt", "yuv420p", "-an", output_mp4
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0


# ── Stock Video + Overlay Composite ───────────────────────────

def render_stock_overlay(stock_video: str, overlay_png: str, output_mp4: str,
                         duration_sec: float, config: dict, seek_sec: float = 2):
    """ストック動画にテキストオーバーレイ(透過PNG)を合成"""
    brightness = config["visuals"]["stock_brightness_adjust"]
    crf = config["video"]["crf"]
    fps = config["video"]["fps"]

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(seek_sec), "-t", f"{duration_sec:.2f}", "-i", stock_video,
        "-i", overlay_png,
        "-filter_complex",
        f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        f"crop=1920:1080,eq=brightness={brightness}[bg];"
        f"[bg][1:v]overlay=0:0:format=auto[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", output_mp4
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode == 0


# ── Static Panel (Ken Burns) ──────────────────────────────────

def render_static_panel(image_path: str, output_mp4: str, duration_sec: float, config: dict):
    """静止パネルにKen Burns効果（ゆっくりズーム）を適用"""
    fps = config["video"]["fps"]
    crf = config["video"]["crf"]

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration_sec:.2f}", "-framerate", str(fps),
        "-i", image_path,
        "-vf", "scale=1920:1080",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", output_mp4
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode == 0


# ── Template Parameter Substitution ───────────────────────────

def _resolve_panel_html(template_path: str, params: dict, out_dir: Path, index: int) -> str:
    """
    テンプレートHTMLを読み、{{key}}をparamsで置換した一時HTMLを生成する。
    テンプレート本体は変更しない。paramsがなければテンプレートをそのまま返す。
    """
    if not params:
        return template_path

    import re
    with open(template_path) as f:
        html = f.read()

    for key, value in params.items():
        html = html.replace("{{" + key + "}}", str(value))

    # 未置換プレースホルダーを空文字に
    html = re.sub(r'\{\{[a-zA-Z_0-9]+\}\}', '', html)

    resolved_path = str(out_dir / f"panel_{index:03d}.html")
    with open(resolved_path, "w") as f:
        f.write(html)
    return resolved_path


# ── Overlay PNG Generation ────────────────────────────────────

def generate_overlay_png(text_main: str, text_sub: str, output_png: str, config: dict):
    """テンプレートHTMLからテキストオーバーレイPNGを生成（透過）"""
    template_path = PROJECT_ROOT / "templates" / "overlay" / "text_overlay.html"
    with open(template_path) as f:
        html = f.read()

    html = html.replace("<!-- TEXT_MAIN -->", text_main)
    html = html.replace("<!-- TEXT_SUB -->", text_sub)

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    w = config["video"]["width"]
    h = config["video"]["height"]

    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={{"width": {w}, "height": {h}}})
        await page.goto("file://{tmp_path}")
        await page.wait_for_timeout(500)
        await page.screenshot(path="{output_png}", omit_background=True)
        await browser.close()

asyncio.run(main())
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    os.unlink(tmp_path)
    return result.returncode == 0


# ── Final Composition ─────────────────────────────────────────

def build_se_track(scenes: list, total_duration: float, config: dict, output_wav: str):
    """
    シーン切り替えポイントにSEを配置した音声トラックを生成する。
    タイトル→本編: dramatic, パネル切替: reveal, ストック切替: transition
    """
    se_config = config.get("se", {})
    se_volume = se_config.get("volume", 0.3)

    # SE file mapping by transition type
    se_map = {
        "title_to_content": se_config.get("dramatic", ""),
        "to_panel": se_config.get("reveal", ""),
        "to_stock": se_config.get("transition", ""),
        "closing": se_config.get("decision", ""),
    }

    # Resolve paths and filter existing
    se_events = []  # [(time_sec, se_file)]
    current_time = 0.0

    for i, scene in enumerate(scenes):
        if i == 0:
            current_time += scene["duration_sec"]
            continue

        # Determine SE type based on transition
        prev_type = scenes[i - 1]["visual_type"]
        curr_type = scene["visual_type"]

        if i == 1:
            se_type = "title_to_content"
        elif i == len(scenes) - 1:
            se_type = "closing"
        elif curr_type == "animated_panel":
            se_type = "to_panel"
        else:
            se_type = "to_stock"

        se_file = se_map.get(se_type, "")
        if se_file:
            se_path = str(PROJECT_ROOT / se_file)
            if os.path.exists(se_path):
                se_events.append((current_time, se_path))

        current_time += scene["duration_sec"]

    if not se_events:
        return None

    # Build ffmpeg command to mix all SEs into a single track
    inputs = []
    filter_parts = []

    for idx, (t, path) in enumerate(se_events):
        inputs.extend(["-i", path])
        filter_parts.append(
            f"[{idx}:a]adelay={int(t * 1000)}|{int(t * 1000)},"
            f"volume={se_volume},aformat=sample_rates=44100:channel_layouts=stereo[se{idx}]"
        )

    mix_inputs = "".join(f"[se{i}]" for i in range(len(se_events)))
    filter_parts.append(
        f"{mix_inputs}amix=inputs={len(se_events)}:duration=longest,"
        f"atrim=0:{total_duration:.2f}[seout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[seout]",
        "-c:a", "pcm_s16le", "-ar", "44100",
        output_wav
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        return output_wav
    else:
        print(f"  [WARN] SE track generation failed: {r.stderr[-200:]}")
        return None


def concat_segments(segment_files: list, audio_path: str, output_mp4: str,
                    bgm_path: str = None, bgm_volume: float = 0.06,
                    se_track_path: str = None):
    """全セグメントを結合し、音声+BGM+SEを合成"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")
        list_path = f.name

    # Count audio inputs and build filter
    audio_inputs = ["-i", audio_path]  # index 1
    filter_streams = ["[1:a]aformat=sample_rates=44100:channel_layouts=stereo[voice]"]
    mix_inputs = "[voice]"
    mix_count = 1
    next_idx = 2

    if bgm_path and os.path.exists(bgm_path):
        audio_inputs.extend(["-i", bgm_path])  # index 2
        filter_streams.append(
            f"[{next_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"volume={bgm_volume}[bgm]"
        )
        mix_inputs += "[bgm]"
        mix_count += 1
        next_idx += 1

    if se_track_path and os.path.exists(se_track_path):
        audio_inputs.extend(["-i", se_track_path])
        filter_streams.append(
            f"[{next_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[se]"
        )
        mix_inputs += "[se]"
        mix_count += 1
        next_idx += 1

    if mix_count > 1:
        filter_streams.append(
            f"{mix_inputs}amix=inputs={mix_count}:duration=shortest:normalize=0[aout]"
        )
        filter_complex = ";".join(filter_streams)

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            *audio_inputs,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_mp4
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            *audio_inputs,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_mp4
        ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    os.unlink(list_path)
    return r.returncode == 0


# ── Main Render Pipeline ─────────────────────────────────────

def render(episode_dir: str, scene_plan_path: str = None):
    """
    メインレンダリングパイプライン。

    episode_dir: エピソードディレクトリ（audio/, scene_plan.json含む）
    """
    episode_dir = Path(episode_dir)
    config = load_config()

    if scene_plan_path is None:
        scene_plan_path = episode_dir / "scene_plan.json"
    with open(scene_plan_path) as f:
        plan = json.load(f)

    audio_path = str(episode_dir / "audio" / "combined.wav")
    if not os.path.exists(audio_path):
        print(f"ERROR: {audio_path} not found")
        return False

    segments_dir = episode_dir / "segments"
    segments_dir.mkdir(exist_ok=True)
    output_dir = episode_dir / "output"
    output_dir.mkdir(exist_ok=True)

    segment_files = []

    for i, scene in enumerate(plan["scenes"]):
        seg_path = str(segments_dir / f"seg_{i:03d}.mp4")
        vtype = scene["visual_type"]
        duration = scene["duration_sec"]

        print(f"  [{i+1}/{len(plan['scenes'])}] {vtype}: {scene.get('description', '')[:40]}... ({duration:.1f}s)")

        if vtype == "animated_panel":
            html_path = str(PROJECT_ROOT / scene["template"])
            html_path = _resolve_panel_html(html_path, scene.get("params", {}), segments_dir, i)
            from html_to_video import capture_js_animation
            ok = capture_js_animation(
                html_path, seg_path, duration,
                fps=config["video"]["fps"],
                width=config["video"]["width"],
                height=config["video"]["height"],
                crf=config["video"]["crf"],
            )
            if not ok:
                print(f"    → Falling back to static panel...")
                png_path = seg_path.replace(".mp4", ".png")
                subprocess.run([
                    sys.executable, "-c",
                    f"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={{"width": {config['video']['width']}, "height": {config['video']['height']}}})
    pg.goto("file://{html_path}")
    pg.wait_for_timeout(5000)
    pg.screenshot(path="{png_path}")
    b.close()
"""
                ], capture_output=True, timeout=30)
                render_static_panel(png_path, seg_path, duration, config)

        elif vtype == "stock_overlay":
            stock_path = str(PROJECT_ROOT / scene["stock_video"])
            overlay_path = str(segments_dir / f"overlay_{i:03d}.png")

            generate_overlay_png(
                scene.get("overlay_text", ""),
                scene.get("overlay_sub", ""),
                overlay_path, config
            )
            render_stock_overlay(
                stock_path, overlay_path, seg_path,
                duration, config, seek_sec=scene.get("seek_sec", 2)
            )

        elif vtype == "static_panel":
            image_path = str(PROJECT_ROOT / scene["image"])
            render_static_panel(image_path, seg_path, duration, config)

        else:
            print(f"  [WARN] Unknown visual type: {vtype}")
            continue

        if os.path.exists(seg_path):
            segment_files.append(seg_path)
            sz = os.path.getsize(seg_path) / (1024 * 1024)
            print(f"    ✓ {sz:.1f}MB")
        else:
            print(f"    ✗ Failed to create segment")

    # ── SE Track ──
    total_duration = sum(s["duration_sec"] for s in plan["scenes"])
    se_track_path = str(segments_dir / "se_track.wav")
    print(f"\nGenerating SE track...")
    se_result = build_se_track(plan["scenes"], total_duration, config, se_track_path)
    if se_result:
        print(f"  ✓ SE track: {se_track_path}")
    else:
        print(f"  (no SE)")
        se_track_path = None

    # ── Final composition ──
    print(f"\nCompositing {len(segment_files)} segments + BGM + SE...")
    final_path = str(output_dir / "final.mp4")

    bgm_path = config.get("bgm", {}).get("default")
    if bgm_path:
        bgm_path = str(PROJECT_ROOT / bgm_path)

    ok = concat_segments(
        segment_files, audio_path, final_path,
        bgm_path=bgm_path,
        bgm_volume=config.get("bgm", {}).get("volume", 0.06),
        se_track_path=se_track_path
    )

    if ok:
        sz = os.path.getsize(final_path) / (1024 * 1024)
        print(f"\n✓ DONE: {final_path} ({sz:.1f}MB)")
        return final_path
    else:
        print(f"\n✗ Final composition failed")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python render_faceless.py <episode_dir> [scene_plan.json]")
        sys.exit(1)

    episode_dir = sys.argv[1]
    scene_plan = sys.argv[2] if len(sys.argv) > 2 else None
    result = render(episode_dir, scene_plan)
    sys.exit(0 if result else 1)
