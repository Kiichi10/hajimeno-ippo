#!/usr/bin/env python3
"""
generate_panels.py — エピソード固有のパネルHTMLを生成

台本(script.txt)を読み、各シーンに必要なパネルHTMLを
episodes/{id}/panels/ に生成する。

テンプレートの骨格（CSS/アニメーション）を使い、
コンテンツ（タイトル、数値、ラベル）をエピソード固有に埋める。

Usage:
  python generate_panels.py <episode_dir>
"""

import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ── Template fragments ────────────────────────────────────────

FONT = "'YuGothic', 'Yu Gothic', 'Noto Sans JP', sans-serif"

TITLE_CARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; background: #0a0a1a;
  font-family: {font}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.container {{ text-align: center; position: relative; }}
.ring {{ position: absolute; border-radius: 50%; border: 1px solid rgba(255,215,0,0.08);
  top: 50%; left: 50%; transform: translate(-50%, -50%); animation: ringPulse 4s ease-in-out infinite; }}
.ring:nth-child(1) {{ width: 500px; height: 500px; }}
.ring:nth-child(2) {{ width: 700px; height: 700px; animation-delay: 0.5s; }}
.ring:nth-child(3) {{ width: 900px; height: 900px; animation-delay: 1.0s; }}
@keyframes ringPulse {{ 0%,100% {{ opacity:0.3; transform:translate(-50%,-50%) scale(1); }}
  50% {{ opacity:0.8; transform:translate(-50%,-50%) scale(1.05); }} }}
.main-text {{ font-size: 68px; font-weight: 900; color: #fff; line-height: 1.4; position: relative; z-index: 1; }}
.main-text .line {{ opacity: 0; display: block; }}
.main-text .line:nth-child(1) {{ animation: slideIn 0.8s ease-out 0.5s forwards; }}
.main-text .line:nth-child(2) {{ animation: slideIn 0.8s ease-out 1.2s forwards; }}
.accent {{ color: #ffd700; }}
.divider {{ width: 200px; height: 2px; background: linear-gradient(90deg, transparent, #ffd700, transparent);
  margin: 30px auto; opacity: 0; animation: fadeIn 0.8s ease-out 2.0s forwards; }}
.sub-text {{ font-size: 30px; color: #aaaacc; margin-top: 10px; opacity: 0;
  animation: fadeIn 0.8s ease-out 2.5s forwards; position: relative; z-index: 1; }}
@keyframes slideIn {{ from {{ opacity:0; transform:translateY(30px); }} to {{ opacity:1; transform:translateY(0); }} }}
@keyframes fadeIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
</style></head><body>
<div class="container">
  <div class="ring"></div><div class="ring"></div><div class="ring"></div>
  <div class="main-text">
    <span class="line">{line1}</span>
    <span class="line">{line2}</span>
  </div>
  <div class="divider"></div>
  <div class="sub-text">最初の一歩 — 動けなかったあなたへ</div>
</div></body></html>"""

CLOSING_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; background: #0a0a1a;
  font-family: {font}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.container {{ text-align: center; }}
.main-text {{ font-size: 56px; color: #fff; font-weight: 900; line-height: 1.7; letter-spacing: 2px; }}
.main-text .line {{ display: block; opacity: 0; }}
.main-text .line:nth-child(1) {{ animation: fadeUp 0.8s ease-out 0.5s forwards; }}
.main-text .line:nth-child(2) {{ animation: fadeUp 0.8s ease-out 1.3s forwards; }}
.gold {{ color: #ffd700; font-size: 60px; }}
.divider {{ width: 300px; height: 2px; background: linear-gradient(90deg, transparent, #ffd700, transparent);
  margin: 40px auto; opacity: 0; animation: fadeUp 0.8s ease-out 2.5s forwards; }}
.cta {{ font-size: 28px; color: #aaaacc; line-height: 1.8; opacity: 0; animation: fadeUp 0.8s ease-out 3.0s forwards; }}
.channel {{ font-size: 22px; color: #666; margin-top: 30px; opacity: 0; animation: fadeUp 0.8s ease-out 3.5s forwards; }}
@keyframes fadeUp {{ from {{ opacity:0; transform:translateY(20px); }} to {{ opacity:1; transform:translateY(0); }} }}
</style></head><body>
<div class="container">
  <div class="main-text">
    <span class="line">{line1}</span>
    <span class="line"><span class="gold">{line2}</span></span>
  </div>
  <div class="divider"></div>
  <div class="cta">{cta}</div>
  <div class="channel">最初の一歩 — 動けなかったあなたへ</div>
</div></body></html>"""

BAR_CHART_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; background: #0a0a1a;
  font-family: {font}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.container {{ width: 1500px; height: 800px; position: relative; }}
.title {{ font-size: 44px; color: #fff; font-weight: 700; text-align: center; margin-bottom: 50px;
  opacity: 0; animation: fadeIn 0.8s ease-out 0.3s forwards; }}
.highlight {{ color: #ffd700; }}
.chart {{ width: 1300px; height: 550px; margin: 0 auto; position: relative;
  border-left: 2px solid #333; border-bottom: 2px solid #333; }}
.bar-group {{ position: absolute; bottom: 0; display: flex; flex-direction: column; align-items: center; }}
.bar {{ width: 140px; border-radius: 10px 10px 0 0; position: relative; height: 0; }}
{bar_styles}
@keyframes growBar {{ from {{ height: 0; }} to {{ height: var(--target-height); }} }}
.bar-label {{ color: #fff; font-size: 36px; font-weight: 700; position: absolute; top: -50px;
  width: 100%; text-align: center; white-space: nowrap; overflow: visible; opacity: 0; }}
{label_styles}
.year-label {{ color: #888; font-size: 22px; margin-top: 15px; opacity: 0; }}
{year_styles}
@keyframes fadeIn {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
</style></head><body>
<div class="container">
  <div class="title">{title}</div>
  <div class="chart">
    {bars_html}
  </div>
</div></body></html>"""

COMPARISON_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; background: #0a0a1a;
  font-family: {font}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.container {{ width: 1500px; }}
.title {{ font-size: 44px; color: #fff; font-weight: 700; text-align: center; margin-bottom: 60px;
  opacity: 0; animation: fadeIn 0.8s ease-out 0.3s forwards; }}
.highlight {{ color: #ff4444; }}
.comparison {{ display: flex; justify-content: center; gap: 100px; align-items: flex-end; }}
.person {{ text-align: center; }}
.person-label {{ font-size: 30px; color: #aaaacc; margin-bottom: 15px; opacity: 0; }}
.person:nth-child(1) .person-label {{ animation: fadeIn 0.5s ease-out 1.0s forwards; }}
.person:nth-child(3) .person-label {{ animation: fadeIn 0.5s ease-out 1.5s forwards; }}
.amount-bar {{ width: 250px; border-radius: 12px 12px 0 0; display: flex; align-items: flex-end;
  justify-content: center; padding-bottom: 25px; height: 0; }}
.person:nth-child(1) .amount-bar {{ background: linear-gradient(180deg, #ffd700, #ff8c00);
  animation: growBar 1.5s ease-out 1.5s forwards; --target-height: {left_height}px; }}
.person:nth-child(3) .amount-bar {{ background: linear-gradient(180deg, #555, #333);
  animation: growBar 1.5s ease-out 2.0s forwards; --target-height: {right_height}px; }}
.amount {{ font-size: 48px; font-weight: 900; color: #fff; opacity: 0; }}
.person:nth-child(1) .amount {{ animation: fadeIn 0.5s ease-out 2.8s forwards; }}
.person:nth-child(3) .amount {{ animation: fadeIn 0.5s ease-out 3.3s forwards; }}
.vs {{ font-size: 80px; color: #333; font-weight: 900; align-self: center; margin-bottom: 100px;
  opacity: 0; animation: fadeIn 0.5s ease-out 1.2s forwards; }}
.gap-box {{ text-align: center; margin-top: 60px; padding: 30px 60px; border: 2px solid #ff4444;
  border-radius: 16px; background: rgba(255,68,68,0.1); opacity: 0; animation: fadeIn 0.8s ease-out 4.0s forwards; }}
.gap-number {{ font-size: 64px; font-weight: 900; color: #ff4444; }}
.gap-label {{ font-size: 26px; color: #aaaacc; margin-top: 10px; }}
@keyframes growBar {{ from {{ height: 0; }} to {{ height: var(--target-height); }} }}
@keyframes fadeIn {{ from {{ opacity:0; transform:translateY(15px); }} to {{ opacity:1; transform:translateY(0); }} }}
</style></head><body>
<div class="container">
  <div class="title">{title}</div>
  <div class="comparison">
    <div class="person">
      <div class="person-label">{left_label}</div>
      <div class="amount-bar"><div class="amount">{left_amount}</div></div>
    </div>
    <div class="vs">VS</div>
    <div class="person">
      <div class="person-label">{right_label}</div>
      <div class="amount-bar"><div class="amount">{right_amount}</div></div>
    </div>
  </div>
  <div class="gap-box">
    <div class="gap-number">{gap_amount}</div>
    <div class="gap-label">{gap_label}</div>
  </div>
</div></body></html>"""

COUNTER_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ width: 1920px; height: 1080px; background: #0a0a1a;
  font-family: {font}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.container {{ text-align: center; }}
.label {{ font-size: 36px; color: #aaaacc; margin-bottom: 20px; opacity: 0; animation: fadeIn 0.6s ease-out 0.5s forwards; }}
.number {{ font-size: 160px; font-weight: 900; color: #ffd700; text-shadow: 0 0 40px rgba(255,215,0,0.4);
  font-variant-numeric: tabular-nums; }}
.unit {{ font-size: 60px; color: #ffd700; opacity: 0.8; }}
.sub {{ font-size: 28px; color: #888; margin-top: 20px; opacity: 0; animation: fadeIn 0.6s ease-out 3.5s forwards; }}
@keyframes fadeIn {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
</style></head><body>
<div class="container">
  <div class="label">{label}</div>
  <div class="number"><span id="counter">0</span><span class="unit">{unit}</span></div>
  <div class="sub">{sub}</div>
</div>
<script>
const target = {target};
const duration = 3000;
const startTime = performance.now() + 1000;
function easeOutExpo(t) {{ return t === 1 ? 1 : 1 - Math.pow(2, -10 * t); }}
function animate(now) {{
  const elapsed = now - startTime;
  if (elapsed < 0) {{ requestAnimationFrame(animate); return; }}
  const progress = Math.min(elapsed / duration, 1);
  document.getElementById('counter').textContent = Math.round(target * easeOutExpo(progress)).toLocaleString();
  if (progress < 1) requestAnimationFrame(animate);
}}
requestAnimationFrame(animate);
</script></body></html>"""


# ── Panel generation functions ─────────────────────────────────

def generate_title(line1: str, line2: str) -> str:
    return TITLE_CARD_HTML.format(font=FONT, line1=line1, line2=line2)


def generate_closing(line1: str, line2: str, cta: str) -> str:
    return CLOSING_HTML.format(font=FONT, line1=line1, line2=line2, cta=cta)


def generate_bar_chart(title: str, bars: list[dict]) -> str:
    """bars: [{"label": "300万", "year": "開始", "height": 80, "mult": "×1.0"}, ...]"""
    max_bars = min(len(bars), 4)
    x_positions = [120, 380, 640, 900]
    colors = [
        ("linear-gradient(180deg, #ffd700, #ff8c00)", "#fff"),
        ("linear-gradient(180deg, #ffd700, #ff8c00)", "#fff"),
        ("linear-gradient(180deg, #ffd700, #e67e00)", "#fff"),
        ("linear-gradient(180deg, #ff4444, #cc0000)", "#ff4444"),
    ]

    bar_styles = ""
    label_styles = ""
    year_styles = ""
    bars_html = ""

    for i, bar in enumerate(bars[:max_bars]):
        delay_bar = 1.0 + i * 0.8
        delay_label = delay_bar + 1.0
        bg, label_color = colors[min(i, len(colors) - 1)]

        bar_styles += (
            f".bar-group:nth-child({i+1}) .bar {{ background: {bg}; "
            f"animation: growBar 1.2s ease-out {delay_bar}s forwards; "
            f"--target-height: {bar['height']}px; }}\n"
        )
        label_styles += (
            f".bar-group:nth-child({i+1}) .bar-label {{ "
            f"animation: fadeIn 0.5s ease-out {delay_label}s forwards; "
        )
        if i == max_bars - 1:
            label_styles += f"font-size: 42px; color: {label_color}; "
        label_styles += "}\n"
        year_styles += (
            f".bar-group:nth-child({i+1}) .year-label {{ "
            f"animation: fadeIn 0.5s ease-out {delay_bar}s forwards; }}\n"
        )
        bars_html += (
            f'    <div class="bar-group" style="left: {x_positions[i]}px;">\n'
            f'      <div class="bar"><div class="bar-label">{bar["label"]}</div></div>\n'
            f'      <div class="year-label">{bar.get("year", "")}</div>\n'
            f'    </div>\n'
        )

    return BAR_CHART_HTML.format(
        font=FONT, title=title,
        bar_styles=bar_styles, label_styles=label_styles,
        year_styles=year_styles, bars_html=bars_html,
    )


def generate_comparison(title: str, left_label: str, left_amount: str,
                        right_label: str, right_amount: str,
                        gap_amount: str, gap_label: str,
                        left_height: int = 400, right_height: int = 200) -> str:
    return COMPARISON_HTML.format(
        font=FONT, title=title,
        left_label=left_label, left_amount=left_amount,
        right_label=right_label, right_amount=right_amount,
        gap_amount=gap_amount, gap_label=gap_label,
        left_height=left_height, right_height=right_height,
    )


def generate_counter(label: str, target: int, unit: str, sub: str) -> str:
    return COUNTER_HTML.format(font=FONT, label=label, target=target, unit=unit, sub=sub)


# ── Main: Parse script and generate panels ─────────────────────

def generate(episode_dir: str) -> list[dict]:
    """
    台本を読み、パネルHTMLを episodes/{id}/panels/ に生成する。
    返り値: [{"scene_index": i, "panel_path": "episodes/.../panels/xxx.html"}, ...]
    """
    episode_dir = Path(episode_dir)
    panels_dir = episode_dir / "panels"
    panels_dir.mkdir(exist_ok=True)

    script_path = episode_dir / "script.txt"
    with open(script_path) as f:
        raw_lines = [l.strip() for l in f.readlines() if l.strip()]

    panels = []
    total = len(raw_lines)

    for i, raw in enumerate(raw_lines):
        # Strip key message and panel tags for analysis
        narration = raw.split(" | ")[0].split(" [panel:")[0].strip()

        # ── Title card (first line) ──
        if i == 0:
            parts = narration.split("。", 1)
            line1 = parts[0]
            line2 = parts[1].strip().rstrip("。") if len(parts) > 1 and parts[1].strip() else ""
            html = generate_title(line1, line2)
            path = str(panels_dir / f"scene_{i:02d}_title.html")
            with open(path, "w") as f:
                f.write(html)
            panels.append({"scene_index": i, "panel_path": path, "type": "title"})
            print(f"  ✓ scene {i:02d}: タイトル「{line1[:25]}...」")
            continue

        # ── Closing (last line) ──
        if i == total - 1:
            sentences = [s.strip() for s in narration.replace("。", "。\n").split("\n") if s.strip()]
            line1 = sentences[0].rstrip("。") if sentences else narration
            line2 = sentences[1].rstrip("。") if len(sentences) > 1 else ""
            cta = "最初の一歩を、今日踏み出そう。"
            html = generate_closing(line1, line2, cta)
            path = str(panels_dir / f"scene_{i:02d}_closing.html")
            with open(path, "w") as f:
                f.write(html)
            panels.append({"scene_index": i, "panel_path": path, "type": "closing"})
            print(f"  ✓ scene {i:02d}: クロージング「{line1[:25]}...」")
            continue

        # ── Explicit [panel:type ...] tag ──
        panel_match = re.search(r'\[panel:(\w+)\s*(.*?)\]', raw)
        if panel_match:
            panel_type = panel_match.group(1)
            param_str = panel_match.group(2).strip()
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', param_str):
                params[m.group(1)] = m.group(2)

            html = None
            if panel_type == "comparison":
                html = generate_comparison(
                    title=params.get("title", ""),
                    left_label=params.get("left_label", "A"),
                    left_amount=params.get("left_amount", ""),
                    right_label=params.get("right_label", "B"),
                    right_amount=params.get("right_amount", ""),
                    gap_amount=params.get("gap_amount", ""),
                    gap_label=params.get("gap_label", ""),
                    left_height=int(params.get("left_height", "400")),
                    right_height=int(params.get("right_height", "200")),
                )
            elif panel_type == "counter":
                html = generate_counter(
                    label=params.get("label", ""),
                    target=int(params.get("target", "0")),
                    unit=params.get("unit", ""),
                    sub=params.get("sub", ""),
                )
            elif panel_type == "bar_chart":
                # bar_chart params: title, then bar1_label,bar1_year,bar1_height,...
                bars = []
                for b in range(1, 5):
                    label = params.get(f"bar{b}_label")
                    if label:
                        bars.append({
                            "label": label,
                            "year": params.get(f"bar{b}_year", ""),
                            "height": int(params.get(f"bar{b}_height", "100")),
                        })
                html = generate_bar_chart(title=params.get("title", ""), bars=bars)

            if html:
                path = str(panels_dir / f"scene_{i:02d}_{panel_type}.html")
                with open(path, "w") as f:
                    f.write(html)
                panels.append({"scene_index": i, "panel_path": path, "type": panel_type})
                print(f"  ✓ scene {i:02d}: {panel_type}（明示指定）")

    print(f"\n  生成: {len(panels)} panels")
    return panels


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_panels.py <episode_dir>")
        sys.exit(1)
    generate(sys.argv[1])
