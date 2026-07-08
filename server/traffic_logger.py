from __future__ import annotations

import asyncio
import csv
import os
import threading
import time
from collections.abc import Callable
from typing import Any


CSV_LOCK = threading.Lock()


def _csv_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _migrate_legacy_summary_csv(path: str, current_header: list[str], columns: list[str]) -> bool:
    required_columns = {
        "Timestamp",
        "Interval_Count",
        "Interval_To_Dorm",
        "Interval_To_Starbucks_Gate",
        "Interval_To_Sports_Gate",
    }
    if not required_columns.issubset(set(current_header)):
        return False

    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    migrated_rows = []
    peak_time = ""
    peak_count = 0
    for row in rows:
        timestamp = row.get("Timestamp", "")
        interval_count = _csv_int(row.get("Interval_Count"))
        if not peak_time or interval_count > peak_count:
            peak_time = timestamp
            peak_count = interval_count
        migrated_rows.append([
            timestamp,
            _csv_int(row.get("Interval_To_Dorm")),
            _csv_int(row.get("Interval_To_Starbucks_Gate")),
            _csv_int(row.get("Interval_To_Sports_Gate")),
            interval_count,
            peak_time,
            peak_count,
        ])

    base, ext = os.path.splitext(path)
    backup_path = f"{base}.backup-{time.strftime('%Y%m%d-%H%M%S')}{ext}"
    os.replace(path, backup_path)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(migrated_rows)
    print(f"[CSV] Legacy summary migrated. Old file backed up to {backup_path}")
    return True


def ensure_csv_header(path: str, columns: list[str], allow_legacy_summary_migration: bool = False) -> bool:
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                current_header = next(csv.reader(f), [])
            if current_header == columns:
                return True
            if allow_legacy_summary_migration and _migrate_legacy_summary_csv(path, current_header, columns):
                return True
            base, ext = os.path.splitext(path)
            backup_path = f"{base}.backup-{time.strftime('%Y%m%d-%H%M%S')}{ext}"
            os.replace(path, backup_path)
            print(f"[CSV] Header changed. Old file backed up to {backup_path}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(columns)
        return True
    except PermissionError as e:
        print(f"[CSV] Cannot write header to {path}: {e}")
        return False


def append_csv_row(
    path: str,
    columns: list[str],
    row: list,
    allow_legacy_summary_migration: bool = False,
) -> bool:
    with CSV_LOCK:
        try:
            if not ensure_csv_header(path, columns, allow_legacy_summary_migration):
                return False
            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(row)
            return True
        except PermissionError as e:
            print(f"[CSV] Cannot append to {path}: {e}")
            return False


async def traffic_logger(
    inf_thread_getter: Callable[[], Any],
    shutdown_event,
    traffic_history: list[dict],
    vehicle_history: list[dict],
    traffic_summary_path: str,
    traffic_events_path: str,
    vehicle_summary_path: str,
    summary_csv_columns: list[str],
    event_csv_columns: list[str],
    vehicle_summary_csv_columns: list[str],
    interval_minutes: int,
    history_max_points: int,
    analysis_mode_vehicles: str,
):
    ensure_csv_header(
        traffic_summary_path,
        summary_csv_columns,
        allow_legacy_summary_migration=True,
    )
    ensure_csv_header(traffic_events_path, event_csv_columns)
    ensure_csv_header(vehicle_summary_path, vehicle_summary_csv_columns)

    while not shutdown_event.is_set():
        await asyncio.sleep(interval_minutes * 60)

        inf_thread = inf_thread_getter()
        if inf_thread is None:
            continue

        counts = inf_thread.destination_counts()
        interval_counts = inf_thread.interval_destination_counts()
        assigned_total = sum(counts.values())
        current_total = inf_thread.roi_person_count
        pending_count = inf_thread.pending_destination_count()
        interval_count = current_total - inf_thread.interval_start_roi_count
        inf_thread.interval_start_roi_count = current_total
        inf_thread.interval_start_counts = counts.copy()

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        last_payload = getattr(inf_thread, "last_payload", {})
        current_count = last_payload.get("current_count", 0)
        summary_row = {
            "time": timestamp,
            "count": interval_count,
            "total": current_total,
            "assigned_destination_count": assigned_total,
            "pending_destination_count": pending_count,
            "current": current_count,
            "interval_to_dorm": interval_counts["dorm"],
            "interval_to_starbucks": interval_counts["starbucks"],
            "interval_to_sports": interval_counts["sports"],
            "to_dorm": counts["dorm"],
            "to_starbucks": counts["starbucks"],
            "to_sports": counts["sports"],
            "dominant_destination": inf_thread._dominant_destination(),
            "peak": inf_thread.peak_count,
        }
        peak_interval = max(
            [*traffic_history, summary_row],
            key=lambda item: item.get("count", 0),
        )
        summary_row["peak_interval_time"] = peak_interval.get("time", timestamp)
        summary_row["peak_interval_count"] = peak_interval.get("count", interval_count)

        append_csv_row(
            traffic_summary_path,
            summary_csv_columns,
            [
                timestamp,
                interval_counts["dorm"],
                interval_counts["starbucks"],
                interval_counts["sports"],
                interval_count,
                summary_row["peak_interval_time"],
                summary_row["peak_interval_count"],
            ],
            allow_legacy_summary_migration=True,
        )

        traffic_history.append(summary_row)
        if len(traffic_history) > history_max_points:
            traffic_history.pop(0)

        vehicle_counts = inf_thread.vehicle_counts()
        vehicle_interval_counts = inf_thread.interval_vehicle_counts()
        vehicle_interval_total = inf_thread.vehicle_total_count - inf_thread.vehicle_interval_start_total
        inf_thread.vehicle_interval_start_total = inf_thread.vehicle_total_count
        inf_thread.vehicle_interval_start_counts = vehicle_counts.copy()
        vehicle_interval_car = vehicle_interval_counts["car"]
        vehicle_interval_motorcycle = vehicle_interval_counts["motorcycle"]
        vehicle_interval_selected_total = vehicle_interval_car + vehicle_interval_motorcycle

        append_csv_row(
            vehicle_summary_path,
            vehicle_summary_csv_columns,
            [
                timestamp,
                vehicle_interval_car,
                vehicle_interval_motorcycle,
                vehicle_interval_selected_total,
            ],
        )

        vehicle_history.append({
            "time": timestamp,
            "count": vehicle_interval_total,
            "total": inf_thread.vehicle_total_count,
            "current": last_payload.get("current_count", 0)
                if last_payload.get("analysis_mode") == analysis_mode_vehicles
                else 0,
            "interval_car": vehicle_interval_counts["car"],
            "interval_motorcycle": vehicle_interval_counts["motorcycle"],
            "interval_bus": vehicle_interval_counts["bus"],
            "interval_truck": vehicle_interval_counts["truck"],
            "car": vehicle_counts["car"],
            "motorcycle": vehicle_counts["motorcycle"],
            "bus": vehicle_counts["bus"],
            "truck": vehicle_counts["truck"],
            "dominant_vehicle": inf_thread._dominant_vehicle(),
            "peak": inf_thread.vehicle_peak_count,
        })
        if len(vehicle_history) > history_max_points:
            vehicle_history.pop(0)
