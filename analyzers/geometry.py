from __future__ import annotations

import cv2
import numpy as np


def box_center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def box_iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def merge_feature(old_feat, new_feat):
    if new_feat is None:
        return old_feat
    if old_feat is None:
        return new_feat
    merged = (old_feat * 0.75 + new_feat * 0.25).astype(np.float32)
    norm = np.linalg.norm(merged)
    return merged / norm if norm > 0 else merged


def norm_point(point, frame_shape):
    h, w = frame_shape[:2]
    return (point[0] / max(1, w), point[1] / max(1, h))


def road_roi_pixels(frame_shape, road_roi_norm):
    h, w = frame_shape[:2]
    return np.array([(int(x * w), int(y * h)) for x, y in road_roi_norm], dtype=np.int32)


def norm_to_pixel(point_norm, frame_shape):
    h, w = frame_shape[:2]
    return (int(point_norm[0] * w), int(point_norm[1] * h))


def is_near_road_point(point, frame_shape, road_roi_norm, margin_ratio: float) -> bool:
    h, w = frame_shape[:2]
    roi = road_roi_pixels(frame_shape, road_roi_norm)
    margin_px = min(h, w) * margin_ratio
    distance = cv2.pointPolygonTest(roi, (float(point[0]), float(point[1])), True)
    return distance >= -margin_px


def is_forward_walkway_norm(point_norm, walkway_zones) -> bool:
    nx, ny = point_norm
    for x1, y1, x2, y2 in walkway_zones:
        if x1 <= nx <= x2 and y1 <= ny <= y2:
            return True
    return False


def foot_point(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, y2)


def zone_probe_points(box):
    x1, y1, x2, y2 = box
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    cx = (x1 + x2) / 2.0
    return [
        (cx, y2),
        (x1 + width * 0.35, y2),
        (x1 + width * 0.65, y2),
        (cx, y1 + height * 0.88),
        (cx, y1 + height * 0.72),
    ]


def box_zone_hit(box, frame_shape, road_roi_norm, margin_ratio, walkway_zones):
    foot = foot_point(box)
    foot_norm = norm_point(foot, frame_shape)
    in_road = False
    in_forward_walkway = is_forward_walkway_norm(foot_norm, walkway_zones)
    best_road_norm = foot_norm

    for point in zone_probe_points(box):
        point_norm = norm_point(point, frame_shape)
        if is_near_road_point(point, frame_shape, road_roi_norm, margin_ratio):
            in_road = True
            best_road_norm = point_norm
        if is_forward_walkway_norm(point_norm, walkway_zones):
            in_forward_walkway = True

    return foot, foot_norm, in_road, in_forward_walkway, best_road_norm


def orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a, b, c, eps=1e-9):
    return (
        min(a[0], c[0]) - eps <= b[0] <= max(a[0], c[0]) + eps
        and min(a[1], c[1]) - eps <= b[1] <= max(a[1], c[1]) + eps
    )


def segments_intersect(a, b, c, d, eps=1e-9):
    if a is None or b is None or c is None or d is None:
        return False
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if abs(o1) <= eps and on_segment(a, c, b, eps):
        return True
    if abs(o2) <= eps and on_segment(a, d, b, eps):
        return True
    if abs(o3) <= eps and on_segment(c, a, d, eps):
        return True
    if abs(o4) <= eps and on_segment(c, b, d, eps):
        return True
    return (o1 > eps) != (o2 > eps) and (o3 > eps) != (o4 > eps)


def point_to_segment_distance(point, seg_start, seg_end):
    px, py = point
    ax, ay = seg_start
    bx, by = seg_end
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    length_sq = vx * vx + vy * vy
    if length_sq <= 0:
        return float(((px - ax) ** 2 + (py - ay) ** 2) ** 0.5)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length_sq))
    proj = (ax + t * vx, ay + t * vy)
    return float(((px - proj[0]) ** 2 + (py - proj[1]) ** 2) ** 0.5)


def average_path_norm(points):
    if not points:
        return None
    xs = [point[2][0] for point in points]
    ys = [point[2][1] for point in points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))
