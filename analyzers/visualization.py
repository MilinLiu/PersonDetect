from __future__ import annotations

import cv2

from analyzers.geometry import norm_to_pixel, road_roi_pixels


def draw_direction_guides(
    annotated,
    road_roi_norm,
    exit_lines_norm,
    destination_colors,
    destination_labels,
    show_road_roi: bool,
    show_direction_guides: bool,
):
    if not (show_road_roi or show_direction_guides):
        return

    roi = road_roi_pixels(annotated.shape, road_roi_norm)
    cv2.polylines(annotated, [roi], True, (0, 220, 255), 2)
    if not show_direction_guides:
        return

    for destination, segment in exit_lines_norm.items():
        color = destination_colors.get(destination, (255, 255, 255))
        start_px = norm_to_pixel(segment[0], annotated.shape)
        end_px = norm_to_pixel(segment[1], annotated.shape)
        label_x = int((start_px[0] + end_px[0]) / 2)
        label_y = int((start_px[1] + end_px[1]) / 2)
        cv2.line(annotated, start_px, end_px, color, 3)
        cv2.circle(annotated, start_px, 4, color, -1)
        cv2.circle(annotated, end_px, 4, color, -1)
        cv2.putText(
            annotated,
            destination_labels.get(destination, destination),
            (max(8, label_x - 44), max(24, label_y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            color,
            2,
        )


def _clamp01(value) -> float:
    return max(0.0, min(1.0, float(value)))


def _norm_rect_to_pixels(rect_norm, frame_shape):
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = rect_norm
    x1 = _clamp01(x1)
    y1 = _clamp01(y1)
    x2 = _clamp01(x2)
    y2 = _clamp01(y2)
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1
    return (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))


def _visible_exit_rule_rect(rule: dict):
    return (
        rule.get("x_min", 0.0),
        rule.get("y_min", 0.0),
        rule.get("x_max", 1.0),
        rule.get("y_max", 1.0),
    )


def _draw_translucent_rect(annotated, rect_norm, color, label: str | None = None, alpha: float = 0.13):
    pt1, pt2 = _norm_rect_to_pixels(rect_norm, annotated.shape)
    overlay = annotated.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    cv2.addWeighted(overlay, alpha, annotated, 1.0 - alpha, 0, annotated)
    cv2.rectangle(annotated, pt1, pt2, color, 1)
    if label:
        cv2.putText(
            annotated,
            label,
            (pt1[0] + 5, max(18, pt1[1] + 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            1,
        )


def draw_count_debug_zones(
    annotated,
    forward_walkway_zones_norm,
    visible_exit_zones,
    destination_colors,
    destination_labels,
):
    for index, rect in enumerate(forward_walkway_zones_norm or (), start=1):
        _draw_translucent_rect(
            annotated,
            rect,
            (180, 180, 255),
            f"walkway {index}",
            alpha=0.10,
        )

    for destination, rule in (visible_exit_zones or {}).items():
        color = destination_colors.get(destination, (255, 255, 255))
        label = destination_labels.get(destination, destination)
        _draw_translucent_rect(
            annotated,
            _visible_exit_rule_rect(rule),
            color,
            f"exit {label}",
            alpha=0.16,
        )


def _recent_motion_text(state) -> str:
    points = list(state.get("path", ())) if state else []
    if len(points) < 2:
        return "dx +0.000 dy +0.000"
    sample = points[-min(6, len(points)):]
    sx, sy = sample[0][2]
    ex, ey = sample[-1][2]
    return f"dx {ex - sx:+.3f} dy {ey - sy:+.3f}"


def draw_person_debug_label(annotated, det, state, box, destination_labels):
    if not state:
        return
    x1, y1, x2, y2 = box
    points = list(state.get("path", ()))
    if state.get("destination_counted"):
        destination = state.get("destination")
        status = f"dest {destination_labels.get(destination, destination)}"
        color = (80, 255, 80)
    elif state.get("roi_counted"):
        status = "pending"
        color = (0, 220, 255)
    else:
        status = "watch"
        color = (210, 210, 210)

    foot = tuple(map(int, points[-1][1])) if points else (int((x1 + x2) / 2), y2)
    cv2.circle(annotated, foot, 5, color, -1)
    label = f"P{det['person_id']} {status} pts {len(points)} {_recent_motion_text(state)}"
    label_y = y2 + 18 if y2 + 22 < annotated.shape[0] else max(20, y1 + 18)
    cv2.putText(
        annotated,
        label,
        (max(4, x1), label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
    )


def draw_count_debug_panel(annotated, count_debug):
    if not count_debug:
        return
    destination_counts = count_debug.get("destination_counts", {})
    lines = [
        "COUNT DEBUG",
        (
            f"current {count_debug.get('current_count', 0)} "
            f"total {count_debug.get('total_count', 0)} "
            f"assigned {count_debug.get('assigned_destination_count', 0)} "
            f"pending {count_debug.get('pending_destination_count', 0)}"
        ),
        (
            f"dorm {destination_counts.get('dorm', 0)} "
            f"star {destination_counts.get('starbucks', 0)} "
            f"sports {destination_counts.get('sports', 0)}"
        ),
        (
            f"visible tracks {count_debug.get('visible_tracks', 0)} "
            f"active states {count_debug.get('active_tracks', 0)} "
            f"pending states {count_debug.get('tracked_pending_count', 0)}"
        ),
        (
            f"count_on {count_debug.get('total_count_on', '')} "
            f"missing_infer {count_debug.get('allow_missing_destination_infer', False)}"
        ),
        (
            f"min pts {count_debug.get('visible_exit_min_points', 0)} "
            f"travel {count_debug.get('visible_exit_min_travel_ratio', 0):.3f} "
            f"delta {count_debug.get('visible_exit_min_delta', 0):.3f}"
        ),
    ]

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.44
    thickness = 1
    sizes = [cv2.getTextSize(line, font, scale, thickness)[0] for line in lines]
    width = max(size[0] for size in sizes) + 22
    height = len(lines) * 18 + 18
    width = min(width, annotated.shape[1] - 16)
    overlay = annotated.copy()
    cv2.rectangle(overlay, (8, 8), (8 + width, 8 + height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.58, annotated, 0.42, 0, annotated)
    for index, line in enumerate(lines):
        color = (80, 255, 80) if index == 0 else (245, 245, 245)
        cv2.putText(
            annotated,
            line,
            (18, 28 + index * 18),
            font,
            scale,
            color,
            thickness,
        )


def draw_person_trail(annotated, state):
    if not state:
        return
    points = list(state.get("path", ()))[-14:]
    if len(points) < 2:
        return

    pixel_points = [tuple(map(int, point[1])) for point in points]
    color = (120, 255, 120) if state.get("destination_counted") else (255, 220, 80)
    for start, end in zip(pixel_points, pixel_points[1:]):
        cv2.line(annotated, start, end, color, 2)
    cv2.circle(annotated, pixel_points[-1], 4, color, -1)


def _person_status_label(state, destination_labels) -> str:
    if not state:
        return "detect"
    if state.get("destination_counted"):
        destination = state.get("destination")
        return destination_labels.get(destination, destination) or "done"
    if state.get("total_counted"):
        return "pending"
    if state.get("roi_counted"):
        return "roi"
    return "detect"


def _person_label(det, state, destination_labels) -> str:
    person_id = det.get("person_id", "?")
    label = f"P{person_id}"
    if state and state.get("display_count") is not None:
        label = f"{label} #{state.get('display_count')}"
    suffix = " hold" if det.get("held") else ""
    return f"{label} {_person_status_label(state, destination_labels)}{suffix}"


def _draw_label_box(annotated, text: str, x: int, y: int, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.56
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    y = max(th + 8, y)
    x = max(2, min(x, annotated.shape[1] - tw - 8))
    cv2.rectangle(
        annotated,
        (x - 2, y - th - 6),
        (x + tw + 6, y + baseline + 2),
        (20, 24, 32),
        -1,
    )
    cv2.rectangle(
        annotated,
        (x - 2, y - th - 6),
        (x + tw + 6, y + baseline + 2),
        color,
        1,
    )
    cv2.putText(annotated, text, (x + 2, y), font, scale, color, thickness)


def _draw_recent_missing_people(annotated, detections, people, now, destination_labels, hold_sec: float = 1.2):
    visible = {det.get("person_id") for det in detections}
    for person_id, state in people.items():
        if person_id in visible:
            continue
        age = now - float(state.get("last_seen", 0))
        if age < 0 or age > hold_sec:
            continue
        box = state.get("last_box")
        if not box:
            continue
        x1, y1, x2, y2 = map(int, box)
        color = (135, 150, 170)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)
        label = _person_label({"person_id": person_id}, state, destination_labels)
        _draw_label_box(annotated, f"{label} hold", x1, max(22, y1 - 8), color)


def draw_person_annotations(
    frame,
    detections,
    people,
    mode: str,
    road_roi_norm,
    exit_lines_norm,
    destination_colors,
    destination_labels,
    show_road_roi: bool,
    show_direction_guides: bool,
    show_person_labels: bool,
    now: float,
    count_event_overlay_sec: float,
    show_count_debug: bool = False,
    forward_walkway_zones_norm=None,
    visible_exit_zones=None,
    count_debug=None,
):
    annotated = frame.copy()

    if show_road_roi or show_direction_guides:
        draw_direction_guides(
            annotated,
            road_roi_norm,
            exit_lines_norm,
            destination_colors,
            destination_labels,
            show_road_roi,
            show_direction_guides,
        )

    if show_count_debug:
        draw_count_debug_zones(
            annotated,
            forward_walkway_zones_norm,
            visible_exit_zones,
            destination_colors,
            destination_labels,
        )

    for det in detections:
        x1, y1, x2, y2 = map(int, det["box"])
        color = (44, 214, 255) if mode == "day" else (120, 255, 120)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        state = people.get(det["person_id"])
        label = _person_label(det, state, destination_labels) if show_person_labels else "Person"
        cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        draw_person_trail(annotated, state)
        if show_count_debug:
            draw_person_debug_label(annotated, det, state, (x1, y1, x2, y2), destination_labels)
        draw_count_event(annotated, state, (x1, y1, x2, y2), now, count_event_overlay_sec, destination_labels)
    if show_count_debug:
        draw_count_debug_panel(annotated, count_debug)
    return annotated


def draw_count_event(annotated, state, box, now: float, overlay_sec: float, destination_labels):
    if not state:
        return
    event = state.get("count_event")
    if not event:
        return
    age = now - float(event.get("ts", 0))
    if age < 0 or age > overlay_sec:
        return

    x1, y1, x2, y2 = box
    total = event.get("total")
    text = "COUNT"
    if total is not None:
        text = f"COUNT #{total}"
    color = (64, 255, 64)
    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
    cv2.putText(
        annotated,
        text,
        (x1, max(28, y1 - 30)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        color,
        2,
    )


def draw_vehicle_annotations(
    frame,
    detections,
    current_count: int,
    mode: str,
    show_road_roi: bool,
    road_roi_norm,
    vehicle_colors,
    vehicle_display_labels,
):
    annotated = frame.copy()
    if show_road_roi:
        cv2.polylines(annotated, [road_roi_pixels(annotated.shape, road_roi_norm)], True, (0, 220, 255), 2)

    for det in detections:
        x1, y1, x2, y2 = map(int, det["box"])
        vehicle_type = det["vehicle_type"]
        color = vehicle_colors.get(vehicle_type, (56, 189, 248))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = vehicle_display_labels.get(vehicle_type, "Vehicle")
        if det.get("track_key") is None:
            label = f"{label}?"
        cv2.putText(annotated, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.putText(
        annotated,
        f"Vehicle flow: {current_count}",
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.82,
        (255, 255, 255),
        2,
    )
    return annotated
