from __future__ import annotations

from pathlib import Path
import threading
import time

import cv2


class VideoCaptureThreading:
    def __init__(
        self,
        src: str,
        shutdown_event: threading.Event | None = None,
        reconnect_delay: float = 3.0,
        fail_threshold: int = 25,
        rtsp_open_timeout_ms: int = 5000,
        rtsp_read_timeout_ms: int = 5000,
        rtsp_stale_frame_sec: float = 8.0,
        rtsp_restart_cooldown_sec: float = 4.0,
        capture_buffer_size: int = 1,
    ):
        self.src = src
        self.shutdown_event = shutdown_event or threading.Event()
        self.reconnect_delay = reconnect_delay
        self.fail_threshold = fail_threshold
        self.rtsp_open_timeout_ms = rtsp_open_timeout_ms
        self.rtsp_read_timeout_ms = rtsp_read_timeout_ms
        self.rtsp_stale_frame_sec = rtsp_stale_frame_sec
        self.rtsp_restart_cooldown_sec = rtsp_restart_cooldown_sec
        self.capture_buffer_size = capture_buffer_size
        self._running = True
        self._lock = threading.Lock()
        self._ret = False
        self._frame = None
        self._cap = None
        self._last_frame_at = 0.0
        self._last_connect_attempt = 0.0
        self._reconnect_requested = False
        self._reconnect_reason = ""
        self._is_video_file_source = self._looks_like_video_file(src)
        self._frame_interval = 0.0

        self._connect("startup")
        self._thread = threading.Thread(target=self._update, daemon=True, name="CaptureThread")
        self._thread.start()

    @staticmethod
    def _looks_like_video_file(src: str) -> bool:
        if "://" in src:
            return False
        return Path(src).expanduser().exists()

    def _connect(self, reason: str = "startup"):
        elapsed = time.time() - self._last_connect_attempt
        if self._last_connect_attempt > 0 and elapsed < self.rtsp_restart_cooldown_sec:
            time.sleep(self.rtsp_restart_cooldown_sec - elapsed)
        self._last_connect_attempt = time.time()

        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            time.sleep(self.reconnect_delay)

        print("[Camera] 嘗試連線...")
        cap = None
        try:
            cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.rtsp_open_timeout_ms)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.rtsp_read_timeout_ms)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, self.capture_buffer_size)
            if self._is_video_file_source:
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                self._frame_interval = 1.0 / fps if fps > 0 else 0.0
            else:
                self._frame_interval = 0.0

            ret, frame = cap.read()
            if ret and frame is not None:
                print("[Camera] 連線成功 ✅")
                with self._lock:
                    self._ret = ret
                    self._frame = frame
                    self._last_frame_at = time.time()
                    self._reconnect_requested = False
                    self._reconnect_reason = ""
                self._cap = cap
            else:
                print("[Camera] 連線失敗（無法讀取幀），稍後重試...")
                cap.release()
                self._cap = None

        except cv2.error as e:
            print(f"[Camera] OpenCV 連線錯誤：{e}")
            if cap:
                cap.release()
            self._cap = None

        except Exception as e:
            print(f"[Camera] 連線異常：{type(e).__name__}: {e}")
            if cap:
                cap.release()
            self._cap = None

    def request_reconnect(self, reason: str):
        with self._lock:
            self._reconnect_requested = True
            self._reconnect_reason = reason

    def _consume_reconnect_request(self):
        with self._lock:
            if not self._reconnect_requested:
                return None
            reason = self._reconnect_reason or "requested"
            self._reconnect_requested = False
            self._reconnect_reason = ""
            return reason

    def is_stale(self) -> bool:
        with self._lock:
            if self._frame is None or self._last_frame_at <= 0:
                return True
            return time.time() - self._last_frame_at > self.rtsp_stale_frame_sec

    def _update(self):
        fail_count = 0
        while self._running:
            if self.shutdown_event.is_set():
                print("[Camera] 收到關閉信號，停止讀取")
                break

            reconnect_reason = self._consume_reconnect_request()
            if reconnect_reason:
                fail_count = 0
                print(f"[Camera] Reconnect requested: {reconnect_reason}")
                self._connect(reconnect_reason)
                continue

            if self._cap is None or not self._cap.isOpened():
                self._connect("capture not open")
                continue

            try:
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    fail_count = 0
                    with self._lock:
                        self._ret, self._frame = ret, frame
                        self._last_frame_at = time.time()
                    if self._frame_interval > 0:
                        time.sleep(self._frame_interval)
                else:
                    fail_count += 1
                    time.sleep(0.1)
                    if fail_count >= self.fail_threshold or self.is_stale():
                        print("[Camera] 連續讀取失敗，重新連線...")
                        fail_count = 0
                        self._connect("read failure")

            except cv2.error as e:
                print(f"[Camera] OpenCV 讀取錯誤：{e}")
                fail_count += 1
                time.sleep(0.1)
                if fail_count >= self.fail_threshold or self.is_stale():
                    fail_count = 0
                    self._connect("opencv read error")

            except Exception as e:
                print(f"[Camera] 未知錯誤：{type(e).__name__}: {e}")
                fail_count += 1
                time.sleep(0.1)
                if fail_count >= self.fail_threshold or self.is_stale():
                    fail_count = 0
                    self._connect("read exception")

    def read(self):
        with self._lock:
            if self._frame is None:
                return False, None
            if time.time() - self._last_frame_at > self.rtsp_stale_frame_sec:
                return False, None
            return self._ret, self._frame.copy()

    def stop(self):
        self._running = False
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
