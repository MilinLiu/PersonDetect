from __future__ import annotations

from collections import deque


class VehicleFlowCounter:
    def __init__(
        self,
        class_labels: dict[int, str],
        display_labels: dict[str, str],
        track_id_ttl_sec: float,
        avg_window_sec: float,
    ):
        self.class_labels = class_labels
        self.display_labels = display_labels
        self.track_id_ttl_sec = track_id_ttl_sec
        self.avg_window_sec = avg_window_sec
        self.total_count = 0
        self.type_counts = {vehicle_type: 0 for vehicle_type in display_labels}
        self.interval_start_total = 0
        self.interval_start_counts = self.type_counts.copy()
        self.peak_count = 0
        self.avg_count = 0.0
        self.samples = deque()
        self.active_tracks: dict[str, dict] = {}
        self.counted_keys: set[str] = set()

    def vehicle_type_for_class(self, class_id: int) -> str:
        return self.class_labels.get(int(class_id), "vehicle")

    def counts(self):
        return self.type_counts.copy()

    def interval_counts(self):
        counts = self.counts()
        return {key: counts[key] - self.interval_start_counts.get(key, 0) for key in counts}

    def dominant(self) -> str:
        counts = self.counts()
        top_value = max(counts.values())
        if top_value <= 0:
            return "none"
        winners = [name for name, value in counts.items() if value == top_value]
        return winners[0] if len(winners) == 1 else "balanced"

    def purge_stale(self, now: float):
        cutoff = now - self.track_id_ttl_sec
        for track_key, state in list(self.active_tracks.items()):
            if state.get("last_seen", 0) < cutoff:
                self.active_tracks.pop(track_key, None)

    def register_detection(self, raw_id, class_id: int, box, now: float):
        vehicle_type = self.vehicle_type_for_class(class_id)
        track_key = None if raw_id is None else f"{vehicle_type}:{int(raw_id)}"
        if track_key is not None:
            self.active_tracks[track_key] = {
                "last_seen": now,
                "box": box,
                "vehicle_type": vehicle_type,
            }
            if track_key not in self.counted_keys:
                self.counted_keys.add(track_key)
                self.total_count += 1
                self.type_counts[vehicle_type] = self.type_counts.get(vehicle_type, 0) + 1
        return track_key

    def update_stats(self, current_count: int, now: float):
        self.peak_count = max(self.peak_count, current_count)
        self.samples.append((now, current_count))
        cutoff = now - self.avg_window_sec
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        if self.samples:
            self.avg_count = sum(v for _, v in self.samples) / len(self.samples)
        else:
            self.avg_count = 0.0
