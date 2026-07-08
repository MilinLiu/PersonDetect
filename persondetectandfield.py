"""
School Safety Surveillance Server
"""

import cv2
import asyncio
import websockets
import base64
import time
import threading
import os
import signal
import numpy as np
from collections import deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TMP_DIR = os.path.join(BASE_DIR, ".tmp")
LOCAL_MPL_DIR = os.path.join(BASE_DIR, ".matplotlib")
os.makedirs(LOCAL_TMP_DIR, exist_ok=True)
os.makedirs(LOCAL_MPL_DIR, exist_ok=True)
os.environ.setdefault("TMP", LOCAL_TMP_DIR)
os.environ.setdefault("TEMP", LOCAL_TMP_DIR)
os.environ.setdefault("YOLO_CONFIG_DIR", BASE_DIR)
os.environ.setdefault("MPLCONFIGDIR", LOCAL_MPL_DIR)

from ultralytics import YOLO
import torch
import queue as stdlib_queue
from analyzers.geometry import (
    average_path_norm,
    box_center,
    box_iou,
    box_zone_hit,
    merge_feature,
    point_to_segment_distance,
    segments_intersect,
    is_forward_walkway_norm,
)
from analyzers.visualization import draw_person_annotations, draw_vehicle_annotations
from analyzers.vehicle_flow import VehicleFlowCounter
from core.appearance import AppearanceCache
from core.camera_source import VideoCaptureThreading
from core.config import load_config
from core.image_utils import enhance_night_frame, estimate_brightness
from core.model_utils import warmup_model
from core.runtime import cleanup_resources, find_camera_ip, preflight_check
from server.traffic_logger import append_csv_row, traffic_logger
from server.websocket_server import video_ai_stream

CONFIG = load_config()


def _project_path(path_value: str) -> str:
    path_text = str(path_value or "")
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(BASE_DIR, path_text)


def _points(points):
    return [tuple(point) for point in points]


def _exit_lines(exits):
    return {
        name: (tuple(points[0]), tuple(points[1]))
        for name, points in exits.items()
    }


def _color_map(colors):
    return {name: tuple(value) for name, value in colors.items()}


_CAMERA_CONFIG = CONFIG["camera"]
_SERVER_CONFIG = CONFIG["server"]
_VIDEO_CONFIG = CONFIG["video"]
_CAPTURE_CONFIG = CONFIG["capture"]
_MODEL_CONFIG = CONFIG["model"]
_TRACKING_CONFIG = CONFIG["tracking"]
_COUNTING_CONFIG = CONFIG["counting"]
_ZONES_CONFIG = CONFIG["zones"]
_DISPLAY_CONFIG = CONFIG["display"]
_DESTINATION_CONFIG = CONFIG["destinations"]
_ALERT_CONFIG = CONFIG["alert"]
_LOGGING_CONFIG = CONFIG["logging"]
# ──────────────────────────────────────────────────────────────────────────────
# RTSP 環境參數
# ──────────────────────────────────────────────────────────────────────────────
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp"
    "|stimeout;4000000"
    "|timeout;4000000"
)

# ──────────────────────────────────────────────────────────────────────────────
# 全域常數
# ──────────────────────────────────────────────────────────────────────────────
CAMERA_SCAN_BASE_IP = str(_CAMERA_CONFIG["scan_base_ip"])
CAMERA_SCAN_PORT = int(_CAMERA_CONFIG["scan_port"])
CAMERA_RTSP_URL = str(_CAMERA_CONFIG.get("rtsp_url") or "").strip()
CAMERA_RTSP_USERNAME = str(_CAMERA_CONFIG["rtsp_username"])
CAMERA_RTSP_PASSWORD = str(_CAMERA_CONFIG["rtsp_password"])
CAMERA_RTSP_PATH = str(_CAMERA_CONFIG["rtsp_path"]).strip("/")
SERVER_HOST = str(_SERVER_CONFIG["host"])
SERVER_PORT = int(_SERVER_CONFIG["port"])
MODEL_WEIGHTS_PATH = _project_path(_MODEL_CONFIG["weights"])
INFERENCE_FPS   = int(_VIDEO_CONFIG["inference_fps"])
OUTPUT_WIDTH    = int(_VIDEO_CONFIG["output_width"])
OUTPUT_HEIGHT   = int(_VIDEO_CONFIG["output_height"])
JPEG_QUALITY    = int(_VIDEO_CONFIG["jpeg_quality"])
RECONNECT_DELAY = float(_CAPTURE_CONFIG["reconnect_delay"])
FAIL_THRESHOLD  = int(_CAPTURE_CONFIG["fail_threshold"])
RTSP_OPEN_TIMEOUT_MS = int(_CAPTURE_CONFIG["rtsp_open_timeout_ms"])
RTSP_READ_TIMEOUT_MS = int(_CAPTURE_CONFIG["rtsp_read_timeout_ms"])
RTSP_STALE_FRAME_SEC = float(_CAPTURE_CONFIG["rtsp_stale_frame_sec"])
RTSP_RESTART_COOLDOWN_SEC = float(_CAPTURE_CONFIG["rtsp_restart_cooldown_sec"])
INFERENCE_NO_FRAME_RESTART_SEC = float(_CAPTURE_CONFIG["inference_no_frame_restart_sec"])
CAPTURE_BUFFER_SIZE = int(_CAPTURE_CONFIG["capture_buffer_size"])
BYTETRACK_CONF  = float(_MODEL_CONFIG["conf"])
YOLO_IMGSZ      = int(_MODEL_CONFIG["imgsz"])
TRACKER_CONFIG  = str(_MODEL_CONFIG.get("tracker", "bytetrack.yaml"))
REID_THRESH     = float(_TRACKING_CONFIG["reid_thresh"])
REID_EXPIRE_SEC = float(_TRACKING_CONFIG["reid_expire_sec"])
TRACK_MAX_MISSING_SEC = float(_TRACKING_CONFIG["track_max_missing_sec"])
BOX_HOLD_SEC = float(_TRACKING_CONFIG.get("box_hold_sec", 1.0))
BOX_HOLD_MIN_HITS = int(_TRACKING_CONFIG.get("box_hold_min_hits", 2))
TRACK_ID_TTL_SEC = float(_TRACKING_CONFIG["track_id_ttl_sec"])
MATCH_IOU_THRESH = float(_TRACKING_CONFIG["match_iou_thresh"])
MATCH_DISTANCE_RATIO = float(_TRACKING_CONFIG["match_distance_ratio"])
# Re-association 防呆：短暫遮擋才允許純幾何接續；間隔較久必須外觀相似才併身份，
# 避免「不同人走到同一位置」被吸收成同一個 ID 而漏記。
REASSOC_RECENT_SEC = float(_TRACKING_CONFIG.get("reassoc_recent_sec", 1.5))
REASSOC_APPEARANCE_MIN = float(_TRACKING_CONFIG.get("reassoc_appearance_min", REID_THRESH))
REASSOC_VERY_NEAR_RATIO = float(_TRACKING_CONFIG.get("reassoc_very_near_ratio", 0.5))
ROAD_ROI_NORM = _points(_ZONES_CONFIG["road_roi"])
ROAD_ROI_MARGIN_RATIO = float(_ZONES_CONFIG["road_roi_margin_ratio"])
FORWARD_WALKWAY_ZONES_NORM = _points(_ZONES_CONFIG["forward_walkway_zones"])
EXIT_LINES_NORM = _exit_lines(_ZONES_CONFIG["exits"])
DESTINATION_LABELS = dict(_DESTINATION_CONFIG["labels"])
DESTINATION_COLORS = _color_map(_DESTINATION_CONFIG["colors"])
DESTINATION_MIN_TRAVEL_RATIO = float(_TRACKING_CONFIG["destination_min_travel_ratio"])
DESTINATION_MIN_TRACK_SEC = float(_TRACKING_CONFIG["destination_min_track_sec"])
DESTINATION_MISSING_INFER_SEC = float(_TRACKING_CONFIG["destination_missing_infer_sec"])
DESTINATION_HISTORY_SIZE = int(_TRACKING_CONFIG["destination_history_size"])
TOTAL_COUNT_ON = str(_COUNTING_CONFIG["total_count_on"])
ALLOW_MISSING_DESTINATION_INFER = bool(_COUNTING_CONFIG["allow_missing_destination_infer"])
COUNT_EVENT_OVERLAY_SEC = float(_COUNTING_CONFIG["count_event_overlay_sec"])
VISIBLE_EXIT_MIN_POINTS = int(_COUNTING_CONFIG["visible_exit_min_points"])
VISIBLE_EXIT_MIN_TRACK_SEC = float(_COUNTING_CONFIG["visible_exit_min_track_sec"])
VISIBLE_EXIT_MIN_TRAVEL_RATIO = float(_COUNTING_CONFIG["visible_exit_min_travel_ratio"])
VISIBLE_EXIT_MIN_DELTA = float(_COUNTING_CONFIG["visible_exit_min_delta"])
DORM_VISIBLE_EXIT_X = float(_COUNTING_CONFIG["dorm_visible_exit_x"])
DORM_STRICT_EXIT_X = float(_COUNTING_CONFIG["dorm_strict_exit_x"])
STARBUCKS_VISIBLE_EXIT_X = float(_COUNTING_CONFIG["starbucks_visible_exit_x"])
SPORTS_VISIBLE_EXIT_Y = float(_COUNTING_CONFIG["sports_visible_exit_y"])
VISIBLE_EXIT_ZONES = dict(_COUNTING_CONFIG.get("visible_exit_zones") or {})
DOUBLE_ZONE_COUNTING = bool(_COUNTING_CONFIG.get("double_zone_counting", True))
DOUBLE_ZONE_ENTRY_ZONES = list(_COUNTING_CONFIG.get("double_zone_entry_zones") or [])
DOUBLE_ZONE_EXIT_ZONES = dict(_COUNTING_CONFIG.get("double_zone_exit_zones") or {})
DOUBLE_ZONE_EXIT_HITS = int(_COUNTING_CONFIG.get("double_zone_exit_hits", 2))
DOUBLE_ZONE_MIN_POINTS = int(_COUNTING_CONFIG.get("double_zone_min_points", 3))
DOUBLE_ZONE_MIN_TRACK_SEC = float(_COUNTING_CONFIG.get("double_zone_min_track_sec", 0.35))
SHOW_ROAD_ROI = bool(_DISPLAY_CONFIG["show_road_roi"])
SHOW_DIRECTION_GUIDES = bool(_DISPLAY_CONFIG["show_direction_guides"])
SHOW_COUNT_DEBUG = bool(_DISPLAY_CONFIG.get("show_count_debug", False))
NIGHT_BRIGHTNESS_THRESHOLD = float(_VIDEO_CONFIG["night_brightness_threshold"])
NIGHT_MODE_HYSTERESIS = float(_VIDEO_CONFIG["night_mode_hysteresis"])
ALERT_THRESHOLD = int(_ALERT_CONFIG["current_count_threshold"])
AVG_WINDOW_SEC = 60
SHOW_PERSON_LABELS = bool(_DISPLAY_CONFIG["show_person_labels"])
MODEL_DEVICE = 0 if torch.cuda.is_available() else "cpu"
ANALYSIS_MODE_PEOPLE = "people"
ANALYSIS_MODE_VEHICLES = "vehicles"
DEFAULT_ANALYSIS_MODE = ANALYSIS_MODE_PEOPLE
VEHICLE_CLASS_IDS = [2, 3, 5, 7]
VEHICLE_CLASS_LABELS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
VEHICLE_DISPLAY_LABELS = {
    "car": "Car",
    "motorcycle": "Motorcycle",
    "bus": "Bus",
    "truck": "Truck",
}
VEHICLE_COLORS = {
    "car": (56, 189, 248),
    "motorcycle": (45, 212, 191),
    "bus": (245, 158, 11),
    "truck": (239, 68, 68),
}
traffic_history = []  # 存儲給前端畫圖用的歷史資料
vehicle_history = []
INTERVAL_MINUTES = int(_LOGGING_CONFIG["interval_minutes"])  # 設定每幾分鐘記錄一次
HISTORY_DASHBOARD_POINTS = int(_LOGGING_CONFIG["history_dashboard_points"])
HISTORY_MAX_POINTS = int(_LOGGING_CONFIG["history_max_points"])
TRAFFIC_LOG_DIR = _project_path(_LOGGING_CONFIG["traffic_log_dir"])
os.makedirs(TRAFFIC_LOG_DIR, exist_ok=True)
SUMMARY_CSV_COLUMNS = [
    "時間",
    "往宿舍",
    "往星巴門",
    "往體育門",
    "當下時段經過人數",
    "最高人流時段",
    "最高時段人數",
]
VEHICLE_SUMMARY_CSV_COLUMNS = [
    "時間",
    "汽車",
    "機車",
    "當下時段經過車輛",
]
EVENT_CSV_COLUMNS = [
    "Timestamp",
    "Person_ID",
    "Destination",
    "Assigned_Destination_Count",
    "Pending_Destination_Count",
    "To_Dorm_Count",
    "To_Starbucks_Gate_Count",
    "To_Sports_Gate_Count",
    "Total_Count",
]
TRAFFIC_SUMMARY_PATH = os.path.join(TRAFFIC_LOG_DIR, "traffic_summary.csv")
TRAFFIC_EVENTS_PATH = os.path.join(TRAFFIC_LOG_DIR, "traffic_events.csv")
VEHICLE_SUMMARY_PATH = os.path.join(TRAFFIC_LOG_DIR, "vehicle_summary.csv")
# 全域引用
_vcap           = None
_inf_thread     = None
_server         = None
_shutdown_event = threading.Event()
_main_task      = None   # ← 保存 main task 讓 signal handler 能取消它

# ══════════════════════════════════════════════════════════════════════════════
# 1. 推理執行緒
# ══════════════════════════════════════════════════════════════════════════════
class InferenceThread(threading.Thread):
    def __init__(self, model, vcap: VideoCaptureThreading,
                 appearance_cache: AppearanceCache,
                 clock=None):
        super().__init__(daemon=True, name="InferenceThread")
        self.model = model
        self.vcap = vcap
        self.cache = appearance_cache
        self._clock = clock or time.time
        self.result_q: stdlib_queue.Queue = stdlib_queue.Queue(maxsize=2)
        self._running = True
        self.detected_person_count = 0
        self.roi_person_count = 0
        self.to_dorm_count = 0
        self.to_starbucks_count = 0
        self.to_sports_count = 0
        self.peak_count = 0
        self.avg_count = 0.0
        self.interval_start_roi_count = 0
        self.interval_start_counts = {"dorm": 0, "starbucks": 0, "sports": 0}
        self._next_person_id = 1
        self._people: dict[int, dict] = {}
        self._raw_to_person: dict[int, int] = {}
        self._raw_seen_at: dict[int, float] = {}
        self._current_samples = deque()
        self._mode = "day"
        self._analysis_mode = DEFAULT_ANALYSIS_MODE
        self._mode_lock = threading.Lock()
        self._tracker_reset_requested = False
        self.vehicle_flow = VehicleFlowCounter(
            VEHICLE_CLASS_LABELS,
            VEHICLE_DISPLAY_LABELS,
            TRACK_ID_TTL_SEC,
            AVG_WINDOW_SEC,
        )
        self.last_payload = {}
        self._frame_interval = 1.0 / INFERENCE_FPS

    def _now(self) -> float:
        return float(self._clock())

    @staticmethod
    def _normalize_analysis_mode(mode: str | None) -> str:
        if mode == ANALYSIS_MODE_VEHICLES:
            return ANALYSIS_MODE_VEHICLES
        return ANALYSIS_MODE_PEOPLE

    def set_analysis_mode(self, mode: str | None):
        next_mode = self._normalize_analysis_mode(mode)
        with self._mode_lock:
            if next_mode != self._analysis_mode:
                self._analysis_mode = next_mode
                self._tracker_reset_requested = True
                print(f"[Mode] Switched to {next_mode}")

    def analysis_mode(self) -> str:
        with self._mode_lock:
            return self._analysis_mode

    def consume_tracker_reset(self) -> bool:
        with self._mode_lock:
            reset = self._tracker_reset_requested
            self._tracker_reset_requested = False
            return reset

    @property
    def vehicle_total_count(self):
        return self.vehicle_flow.total_count

    @property
    def vehicle_interval_start_total(self):
        return self.vehicle_flow.interval_start_total

    @vehicle_interval_start_total.setter
    def vehicle_interval_start_total(self, value):
        self.vehicle_flow.interval_start_total = value

    @property
    def vehicle_interval_start_counts(self):
        return self.vehicle_flow.interval_start_counts

    @vehicle_interval_start_counts.setter
    def vehicle_interval_start_counts(self, value):
        self.vehicle_flow.interval_start_counts = value

    @property
    def vehicle_peak_count(self):
        return self.vehicle_flow.peak_count

    @property
    def vehicle_avg_count(self):
        return self.vehicle_flow.avg_count

    def _crop_person(self, frame: np.ndarray, box):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = map(int, box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _purge_stale(self, now: float):
        for raw_id, last_seen in list(self._raw_seen_at.items()):
            if now - last_seen > TRACK_ID_TTL_SEC:
                self._raw_seen_at.pop(raw_id, None)
                self._raw_to_person.pop(raw_id, None)

        for person_id, state in list(self._people.items()):
            if ALLOW_MISSING_DESTINATION_INFER and now - state["last_seen"] > DESTINATION_MISSING_INFER_SEC:
                destination = self._infer_destination_on_missing(state, now)
                if destination is not None:
                    self._finalize_destination(state, person_id, destination, now)
            if now - state["last_seen"] > REID_EXPIRE_SEC:
                self._people.pop(person_id, None)

    def _match_existing_person(self, box, center, feature, frame_shape, now, visible_ids):
        """把一個新的偵測接回既有身份。

        規則式、分時間窗，避免舊版「距離夠近就併」造成不同人被吸收成同一 ID：
        - 短暫遺失（age <= REASSOC_RECENT_SEC）：視為遮擋/閃爍，IoU 有重疊或
          質心非常接近即可接續（維持同一 ID，避免同一人被重複計數）。
        - 較久的間隔：必須「外觀相似」且「空間合理」才可接續，單純位置接近不算，
          以免後面走到同位置的另一個人繼承前一個人的 ID 而漏記人數。
        """
        h, w = frame_shape[:2]
        max_distance = ((h * h + w * w) ** 0.5) * MATCH_DISTANCE_RATIO
        very_near_distance = max_distance * REASSOC_VERY_NEAR_RATIO
        best_person_id = None
        best_key = None

        for person_id, state in self._people.items():
            if person_id in visible_ids:
                continue

            age = now - state["last_seen"]
            if age > TRACK_MAX_MISSING_SEC:
                continue

            iou = box_iou(box, state["last_box"])
            distance = float(np.linalg.norm(np.array(center) - np.array(state["last_center"])))
            similarity = self.cache.similarity(feature, state.get("feature"))
            near = distance <= max_distance

            matched = False
            if age <= REASSOC_RECENT_SEC:
                # 剛剛才遺失：幾何連續性足以判定是同一人。
                if iou >= MATCH_IOU_THRESH or distance <= very_near_distance:
                    matched = True
            if not matched and near and similarity >= REASSOC_APPEARANCE_MIN:
                # 間隔較久：外觀一致 + 空間合理才接續。
                matched = True

            if not matched:
                continue

            # 排序偏好：先看 IoU，再看外觀相似度，最後看距離（越近越好）。
            key = (round(iou, 4), round(similarity, 4), -distance)
            if best_key is None or key > best_key:
                best_key = key
                best_person_id = person_id

        return best_person_id

    def _exit_for_transition(self, last_inside_norm, current_norm):
        for destination, segment in EXIT_LINES_NORM.items():
            if segments_intersect(last_inside_norm, current_norm, segment[0], segment[1]):
                return destination
        return None

    def _nearest_exit(self, point_norm):
        distances = {
            destination: point_to_segment_distance(point_norm, segment[0], segment[1])
            for destination, segment in EXIT_LINES_NORM.items()
        }
        destination, distance = min(distances.items(), key=lambda item: item[1])
        return destination if distance <= 0.14 else None

    def _exit_for_path(self, points):
        for prev, curr in zip(points, points[1:]):
            _, _, prev_norm, prev_in_road = prev
            _, _, curr_norm, curr_in_road = curr
            if prev_in_road and not curr_in_road:
                destination = self._exit_for_transition(prev_norm, curr_norm)
                if destination is not None:
                    return destination
        return None

    def _record_path_point(self, state, box, frame_shape, now):
        foot, foot_norm, in_road, in_forward_walkway, road_norm = box_zone_hit(
            box,
            frame_shape,
            ROAD_ROI_NORM,
            ROAD_ROI_MARGIN_RATIO,
            FORWARD_WALKWAY_ZONES_NORM,
        )
        nx, ny = foot_norm

        # Keep the configured walkway zones as a softer buffer outside the road ROI.
        in_forward_walkway = in_forward_walkway or is_forward_walkway_norm((nx, ny), FORWARD_WALKWAY_ZONES_NORM)
        in_visible_exit_zone = self._point_in_visible_exit_zone((nx, ny))
        if in_forward_walkway and not in_road:
            self._mark_roi_person(state, now)
            state["path"].append((now, foot, (nx, ny), in_road))
            self._remember_double_zone_entry(state, (nx, ny), now)
            if state.get("was_inside_roi"):
                exit_destination = self._exit_for_transition(state.get("last_inside_norm"), (nx, ny))
                if exit_destination is not None:
                    return exit_destination
            return self._classify_zone_exit(state, (nx, ny), now)

        if state.get("was_inside_roi") and not in_road:
            state["path"].append((now, foot, (nx, ny), in_road))
            self._remember_double_zone_entry(state, (nx, ny), now)
            destination = self._exit_for_transition(state.get("last_inside_norm"), (nx, ny))
            if destination is not None:
                return destination
            return self._classify_zone_exit(state, (nx, ny), now)

        if not in_road and not in_forward_walkway:
            if in_visible_exit_zone:
                self._mark_roi_person(state, now)
                state["path"].append((now, foot, (nx, ny), in_road))
                self._remember_double_zone_entry(state, (nx, ny), now)
                return self._classify_zone_exit(state, (nx, ny), now)
            return None

        state["path"].append((now, foot, (nx, ny), in_road))
        self._remember_double_zone_entry(state, (nx, ny), now)
        if in_road:
            self._mark_roi_person(state, now)
            state["was_inside_roi"] = True
            state["last_inside_norm"] = road_norm
            state["last_inside_ts"] = now
        elif in_forward_walkway:
            return self._classify_zone_exit(state, (nx, ny), now)
        return self._classify_zone_exit(state, (nx, ny), now)

    def _mark_roi_person(self, state, now):
        if state.get("roi_counted"):
            return
        state["roi_counted"] = True
        state["roi_entered_ts"] = now
        if TOTAL_COUNT_ON == "roi_entry":
            self._mark_total_person(state, None, "roi_entry", now)

    def _mark_total_person(self, state, person_id, destination: str | None, now: float):
        if state.get("total_counted"):
            return
        state["total_counted"] = True
        state["total_counted_ts"] = now
        self.roi_person_count += 1
        state["display_count"] = self.roi_person_count
        state["count_event"] = {
            "ts": now,
            "person_id": person_id,
            "destination": destination,
            "total": self.roi_person_count,
        }

    @staticmethod
    def _point_matches_rect(point_norm, rect) -> bool:
        if isinstance(rect, dict):
            return InferenceThread._point_matches_exit_rule(point_norm, rect)

        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            return False

        x, y = point_norm
        x1, y1, x2, y2 = (float(value) for value in rect)
        return min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)

    def _point_in_double_zone_entry(self, point_norm) -> bool:
        return any(self._point_matches_rect(point_norm, zone) for zone in DOUBLE_ZONE_ENTRY_ZONES)

    def _double_zone_exit_destination(self, point_norm):
        for destination, rule in DOUBLE_ZONE_EXIT_ZONES.items():
            if self._point_matches_rect(point_norm, rule):
                return destination
        return None

    def _remember_double_zone_entry(self, state, point_norm, now: float):
        if not DOUBLE_ZONE_COUNTING or not DOUBLE_ZONE_ENTRY_ZONES:
            return
        if not self._point_in_double_zone_entry(point_norm):
            return

        state["double_zone_entry_seen"] = True
        if state.get("double_zone_entry_ts") is None:
            state["double_zone_entry_ts"] = now
        state["double_zone_entry_last_ts"] = now

    def _classify_double_zone_exit(self, state, point_norm, now: float):
        if (
            not DOUBLE_ZONE_COUNTING
            or not DOUBLE_ZONE_EXIT_ZONES
            or state.get("destination_counted")
            or not state.get("roi_counted")
            or not state.get("double_zone_entry_seen")
        ):
            return None

        points = state.get("path", ())
        if len(points) < DOUBLE_ZONE_MIN_POINTS:
            return None

        entry_ts = state.get("double_zone_entry_ts") or state.get("roi_entered_ts") or points[0][0]
        if now - float(entry_ts) < DOUBLE_ZONE_MIN_TRACK_SEC:
            return None

        destination = self._double_zone_exit_destination(point_norm)
        if destination is None:
            state["double_zone_exit_candidate"] = None
            state["double_zone_exit_hits"] = 0
            return None

        if state.get("double_zone_exit_candidate") != destination:
            state["double_zone_exit_candidate"] = destination
            state["double_zone_exit_hits"] = 1
        else:
            state["double_zone_exit_hits"] = int(state.get("double_zone_exit_hits", 0)) + 1

        if int(state.get("double_zone_exit_hits", 0)) < DOUBLE_ZONE_EXIT_HITS:
            return None
        return destination

    def _classify_zone_exit(self, state, point_norm, now: float):
        destination = self._classify_double_zone_exit(state, point_norm, now)
        if destination is not None:
            return destination

        if DOUBLE_ZONE_COUNTING and DOUBLE_ZONE_ENTRY_ZONES and DOUBLE_ZONE_EXIT_ZONES:
            return None
        return self._classify_visible_exit(state)

    @staticmethod
    def _point_matches_exit_rule(point_norm, rule: dict) -> bool:
        x, y = point_norm
        if "x_min" in rule and x < float(rule["x_min"]):
            return False
        if "x_max" in rule and x > float(rule["x_max"]):
            return False
        if "y_min" in rule and y < float(rule["y_min"]):
            return False
        if "y_max" in rule and y > float(rule["y_max"]):
            return False
        return True

    def _point_in_visible_exit_zone(self, point_norm) -> bool:
        return any(
            self._point_matches_exit_rule(point_norm, rule)
            for rule in VISIBLE_EXIT_ZONES.values()
        )

    def _visible_exit_rule_matches_motion(self, rule: dict, dx: float, dy: float) -> bool:
        if "dx_min" in rule and dx < float(rule["dx_min"]):
            return False
        if "dx_max" in rule and dx > float(rule["dx_max"]):
            return False
        if "dy_min" in rule and dy < float(rule["dy_min"]):
            return False
        if "dy_max" in rule and dy > float(rule["dy_max"]):
            return False

        axis = rule.get("dominant_axis")
        axis_ratio = float(rule.get("axis_ratio", 0.0))
        if axis == "x" and abs(dx) < abs(dy) * axis_ratio:
            return False
        if axis == "y" and abs(dy) < abs(dx) * axis_ratio:
            return False
        return True

    def _classify_visible_exit_by_rules(self, end_norm, dx: float, dy: float):
        for destination, rule in VISIBLE_EXIT_ZONES.items():
            if not self._point_matches_exit_rule(end_norm, rule):
                continue
            if self._visible_exit_rule_matches_motion(rule, dx, dy):
                return destination
        return None

    def _classify_visible_exit(self, state):
        if state.get("destination_counted") or not state.get("roi_counted"):
            return None

        points = list(state.get("path", ()))
        if len(points) < VISIBLE_EXIT_MIN_POINTS:
            return None

        candidates = [points]
        recent_points = points[-6:]
        if recent_points != points and len(recent_points) >= VISIBLE_EXIT_MIN_POINTS:
            candidates.insert(0, recent_points)

        for sample in candidates:
            destination = self._classify_visible_exit_sample(sample)
            if destination is not None:
                return destination
        return None

    def _classify_visible_exit_sample(self, points):
        if len(points) < VISIBLE_EXIT_MIN_POINTS:
            return None

        start_ts = points[0][0]
        end_ts = points[-1][0]
        if end_ts - start_ts < VISIBLE_EXIT_MIN_TRACK_SEC:
            return None

        sample_size = min(4, max(1, len(points) // 3))
        start_norm = average_path_norm(points[:sample_size])
        end_norm = average_path_norm(points[-sample_size:])
        if start_norm is None or end_norm is None:
            return None

        sx, sy = start_norm
        ex, ey = end_norm
        dx = ex - sx
        dy = ey - sy
        travel = float((dx * dx + dy * dy) ** 0.5)
        if travel < VISIBLE_EXIT_MIN_TRAVEL_RATIO:
            return None

        abs_dx = abs(dx)
        abs_dy = abs(dy)
        rule_destination = self._classify_visible_exit_by_rules((ex, ey), dx, dy)
        if rule_destination is not None:
            return rule_destination

        if ex <= DORM_VISIBLE_EXIT_X and dx <= -VISIBLE_EXIT_MIN_DELTA and abs_dx >= abs_dy * 0.25:
            return "dorm"
        if ex <= DORM_STRICT_EXIT_X and dx <= -VISIBLE_EXIT_MIN_DELTA:
            return "dorm"
        if ex >= STARBUCKS_VISIBLE_EXIT_X and dx >= VISIBLE_EXIT_MIN_DELTA and abs_dx >= abs_dy * 0.25:
            return "starbucks"
        if ey <= SPORTS_VISIBLE_EXIT_Y and dy <= -VISIBLE_EXIT_MIN_DELTA and (abs_dy >= abs_dx * 0.25 or ey < 0.50):
            return "sports"
        return None

    def _classify_destination_from_path(self, state):
        if state.get("destination_counted"):
            return None

        points = list(state.get("path", ()))
        if len(points) < 2:
            return None

        exit_destination = self._exit_for_path(points)
        if exit_destination is not None:
            return exit_destination

        start_ts = points[0][0]
        end_ts = points[-1][0]
        if end_ts - start_ts < DESTINATION_MIN_TRACK_SEC:
            return None

        sample_size = min(4, max(1, len(points) // 3))
        start_norm = average_path_norm(points[:sample_size])
        end_norm = average_path_norm(points[-sample_size:])
        if start_norm is None or end_norm is None:
            return None

        sx, sy = start_norm
        ex, ey = end_norm
        dx = ex - sx
        dy = ey - sy
        travel = float((dx * dx + dy * dy) ** 0.5)
        if travel < DESTINATION_MIN_TRAVEL_RATIO:
            return None

        abs_dx = abs(dx)
        abs_dy = abs(dy)
        # 畫面上方是路口往前，包含右側人行道往前走的情境。
        if dy < -0.045 and (abs_dy >= abs_dx * 0.55 or ey < 0.56):
            return "sports"
        if dx < -0.055 and abs_dx >= abs_dy * 0.55:
            return "dorm"
        if dx > 0.055 and abs_dx >= abs_dy * 0.55:
            return "starbucks"
        # 如果方向很斜，改看落點靠近哪個出口。
        if ey < 0.55:
            return "sports"
        if ex < 0.32:
            return "dorm"
        if ex > 0.68:
            return "starbucks"
        return None

    def _infer_destination_on_missing(self, state, now):
        if state.get("destination_counted"):
            return None
        points = list(state.get("path", ()))
        if len(points) < 2:
            return None
        last_ts, _, last_norm, _ = points[-1]
        if now - last_ts < DESTINATION_MISSING_INFER_SEC:
            return None
        destination = self._classify_destination_from_path(state)
        if destination is not None:
            return destination
        if state.get("was_inside_roi"):
            return self._nearest_exit(last_norm)
        return None

    def _add_destination_count(self, destination: str):
        if destination == "dorm":
            self.to_dorm_count += 1
        elif destination == "starbucks":
            self.to_starbucks_count += 1
        elif destination == "sports":
            self.to_sports_count += 1

    def _finalize_destination(self, state, person_id: int, destination: str, now: float):
        if state.get("destination_counted"):
            return
        state["destination"] = destination
        state["destination_counted"] = True
        self._mark_total_person(state, person_id, destination, now)
        self._add_destination_count(destination)
        append_csv_row(
            TRAFFIC_EVENTS_PATH,
            EVENT_CSV_COLUMNS,
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                person_id,
                destination,
                self.destination_total(),
                self.pending_destination_count(),
                self.to_dorm_count,
                self.to_starbucks_count,
                self.to_sports_count,
                self.roi_person_count,
            ],
        )

    def destination_counts(self):
        return {
            "dorm": self.to_dorm_count,
            "starbucks": self.to_starbucks_count,
            "sports": self.to_sports_count,
        }

    def destination_total(self):
        return sum(self.destination_counts().values())

    def pending_destination_count(self):
        if TOTAL_COUNT_ON == "exit_crossing":
            return sum(
                1
                for state in self._people.values()
                if state.get("roi_counted") and not state.get("destination_counted")
            )
        return max(0, self.roi_person_count - self.destination_total())

    def count_debug_snapshot(
        self,
        current_count: int,
        destination_counts: dict | None = None,
        destination_total: int | None = None,
        pending_count: int | None = None,
    ) -> dict:
        destination_counts = destination_counts or self.destination_counts()
        if destination_total is None:
            destination_total = sum(destination_counts.values())
        if pending_count is None:
            pending_count = self.pending_destination_count()
        tracked_pending = sum(
            1
            for state in self._people.values()
            if state.get("roi_counted") and not state.get("destination_counted")
        )
        return {
            "total_count_on": TOTAL_COUNT_ON,
            "allow_missing_destination_infer": ALLOW_MISSING_DESTINATION_INFER,
            "current_count": current_count,
            "detected_total_count": self.detected_person_count,
            "total_count": self.roi_person_count,
            "assigned_destination_count": destination_total,
            "pending_destination_count": pending_count,
            "tracked_pending_count": tracked_pending,
            "active_tracks": len(self._people),
            "visible_tracks": current_count,
            "destination_counts": destination_counts,
            "visible_exit_min_points": VISIBLE_EXIT_MIN_POINTS,
            "visible_exit_min_track_sec": VISIBLE_EXIT_MIN_TRACK_SEC,
            "visible_exit_min_travel_ratio": VISIBLE_EXIT_MIN_TRAVEL_RATIO,
            "visible_exit_min_delta": VISIBLE_EXIT_MIN_DELTA,
            "double_zone_counting": DOUBLE_ZONE_COUNTING,
            "double_zone_entry_zones": DOUBLE_ZONE_ENTRY_ZONES,
            "double_zone_exit_zones": DOUBLE_ZONE_EXIT_ZONES,
            "double_zone_min_points": DOUBLE_ZONE_MIN_POINTS,
            "double_zone_min_track_sec": DOUBLE_ZONE_MIN_TRACK_SEC,
            "double_zone_exit_hits": DOUBLE_ZONE_EXIT_HITS,
        }

    def interval_destination_counts(self):
        counts = self.destination_counts()
        return {key: counts[key] - self.interval_start_counts.get(key, 0) for key in counts}

    def _register_detection(self, raw_id, box, frame, frame_shape, now, visible_ids):
        center = box_center(box)
        crop = self._crop_person(frame, box)
        feature = self.cache.extract(crop)
        person_id = None

        if raw_id is not None:
            mapped_id = self._raw_to_person.get(raw_id)
            mapped_state = self._people.get(mapped_id)
            if mapped_state is not None and now - mapped_state["last_seen"] <= TRACK_MAX_MISSING_SEC:
                person_id = mapped_id
            else:
                self._raw_to_person.pop(raw_id, None)

        if person_id is None:
            person_id = self._match_existing_person(box, center, feature, frame_shape, now, visible_ids)

        if person_id is None:
            person_id = self._next_person_id
            self._next_person_id += 1
            self.detected_person_count += 1
            self._people[person_id] = {
                "first_seen": now,
                "last_seen": now,
                "last_box": box,
                "last_center": center,
                "hit_count": 0,
                "feature": feature,
                "path": deque(maxlen=DESTINATION_HISTORY_SIZE),
                "destination": None,
                "destination_counted": False,
                "roi_counted": False,
                "roi_entered_ts": None,
                "total_counted": False,
                "total_counted_ts": None,
                "count_event": None,
                "was_inside_roi": False,
                "last_inside_norm": None,
                "last_inside_ts": None,
                "double_zone_entry_seen": False,
                "double_zone_entry_ts": None,
                "double_zone_entry_last_ts": None,
                "double_zone_exit_candidate": None,
                "double_zone_exit_hits": 0,
            }

        if raw_id is not None:
            self._raw_to_person[raw_id] = person_id
            self._raw_seen_at[raw_id] = now

        state = self._people[person_id]
        destination = self._record_path_point(state, box, frame_shape, now)
        if destination is not None:
            self._finalize_destination(state, person_id, destination, now)

        state["last_seen"] = now
        state["last_box"] = box
        state["last_center"] = center
        state["hit_count"] = int(state.get("hit_count", 0)) + 1
        state["feature"] = merge_feature(state.get("feature"), feature)
        visible_ids.add(person_id)
        return person_id

    def _held_detections(self, now: float, visible_ids: set[int]):
        held = []
        if BOX_HOLD_SEC <= 0:
            return held

        for person_id, state in self._people.items():
            if person_id in visible_ids:
                continue
            if int(state.get("hit_count", 0)) < BOX_HOLD_MIN_HITS:
                continue
            age = now - float(state.get("last_seen", 0))
            if age < 0 or age > BOX_HOLD_SEC:
                continue
            box = state.get("last_box")
            if not box:
                continue
            held.append({
                "person_id": person_id,
                "box": box,
                "held": True,
                "missing_age": age,
            })
        return held

    def _update_current_stats(self, current_count: int, now: float):
        self.peak_count = max(self.peak_count, current_count)
        self._current_samples.append((now, current_count))
        cutoff = now - AVG_WINDOW_SEC
        while self._current_samples and self._current_samples[0][0] < cutoff:
            self._current_samples.popleft()
        if self._current_samples:
            self.avg_count = sum(v for _, v in self._current_samples) / len(self._current_samples)
        else:
            self.avg_count = 0.0

    def _update_mode(self, brightness: float) -> str:
        if self._mode == "night":
            if brightness > NIGHT_BRIGHTNESS_THRESHOLD + NIGHT_MODE_HYSTERESIS:
                self._mode = "day"
        else:
            if brightness < NIGHT_BRIGHTNESS_THRESHOLD - NIGHT_MODE_HYSTERESIS:
                self._mode = "night"
        return self._mode

    def _dominant_destination(self) -> str:
        counts = {
            "dorm": self.to_dorm_count,
            "starbucks": self.to_starbucks_count,
            "sports": self.to_sports_count,
        }
        top_value = max(counts.values())
        if top_value <= 0:
            return "none"
        winners = [name for name, value in counts.items() if value == top_value]
        return winners[0] if len(winners) == 1 else "balanced"

    def vehicle_counts(self):
        return self.vehicle_flow.counts()

    def interval_vehicle_counts(self):
        return self.vehicle_flow.interval_counts()

    def _dominant_vehicle(self) -> str:
        return self.vehicle_flow.dominant()

    def run(self):
        no_frame_since = None
        while self._running:
            if _shutdown_event.is_set():
                print("[Inference] 收到關閉信號，停止推理")
                break

            t0 = time.time()
            ret, frame = self.vcap.read()
            if not ret or frame is None:
                now = self._now()
                if no_frame_since is None:
                    no_frame_since = now
                elif now - no_frame_since >= INFERENCE_NO_FRAME_RESTART_SEC:
                    self.vcap.request_reconnect("no fresh frame for inference")
                    no_frame_since = now
                time.sleep(0.05)
                continue
            no_frame_since = None

            brightness = estimate_brightness(frame)
            mode = self._update_mode(brightness)
            frame = enhance_night_frame(frame) if mode == "night" else frame
            analysis_mode = self.analysis_mode()
            reset_tracker = self.consume_tracker_reset()
            track_classes = VEHICLE_CLASS_IDS if analysis_mode == ANALYSIS_MODE_VEHICLES else [0]
            results = self.model.track(
                frame,
                persist=not reset_tracker,
                classes=track_classes,
                tracker=TRACKER_CONFIG,
                verbose=False,
                imgsz=YOLO_IMGSZ,
                conf=BYTETRACK_CONF,
                device=MODEL_DEVICE,
            )

            now = self._now()
            if analysis_mode == ANALYSIS_MODE_VEHICLES:
                self.vehicle_flow.purge_stale(now)
                detections = []

                if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                    boxes_obj = results[0].boxes
                    boxes = boxes_obj.xyxy.cpu().tolist()
                    if boxes_obj.id is not None:
                        ids = boxes_obj.id.int().cpu().tolist()
                    else:
                        ids = [None] * len(boxes)
                    if boxes_obj.cls is not None:
                        class_ids = boxes_obj.cls.int().cpu().tolist()
                    else:
                        class_ids = [None] * len(boxes)

                    for raw_id, class_id, box in zip(ids, class_ids, boxes):
                        if class_id is None:
                            continue
                        box = tuple(float(v) for v in box)
                        track_key = self.vehicle_flow.register_detection(raw_id, class_id, box, now)
                        detections.append({
                            "track_key": track_key,
                            "vehicle_type": self.vehicle_flow.vehicle_type_for_class(class_id),
                            "box": box,
                        })

                current_count = len(detections)
                self.vehicle_flow.update_stats(current_count, now)
                annotated = draw_vehicle_annotations(
                    frame,
                    detections,
                    current_count,
                    mode,
                    SHOW_ROAD_ROI,
                    ROAD_ROI_NORM,
                    VEHICLE_COLORS,
                    VEHICLE_DISPLAY_LABELS,
                )

                resized = cv2.resize(annotated, (OUTPUT_WIDTH, OUTPUT_HEIGHT))
                _, buf = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                b64 = base64.b64encode(buf).decode('utf-8')
                is_alert = current_count > ALERT_THRESHOLD
                vehicle_counts = self.vehicle_counts()
                interval_counts = self.interval_vehicle_counts()
                interval_total = self.vehicle_total_count - self.vehicle_interval_start_total

                payload = {
                    "image": b64,
                    "analysis_mode": ANALYSIS_MODE_VEHICLES,
                    "current_count": current_count,
                    "total_count": self.vehicle_total_count,
                    "detected_total_count": self.vehicle_total_count,
                    "assigned_destination_count": self.vehicle_total_count,
                    "pending_destination_count": 0,
                    "interval_count": interval_total,
                    "to_dorm_count": vehicle_counts["car"],
                    "to_starbucks_count": vehicle_counts["motorcycle"],
                    "to_sports_count": vehicle_counts["bus"],
                    "vehicle_counts": vehicle_counts,
                    "interval_vehicle_counts": interval_counts,
                    "destination_counts": {
                        "dorm": vehicle_counts["car"],
                        "starbucks": vehicle_counts["motorcycle"],
                        "sports": vehicle_counts["bus"],
                    },
                    "interval_destination_counts": {
                        "dorm": interval_counts["car"],
                        "starbucks": interval_counts["motorcycle"],
                        "sports": interval_counts["bus"],
                    },
                    "dominant_destination": self._dominant_vehicle(),
                    "dominant_vehicle": self._dominant_vehicle(),
                    "peak_count": self.vehicle_peak_count,
                    "avg_count": round(self.vehicle_avg_count, 1),
                    "mode": mode,
                    "brightness": round(brightness, 1),
                    "alert": f"車流警報：目前 {current_count} 台，超過閾值 {ALERT_THRESHOLD}" if is_alert else "車流辨識中",
                    "alert_active": is_alert,
                    "alert_threshold": ALERT_THRESHOLD,
                    "history": list(vehicle_history[-HISTORY_DASHBOARD_POINTS:]),
                    "time": time.strftime("%H:%M:%S"),
                    "ts_ms": int(self._now() * 1000),
                }
                self.last_payload = payload

                if self.result_q.full():
                    try:
                        self.result_q.get_nowait()
                    except stdlib_queue.Empty:
                        pass
                self.result_q.put_nowait(payload)

                elapsed = time.time() - t0
                sleep_t = self._frame_interval - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)
                continue

            self._purge_stale(now)
            detections = []
            visible_ids = set()

            if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                boxes_obj = results[0].boxes
                boxes = boxes_obj.xyxy.cpu().tolist()
                if boxes_obj.id is not None:
                    ids = boxes_obj.id.int().cpu().tolist()
                else:
                    ids = [None] * len(boxes)

                for raw_id, box in zip(ids, boxes):
                    box = tuple(float(v) for v in box)
                    person_id = self._register_detection(raw_id, box, frame, frame.shape, now, visible_ids)
                    detections.append({"person_id": person_id, "box": box})

            raw_current_count = len(detections)
            held_current_count = 0
            tracked_current_count = len(visible_ids)
            current_count = raw_current_count
            self._update_current_stats(current_count, now)
            destination_counts = self.destination_counts()
            destination_total = sum(destination_counts.values())
            pending_count = self.pending_destination_count()
            count_debug = self.count_debug_snapshot(
                current_count,
                destination_counts,
                destination_total,
                pending_count,
            ) if SHOW_COUNT_DEBUG else None
            annotated = draw_person_annotations(
                frame,
                detections,
                self._people,
                mode,
                ROAD_ROI_NORM,
                EXIT_LINES_NORM,
                DESTINATION_COLORS,
                DESTINATION_LABELS,
                SHOW_ROAD_ROI,
                SHOW_DIRECTION_GUIDES,
                SHOW_PERSON_LABELS,
                now,
                COUNT_EVENT_OVERLAY_SEC,
                SHOW_COUNT_DEBUG,
                FORWARD_WALKWAY_ZONES_NORM,
                VISIBLE_EXIT_ZONES,
                count_debug,
            )

            resized = cv2.resize(annotated, (OUTPUT_WIDTH, OUTPUT_HEIGHT))
            _, buf = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            b64 = base64.b64encode(buf).decode('utf-8')
            is_alert = current_count > ALERT_THRESHOLD
            interval_counts = self.interval_destination_counts()
            interval_total = self.roi_person_count - self.interval_start_roi_count

            payload = {
                "image":         b64,
                "analysis_mode": ANALYSIS_MODE_PEOPLE,
                "current_count": current_count,
                "raw_current_count": raw_current_count,
                "held_current_count": held_current_count,
                "tracked_current_count": tracked_current_count,
                "total_count":   self.roi_person_count,
                "detected_total_count": self.detected_person_count,
                "assigned_destination_count": destination_total,
                "pending_destination_count": pending_count,
                "interval_count": interval_total,
                "to_dorm_count": destination_counts["dorm"],
                "to_starbucks_count": destination_counts["starbucks"],
                "to_sports_count": destination_counts["sports"],
                "destination_counts": destination_counts,
                "interval_destination_counts": interval_counts,
                "dominant_destination": self._dominant_destination(),
                "peak_count":    self.peak_count,
                "avg_count":     round(self.avg_count, 1),
                "mode":          mode,
                "brightness":    round(brightness, 1),
                "alert":         f"人流警報：目前 {current_count} 人，超過閾值 {ALERT_THRESHOLD}" if is_alert else "系統運行中",
                "alert_active":  is_alert,
                "alert_threshold": ALERT_THRESHOLD,
                "history":       list(traffic_history[-HISTORY_DASHBOARD_POINTS:]),
                "time":          time.strftime("%H:%M:%S"),
                "ts_ms":         int(self._now() * 1000),
            }
            if count_debug is not None:
                payload["count_debug"] = count_debug
            self.last_payload = payload

            if self.result_q.full():
                try:
                    self.result_q.get_nowait()
                except stdlib_queue.Empty:
                    pass
            self.result_q.put_nowait(payload)

            elapsed = time.time() - t0
            sleep_t = self._frame_interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    def stop(self):
        self._running = False


# ══════════════════════════════════════════════════════════════════════════════
# 2. 優雅關閉
# ══════════════════════════════════════════════════════════════════════════════
def _cleanup():
    cleanup_resources(_vcap, _inf_thread, _server)


def _signal_handler(signum, frame):
    """
    Ctrl+C 進入這裡。
    透過 call_soon_threadsafe 取消 main task，
    讓 asyncio event loop 自然走到 finally 執行 cleanup，
    不用 sys.exit 或 os._exit。
    """
    print("\n[Signal] 收到中斷信號，準備關閉...")
    _shutdown_event.set()

    if _main_task is not None:
        _main_task.get_loop().call_soon_threadsafe(_main_task.cancel)

# ══════════════════════════════════════════════════════════════════════════════
# 3. 主程式
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    global _vcap, _inf_thread, _server, _main_task

    # 把自己存到全域，讓 signal handler 能取消
    _main_task = asyncio.current_task()

    preflight_check(MODEL_DEVICE)

    print("[Main] 載入 YOLO 模型...")
    model = YOLO(MODEL_WEIGHTS_PATH)
    model.fuse()
    warmup_model(model, YOLO_IMGSZ, MODEL_DEVICE)

    if CAMERA_RTSP_URL:
        rtsp_url = CAMERA_RTSP_URL
    else:
        camera_ip = find_camera_ip(CAMERA_SCAN_BASE_IP, CAMERA_SCAN_PORT)
        if not camera_ip:
            print("[Main] 找不到攝影機，請確認網路設定")
            return
        rtsp_url = (
            f"rtsp://{CAMERA_RTSP_USERNAME}:{CAMERA_RTSP_PASSWORD}"
            f"@{camera_ip}:{CAMERA_SCAN_PORT}/{CAMERA_RTSP_PATH}"
        )
    print(f"[Main] 連線至 {rtsp_url}")

    _vcap = VideoCaptureThreading(
        rtsp_url,
        shutdown_event=_shutdown_event,
        reconnect_delay=RECONNECT_DELAY,
        fail_threshold=FAIL_THRESHOLD,
        rtsp_open_timeout_ms=RTSP_OPEN_TIMEOUT_MS,
        rtsp_read_timeout_ms=RTSP_READ_TIMEOUT_MS,
        rtsp_stale_frame_sec=RTSP_STALE_FRAME_SEC,
        rtsp_restart_cooldown_sec=RTSP_RESTART_COOLDOWN_SEC,
        capture_buffer_size=CAPTURE_BUFFER_SIZE,
    )
    appearance_cache = AppearanceCache()
    _inf_thread = InferenceThread(model, _vcap, appearance_cache)
    _inf_thread.start()
    asyncio.create_task(traffic_logger(
        lambda: _inf_thread,
        _shutdown_event,
        traffic_history,
        vehicle_history,
        TRAFFIC_SUMMARY_PATH,
        TRAFFIC_EVENTS_PATH,
        VEHICLE_SUMMARY_PATH,
        SUMMARY_CSV_COLUMNS,
        EVENT_CSV_COLUMNS,
        VEHICLE_SUMMARY_CSV_COLUMNS,
        INTERVAL_MINUTES,
        HISTORY_MAX_POINTS,
        ANALYSIS_MODE_VEHICLES,
    ))

    try:
        async with websockets.serve(
            lambda ws: video_ai_stream(
                ws,
                _inf_thread,
                _shutdown_event,
                traffic_history,
                vehicle_history,
                ANALYSIS_MODE_VEHICLES,
            ),
            SERVER_HOST,
            SERVER_PORT,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_queue=2,
        ) as server:
            _server = server
            print("🚀 伺服器啟動！請打開網頁。")
            await asyncio.Future()  # 永遠等待，直到被 _main_task.cancel() 取消
            while not _shutdown_event.is_set():
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        print("[Main] 收到取消信號")

    finally:
        _cleanup()


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # signal handler 已處理，這裡不需要再動
