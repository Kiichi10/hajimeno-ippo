#!/usr/bin/env python3
"""
html_to_video.py — CSSアニメーション付きHTMLを動画(MP4)として録画

CSS animationDelayを負の値に設定してフレームごとにスクリーンショットし、
ffmpegで結合する方式。システム負荷に依存しない完璧なフレームタイミング。

Usage:
  python html_to_video.py <html_path> <output_mp4> --duration 6 --fps 30
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def capture_css_animation(
    html_path: str,
    output_mp4: str,
    duration: float = 5.0,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    crf: int = 18,
) -> bool:
    """
    CSSアニメーションをフレーム単位で完璧にキャプチャする。

    各フレームでanimationDelayを負の値に設定し、アニメーションを
    指定時刻の状態に「シーク」してからスクリーンショットを撮る。
    """
    total_frames = int(duration * fps)
    ms_per_frame = 1000.0 / fps

    with tempfile.TemporaryDirectory() as frames_dir:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--force-color-profile=srgb",
                    "--disable-background-timer-throttling",
                ],
            )
            page = browser.new_page(viewport={"width": width, "height": height})

            abs_path = str(Path(html_path).resolve())
            page.goto(f"file://{abs_path}")
            page.wait_for_timeout(500)  # フォント読み込み待ち

            # 全アニメーションを一旦停止
            page.evaluate("""
                () => {
                    document.querySelectorAll('*').forEach(el => {
                        const s = window.getComputedStyle(el);
                        if (s.animationName && s.animationName !== 'none') {
                            el.style.animationPlayState = 'paused';
                        }
                    });
                }
            """)

            t0 = time.time()
            for i in range(total_frames):
                time_ms = i * ms_per_frame

                # 各アニメーションを指定時刻にシーク
                page.evaluate(
                    """
                    (timeMs) => {
                        document.querySelectorAll('*').forEach(el => {
                            const s = window.getComputedStyle(el);
                            if (s.animationName && s.animationName !== 'none') {
                                el.style.animationDelay = '-' + (timeMs / 1000) + 's';
                                el.style.animationPlayState = 'paused';
                            }
                        });
                    }
                    """,
                    time_ms,
                )

                page.screenshot(
                    path=os.path.join(frames_dir, f"frame_{i:06d}.jpg"),
                    type="jpeg",
                    quality=95,
                )

            elapsed = time.time() - t0
            capture_fps = total_frames / elapsed if elapsed > 0 else 0
            print(f"  Captured {total_frames} frames in {elapsed:.1f}s ({capture_fps:.0f} fps)")

            browser.close()

        # ffmpegで結合
        os.makedirs(os.path.dirname(output_mp4) or ".", exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.jpg"),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            output_mp4,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"  [ERROR] ffmpeg encode failed: {r.stderr[-200:]}")
            return False

        size_mb = os.path.getsize(output_mp4) / (1024 * 1024)
        print(f"  Encoded: {output_mp4} ({size_mb:.1f}MB)")
        return True


def capture_js_animation(
    html_path: str,
    output_mp4: str,
    duration: float = 5.0,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    crf: int = 18,
) -> bool:
    """
    CSSアニメーション/JSアニメーションをリアルタイムキャプチャ。
    Playwrightのwait_for_timeoutで正確なタイミングを確保。
    """
    total_frames = int(duration * fps)
    interval_ms = int(1000 / fps)

    with tempfile.TemporaryDirectory() as frames_dir:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                ],
            )
            page = browser.new_page(viewport={"width": width, "height": height})

            abs_path = str(Path(html_path).resolve())
            page.goto(f"file://{abs_path}")
            page.wait_for_timeout(300)

            t0 = time.time()
            for i in range(total_frames):
                page.screenshot(
                    path=os.path.join(frames_dir, f"frame_{i:06d}.jpg"),
                    type="jpeg",
                    quality=95,
                )
                # Wait until next frame time
                if i < total_frames - 1:
                    page.wait_for_timeout(interval_ms)

            elapsed = time.time() - t0
            print(f"  Captured {total_frames} frames in {elapsed:.1f}s ({total_frames/elapsed:.0f} capture fps)")
            browser.close()

        os.makedirs(os.path.dirname(output_mp4) or ".", exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frames_dir, "frame_%06d.jpg"),
            "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", output_mp4,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture animated HTML as MP4")
    parser.add_argument("html", help="Path to HTML file")
    parser.add_argument("output", help="Output MP4 path")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--mode", choices=["css", "js"], default="css")
    args = parser.parse_args()

    if args.mode == "css":
        ok = capture_css_animation(args.html, args.output, args.duration, args.fps, args.width, args.height)
    else:
        ok = capture_js_animation(args.html, args.output, args.duration, args.fps, args.width, args.height)

    sys.exit(0 if ok else 1)
