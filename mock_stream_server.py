import asyncio
import base64
import json
import time

import cv2
import numpy as np
import websockets


WIDTH, HEIGHT = 854, 480


def make_frame(step: int) -> str:
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    frame[:] = (26, 32, 39)

    road = np.array(
        [
            (int(0.02 * WIDTH), int(0.98 * HEIGHT)),
            (int(0.19 * WIDTH), int(0.36 * HEIGHT)),
            (int(0.72 * WIDTH), int(0.36 * HEIGHT)),
            (int(0.98 * WIDTH), int(0.98 * HEIGHT)),
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(frame, [road], (38, 45, 52))
    cv2.polylines(frame, [road], True, (70, 130, 190), 2)
    cv2.putText(frame, "MOCK CAMERA PREVIEW", (28, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220, 230, 240), 2)
    cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (28, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 230, 240), 2)

    paths = [
        ((0.48, 0.82), (0.08, 0.70), (45, 220, 190)),
        ((0.52, 0.80), (0.90, 0.70), (250, 190, 60)),
        ((0.50, 0.78), (0.50, 0.28), (80, 170, 250)),
    ]
    for i, (start, end, color) in enumerate(paths):
        progress = ((step + i * 24) % 72) / 72
        x = int((start[0] + (end[0] - start[0]) * progress) * WIDTH)
        y = int((start[1] + (end[1] - start[1]) * progress) * HEIGHT)
        cv2.circle(frame, (x, y), 12, color, -1)

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        raise RuntimeError("failed to encode mock frame")
    return base64.b64encode(buf).decode("ascii")


async def stream(websocket):
    history = []
    step = 0
    dorm = starbucks = sports = 0
    interval_start = {"dorm": 0, "starbucks": 0, "sports": 0}
    last_bucket = time.time()

    while True:
        if step % 36 == 0:
            dorm += 1
        if step % 54 == 0:
            starbucks += 1
        if step % 45 == 0:
            sports += 1

        counts = {"dorm": dorm, "starbucks": starbucks, "sports": sports}
        interval_counts = {key: counts[key] - interval_start[key] for key in counts}
        assigned_total = sum(counts.values())
        pending = 1 + (step % 3 == 0)
        total = assigned_total + pending
        dominant = max(counts, key=counts.get) if total else "none"
        if len({value for value in counts.values() if value == max(counts.values())}) > 1:
            dominant = "balanced"

        now = time.time()
        if now - last_bucket >= 10:
            history.append(
                {
                    "time": time.strftime("%H:%M:%S"),
                    "count": sum(interval_counts.values()),
                    "total": total,
                    "current": 2 + (step % 3),
                    "interval_to_dorm": interval_counts["dorm"],
                    "interval_to_starbucks": interval_counts["starbucks"],
                    "interval_to_sports": interval_counts["sports"],
                    "to_dorm": dorm,
                    "to_starbucks": starbucks,
                    "to_sports": sports,
                    "dominant_destination": dominant,
                    "peak": 4,
                }
            )
            history = history[-20:]
            interval_start = counts.copy()
            last_bucket = now

        payload = {
            "image": make_frame(step),
            "current_count": 2 + (step % 3),
            "total_count": total,
            "detected_total_count": total + 1,
            "assigned_destination_count": assigned_total,
            "pending_destination_count": pending,
            "interval_count": sum(interval_counts.values()),
            "to_dorm_count": dorm,
            "to_starbucks_count": starbucks,
            "to_sports_count": sports,
            "destination_counts": counts,
            "interval_destination_counts": interval_counts,
            "dominant_destination": dominant,
            "peak_count": 4,
            "mode": "day",
            "brightness": 82.5,
            "alert": "系統運行中",
            "alert_active": False,
            "alert_threshold": 6,
            "history": history,
            "time": time.strftime("%H:%M:%S"),
            "ts_ms": int(time.time() * 1000),
        }
        await websocket.send(json.dumps(payload))
        step += 1
        await asyncio.sleep(0.25)


async def main():
    async with websockets.serve(stream, "127.0.0.1", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
