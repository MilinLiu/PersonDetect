from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:
    yaml = None


BASE_DIR = Path(__file__).resolve().parents[1]


DEFAULT_CONFIG: dict[str, Any] = {
    "camera": {
        "scan_base_ip": "192.168.0.",
        "scan_port": 554,
        "rtsp_url": "",
        "rtsp_username": "adminuser",
        "rtsp_password": "00000000",
        "rtsp_path": "stream2",
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8765,
    },
    "video": {
        "inference_fps": 10,
        "output_width": 854,
        "output_height": 480,
        "jpeg_quality": 60,
        "night_brightness_threshold": 85,
        "night_mode_hysteresis": 10,
    },
    "capture": {
        "reconnect_delay": 3.0,
        "fail_threshold": 25,
        "rtsp_open_timeout_ms": 5000,
        "rtsp_read_timeout_ms": 5000,
        "rtsp_stale_frame_sec": 8.0,
        "rtsp_restart_cooldown_sec": 4.0,
        "inference_no_frame_restart_sec": 8.0,
        "capture_buffer_size": 1,
    },
    "model": {
        "weights": "yolo26s.pt",
        "imgsz": 960,
        "conf": 0.32,
    },
    "tracking": {
        "reid_thresh": 0.82,
        "reid_expire_sec": 60,
        "track_max_missing_sec": 12.0,
        "box_hold_sec": 0.0,
        "box_hold_min_hits": 2,
        "track_id_ttl_sec": 30.0,
        "match_iou_thresh": 0.18,
        "match_distance_ratio": 0.16,
        "destination_min_travel_ratio": 0.09,
        "destination_min_track_sec": 0.8,
        "destination_missing_infer_sec": 2.0,
        "destination_history_size": 36,
    },
    "counting": {
        "total_count_on": "roi_entry",
        "allow_missing_destination_infer": False,
        "count_event_overlay_sec": 1.2,
        "visible_exit_min_points": 4,
        "visible_exit_min_track_sec": 0.45,
        "visible_exit_min_travel_ratio": 0.04,
        "visible_exit_min_delta": 0.02,
        "dorm_visible_exit_x": 0.46,
        "dorm_strict_exit_x": 0.38,
        "starbucks_visible_exit_x": 0.56,
        "sports_visible_exit_y": 0.58,
        "visible_exit_zones": {
            "dorm": {
                "x_max": 0.50,
                "y_min": 0.34,
                "y_max": 0.98,
                "dx_max": -0.006,
                "dominant_axis": "x",
                "axis_ratio": 0.20,
            },
            "starbucks": {
                "x_min": 0.50,
                "y_min": 0.34,
                "y_max": 0.98,
                "dx_min": 0.006,
                "dominant_axis": "x",
                "axis_ratio": 0.20,
            },
            "sports": {
                "x_min": 0.12,
                "x_max": 0.82,
                "y_max": 0.64,
                "dy_max": -0.006,
                "dominant_axis": "y",
                "axis_ratio": 0.20,
            },
        },
    },
    "zones": {
        "road_roi": [
            [0.02, 0.98],
            [0.19, 0.36],
            [0.72, 0.36],
            [0.98, 0.98],
        ],
        "road_roi_margin_ratio": 0.05,
        "forward_walkway_zones": [
            [0.00, 0.36, 0.24, 0.84],
            [0.58, 0.38, 0.99, 0.84],
        ],
        "exits": {
            "dorm": [[0.02, 0.98], [0.19, 0.36]],
            "sports": [[0.19, 0.36], [0.72, 0.36]],
            "starbucks": [[0.72, 0.36], [0.98, 0.98]],
        },
    },
    "display": {
        "show_road_roi": False,
        "show_direction_guides": True,
        "show_person_labels": False,
        "show_count_debug": False,
    },
    "destinations": {
        "labels": {
            "dorm": "Dorm",
            "sports": "Sports",
            "starbucks": "Star Gate",
        },
        "colors": {
            "dorm": [45, 212, 191],
            "sports": [245, 158, 11],
            "starbucks": [56, 189, 248],
        },
    },
    "alert": {
        "current_count_threshold": 6,
    },
    "logging": {
        "interval_minutes": 5,
        "history_dashboard_points": 96,
        "history_max_points": 2016,
        "traffic_log_dir": "traffic_logs",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config_path = Path(path or os.environ.get("MONITOR_CONFIG", "configs/home_gate.yaml"))
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path

    defaults = copy.deepcopy(DEFAULT_CONFIG)

    if yaml is None:
        print("[Config] PyYAML is not installed; using built-in defaults.")
        return defaults

    if not config_path.exists():
        print(f"[Config] {config_path} not found; using built-in defaults.")
        return defaults

    try:
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except Exception as exc:
        print(f"[Config] Failed to read {config_path}: {exc}; using built-in defaults.")
        return defaults

    if not isinstance(loaded, dict):
        print(f"[Config] {config_path} must contain a mapping; using built-in defaults.")
        return defaults

    return _deep_merge(defaults, loaded)
