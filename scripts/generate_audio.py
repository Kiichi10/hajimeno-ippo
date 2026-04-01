#!/usr/bin/env python3
"""
generate_audio.py — 台本から音声を生成

Usage:
  python generate_audio.py <episode_dir>

episode_dir/script.txt を読み、各行の音声を生成して:
  - episode_dir/audio/line_00.wav, line_01.wav, ...
  - episode_dir/audio/combined.wav (結合済み)
"""

import array
import json
import os
import sys
import urllib.parse
import urllib.request
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def load_config():
    with open(PROJECT_ROOT / "config.json") as f:
        return json.load(f)


def generate(episode_dir: str):
    episode_dir = Path(episode_dir)
    config = load_config()

    script_path = episode_dir / "script.txt"
    if not script_path.exists():
        print(f"ERROR: {script_path} not found")
        return False

    with open(script_path) as f:
        raw_lines = [l.strip() for l in f.readlines() if l.strip()]
    # Extract narration only (before | separator)
    lines = [l.split(" | ")[0].strip() for l in raw_lines]

    audio_dir = episode_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    api_url = config["audio"]["api_url"]
    narrator = config["characters"]["narrator"]
    speaker_id = narrator["speaker_id"]
    speed = narrator["speed_scale"]
    tempo = narrator["tempo_dynamics_scale"]
    gap_sec = config["audio"]["line_gap_sec"]
    sample_rate = config["audio"]["sample_rate"]

    print(f"Generating audio for {len(lines)} lines...")

    for i, text in enumerate(lines):
        # Audio query
        params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
        req = urllib.request.Request(f"{api_url}/audio_query?{params}", method="POST")
        with urllib.request.urlopen(req) as resp:
            query = json.loads(resp.read())

        query["speedScale"] = speed
        query["tempoDynamicsScale"] = tempo

        # Synthesis
        req2 = urllib.request.Request(
            f"{api_url}/synthesis?speaker={speaker_id}",
            data=json.dumps(query).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req2) as resp2:
            wav_data = resp2.read()

        outpath = str(audio_dir / f"line_{i:02d}.wav")
        with open(outpath, "wb") as f:
            f.write(wav_data)

        with wave.open(outpath, "rb") as wf:
            dur = wf.getnframes() / wf.getframerate()
        print(f"  [{i:02d}] {dur:.2f}s - {text[:40]}...")

    # Combine all audio
    combined = array.array('h')
    params = None

    for i in range(len(lines)):
        wav_path = str(audio_dir / f"line_{i:02d}.wav")
        with wave.open(wav_path, "rb") as wf:
            if params is None:
                params = wf.getparams()
            data = wf.readframes(wf.getnframes())
            combined.frombytes(data)
            # Add gap silence
            silence_frames = int(params.framerate * gap_sec)
            combined.extend([0] * silence_frames * params.nchannels)

    combined_path = str(audio_dir / "combined.wav")
    with wave.open(combined_path, "wb") as out:
        out.setparams(params)
        out.writeframes(combined.tobytes())

    with wave.open(combined_path, "rb") as wf:
        total = wf.getnframes() / wf.getframerate()

    print(f"\n✓ Combined audio: {combined_path} ({total:.1f}s)")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_audio.py <episode_dir>")
        sys.exit(1)

    ok = generate(sys.argv[1])
    sys.exit(0 if ok else 1)
