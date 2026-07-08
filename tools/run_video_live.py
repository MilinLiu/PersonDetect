from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = PROJECT_ROOT / "configs" / "home_gate.yaml"
TEMP_CONFIG = PROJECT_ROOT / ".tmp" / "video_live_config.yaml"


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live dashboard using a local video file as input.")
    parser.add_argument("video", help="Path to the video file.")
    parser.add_argument("--debug", action="store_true", help="Show ROI and count debug overlays.")
    args = parser.parse_args()

    video_path = Path(args.video).expanduser()
    if not video_path.is_absolute():
        video_path = (Path.cwd() / video_path).resolve()
    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 1

    with BASE_CONFIG.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config = deep_merge(
        config,
        {
            "camera": {
                "rtsp_url": str(video_path),
            },
            "capture": {
                "rtsp_stale_frame_sec": 30.0,
                "inference_no_frame_restart_sec": 30.0,
            },
            "display": {
                "show_count_debug": bool(args.debug),
                "show_road_roi": bool(args.debug),
                "show_direction_guides": True,
            },
        },
    )

    TEMP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with TEMP_CONFIG.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    env = os.environ.copy()
    env["MONITOR_CONFIG"] = str(TEMP_CONFIG)
    env.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".tmp"))
    env.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".tmp" / "matplotlib"))

    print(f"[VideoLive] Video: {video_path}")
    print("[VideoLive] Open teacher_remote_viewer.html and connect to ws://localhost:8765")
    return subprocess.call([sys.executable, str(PROJECT_ROOT / "persondetectandfield.py")], cwd=PROJECT_ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
