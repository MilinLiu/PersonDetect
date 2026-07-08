from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = "configs/home_gate.yaml"
DEFAULT_REPLAY_DIR = PROJECT_ROOT / "replay_outputs"


def resolve_project_path(path_value: str | os.PathLike[str]) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def safe_stem(path: Path) -> str:
    cleaned = []
    for char in path.stem:
        if char.isascii() and (char.isalnum() or char in ("-", "_")):
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("_") or "video"


class ReplayClock:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = time.time()

    def __call__(self) -> float:
        with self._lock:
            return self._current

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._current += max(0.0, float(seconds))
            return self._current


class ReplayVideoCapture:
    def __init__(
        self,
        src: Path,
        clock: ReplayClock,
        configured_inference_fps: int,
        every_n: int | None = None,
        max_frames: int | None = None,
    ):
        self.src = str(src)
        self.clock = clock
        self.configured_inference_fps = max(1, int(configured_inference_fps))
        self.max_frames = max_frames
        self._lock = threading.Lock()
        self._cap = cv2.VideoCapture(self.src)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video: {src}")

        source_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.source_fps = source_fps if source_fps > 0 else float(self.configured_inference_fps)
        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.total_source_frames = total_frames if total_frames > 0 else None

        if every_n is None:
            if self.source_fps > self.configured_inference_fps:
                every_n = round(self.source_fps / self.configured_inference_fps)
            else:
                every_n = 1
        self.every_n = max(1, int(every_n))
        self.frame_step_sec = self.every_n / max(1.0, self.source_fps)
        self.source_frame_index = 0
        self.processed_frames = 0
        self.ended = False

    def read(self):
        with self._lock:
            if self.ended:
                return False, None
            if self.max_frames is not None and self.processed_frames >= self.max_frames:
                self.ended = True
                return False, None

            while True:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    self.ended = True
                    return False, None

                self.source_frame_index += 1
                if (self.source_frame_index - 1) % self.every_n != 0:
                    continue

                self.processed_frames += 1
                self.clock.advance(self.frame_step_sec)
                return True, frame

    def request_reconnect(self, reason: str):
        return None

    def stop(self):
        self.ended = True
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def decode_payload_frame(payload: dict):
    image_b64 = payload.get("image")
    if not image_b64:
        return None
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def default_output_path(video_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return DEFAULT_REPLAY_DIR / f"replay_{safe_stem(video_path)}_{timestamp}.mp4"


def default_summary_path(video_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return DEFAULT_REPLAY_DIR / f"replay_{safe_stem(video_path)}_{timestamp}.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Replay a local video through the same YOLO counting pipeline.",
    )
    parser.add_argument("video", help="Input video path.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="YAML config path.")
    parser.add_argument("--mode", choices=["people", "vehicles"], default="people")
    parser.add_argument("--output", help="Annotated MP4 output path.")
    parser.add_argument("--summary", help="JSON summary output path.")
    parser.add_argument("--log-dir", default="replay_outputs/logs", help="Replay CSV log directory.")
    parser.add_argument("--every-n", type=int, help="Process every Nth source frame.")
    parser.add_argument("--max-frames", type=int, help="Stop after N processed frames.")
    parser.add_argument("--debug", action="store_true", help="Force count debug overlay on.")
    parser.add_argument("--no-output", action="store_true", help="Do not write an annotated MP4.")
    parser.add_argument(
        "--real-time",
        action="store_true",
        help="Sleep between frames like the live server. Default runs as fast as possible.",
    )
    parser.add_argument("--progress-every", type=int, default=25)
    return parser.parse_args()


def import_monitor(config_path: str):
    os.environ["MONITOR_CONFIG"] = config_path
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import persondetectandfield as monitor

    return monitor


def configure_replay_logs(monitor, log_dir: Path):
    from server.traffic_logger import ensure_csv_header

    log_dir.mkdir(parents=True, exist_ok=True)
    monitor.TRAFFIC_LOG_DIR = str(log_dir)
    monitor.TRAFFIC_SUMMARY_PATH = str(log_dir / "replay_traffic_summary.csv")
    monitor.TRAFFIC_EVENTS_PATH = str(log_dir / "replay_traffic_events.csv")
    monitor.VEHICLE_SUMMARY_PATH = str(log_dir / "replay_vehicle_summary.csv")
    ensure_csv_header(
        monitor.TRAFFIC_SUMMARY_PATH,
        monitor.SUMMARY_CSV_COLUMNS,
        allow_legacy_summary_migration=True,
    )
    ensure_csv_header(monitor.TRAFFIC_EVENTS_PATH, monitor.EVENT_CSV_COLUMNS)
    ensure_csv_header(monitor.VEHICLE_SUMMARY_PATH, monitor.VEHICLE_SUMMARY_CSV_COLUMNS)


def final_counts(payload: dict) -> dict:
    keys = [
        "analysis_mode",
        "current_count",
        "raw_current_count",
        "held_current_count",
        "tracked_current_count",
        "total_count",
        "detected_total_count",
        "assigned_destination_count",
        "pending_destination_count",
        "interval_count",
        "to_dorm_count",
        "to_starbucks_count",
        "to_sports_count",
        "destination_counts",
        "vehicle_counts",
        "dominant_destination",
        "dominant_vehicle",
        "peak_count",
        "avg_count",
        "mode",
        "brightness",
    ]
    return {key: payload.get(key) for key in keys if key in payload}


def main():
    args = parse_args()
    video_path = resolve_project_path(args.video)
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    monitor = import_monitor(args.config)
    monitor._shutdown_event.clear()
    if args.debug:
        monitor.SHOW_COUNT_DEBUG = True
        monitor.SHOW_ROAD_ROI = True
        monitor.SHOW_DIRECTION_GUIDES = True

    log_dir = resolve_project_path(args.log_dir)
    configure_replay_logs(monitor, log_dir)

    output_path = None if args.no_output else resolve_project_path(args.output) if args.output else default_output_path(video_path)
    summary_path = resolve_project_path(args.summary) if args.summary else default_summary_path(video_path)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    print("[Replay] Loading YOLO model...")
    model = monitor.YOLO(monitor.MODEL_WEIGHTS_PATH)
    model.fuse()
    monitor.warmup_model(model, monitor.YOLO_IMGSZ, monitor.MODEL_DEVICE)

    clock = ReplayClock()
    capture = ReplayVideoCapture(
        video_path,
        clock,
        monitor.INFERENCE_FPS,
        every_n=args.every_n,
        max_frames=args.max_frames,
    )
    appearance_cache = monitor.AppearanceCache()
    inf_thread = monitor.InferenceThread(model, capture, appearance_cache, clock=clock)
    if args.mode == "vehicles":
        inf_thread.set_analysis_mode(monitor.ANALYSIS_MODE_VEHICLES)
    if not args.real_time:
        inf_thread._frame_interval = 0.0

    writer = None
    payload_frames = 0
    last_payload = {}
    last_payload_wall = time.time()
    start_wall = time.time()
    print(
        "[Replay] "
        f"video={video_path} source_fps={capture.source_fps:.2f} "
        f"every_n={capture.every_n} output={output_path or 'disabled'}"
    )

    inf_thread.start()
    try:
        while True:
            try:
                payload = inf_thread.result_q.get(timeout=0.5)
            except queue.Empty:
                if capture.ended and time.time() - last_payload_wall > 0.5:
                    break
                if not inf_thread.is_alive():
                    break
                continue

            last_payload_wall = time.time()
            last_payload = payload
            payload_frames += 1
            frame = decode_payload_frame(payload)
            if output_path is not None and frame is not None:
                if writer is None:
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(
                        str(output_path),
                        fourcc,
                        float(monitor.INFERENCE_FPS),
                        (frame.shape[1], frame.shape[0]),
                    )
                    if not writer.isOpened():
                        raise RuntimeError(f"Cannot open output writer: {output_path}")
                writer.write(frame)

            if args.progress_every > 0 and payload_frames % args.progress_every == 0:
                counts = final_counts(last_payload)
                print(
                    "[Replay] "
                    f"frames={payload_frames} total={counts.get('total_count')} "
                    f"assigned={counts.get('assigned_destination_count')} "
                    f"pending={counts.get('pending_destination_count')}"
                )
    finally:
        inf_thread.stop()
        capture.stop()
        inf_thread.join(timeout=2.0)
        if writer is not None:
            writer.release()

    summary = {
        "video": str(video_path),
        "config": os.environ.get("MONITOR_CONFIG", DEFAULT_CONFIG),
        "analysis_mode": args.mode,
        "debug_overlay": bool(monitor.SHOW_COUNT_DEBUG),
        "source_fps": capture.source_fps,
        "every_n": capture.every_n,
        "source_frames_read": capture.source_frame_index,
        "processed_frames": capture.processed_frames,
        "payload_frames": payload_frames,
        "wall_seconds": round(time.time() - start_wall, 2),
        "output": str(output_path) if output_path is not None else None,
        "summary": str(summary_path),
        "events_csv": monitor.TRAFFIC_EVENTS_PATH,
        "final_counts": final_counts(last_payload),
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("[Replay] Done.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
