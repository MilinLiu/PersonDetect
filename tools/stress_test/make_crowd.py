"""產生一段「已知真值」的高密度人流壓測影片。

- 指定 N 個不同的人，各自穿越道路 ROI 一次後永久離場（不重生）→ 真值總人數 = N。
- 出場時間錯開 → 高密度並發，壓測大量目標。
- ROI／出口由設定檔讀入（預設 configs/home_gate.yaml），所以人流會跟著實際 ROI 走，
  腳點保證落在 ROI 內，計數（roi_entry）才會觸發。
- 同時輸出 <out>.gt.json 記錄真值，供 score.py 比對。

範例：
  .venv/Scripts/python.exe tools/stress_test/make_crowd.py --people 40 --seconds 28
"""
from __future__ import annotations
import argparse, json, math, random, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np
from core.config import load_config


def resolve(path_value: str) -> Path:
    p = Path(path_value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def x_range_at(y, roi):
    """ROI 多邊形在高度 y（normalized）處的可行走 x 範圍。"""
    xs = []
    n = len(roi)
    for i in range(n):
        x1, y1 = roi[i]
        x2, y2 = roi[(i + 1) % n]
        if min(y1, y2) <= y <= max(y1, y2) and abs(y2 - y1) > 1e-9:
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    if len(xs) < 2:
        return None
    return min(xs), max(xs)


def alpha_blend(bg, fg, x, y):
    h, w = fg.shape[:2]
    H, W = bg.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    if x1 >= x2 or y1 >= y2:
        return
    fx1, fy1 = x1 - x, y1 - y
    fx2, fy2 = fx1 + (x2 - x1), fy1 + (y2 - y1)
    f = fg[fy1:fy2, fx1:fx2, :3].astype(np.float32)
    al = fg[fy1:fy2, fx1:fx2, 3:4].astype(np.float32) / 255.0
    roi = bg[y1:y2, x1:x2].astype(np.float32)
    bg[y1:y2, x1:x2] = (f * al + roi * (1 - al)).astype(np.uint8)


def build_people(n, fps, dur_s, nsprites, roi, seed):
    rng = random.Random(seed)
    ys = [p[1] for p in roi]
    y_top, y_bot = min(ys), max(ys)
    last = int(fps * (dur_s - 6))
    people, gt = [], {"dorm": 0, "starbucks": 0, "sports": 0}
    for _ in range(n):
        spawn = rng.randint(0, max(1, last))
        dur = int(fps * rng.uniform(4.5, 7.5))
        sidx = rng.randrange(nsprites)
        if rng.random() < 0.7:  # 水平穿越
            d = rng.uniform(0.42, 0.98)
            ny = y_top + d * (y_bot - y_top)
            rng_x = x_range_at(ny, roi)
            if rng_x is None:
                continue
            xl, xr = rng_x
            l2r = rng.random() < 0.5
            xs, xe = (xl - 0.05, xr + 0.05) if l2r else (xr + 0.05, xl - 0.05)
            dirn = "starbucks" if l2r else "dorm"
            path = ("h", d, ny, xs, xe)
        else:  # 往前（上方 sports 出口）
            d0, d1 = rng.uniform(0.8, 0.98), rng.uniform(0.34, 0.46)
            nx = rng.uniform(0.4, 0.6)
            dirn = "sports"
            path = ("v", nx, d0, d1, y_top, y_bot)
        gt[dirn] += 1
        people.append({"spawn": spawn, "dur": dur, "sidx": sidx, "path": path})
    return people, gt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets-dir", default=".tmp/stress_assets")
    ap.add_argument("--config", default="configs/home_gate.yaml", help="讀 ROI/出口用")
    ap.add_argument("--people", type=int, default=40)
    ap.add_argument("--seconds", type=float, default=28)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=".tmp/stress_out/crowd.mp4")
    a = ap.parse_args()

    assets = resolve(a.assets_dir)
    plate = cv2.imread(str(assets / "plate.jpg"))
    if plate is None:
        raise SystemExit(f"找不到 plate.jpg（先跑 prep_assets.py）：{assets}")
    sprites = [cv2.imread(str(p), cv2.IMREAD_UNCHANGED) for p in sorted(assets.glob("sprite_*.png"))]
    sprites = [s for s in sprites if s is not None and s.ndim == 3 and s.shape[2] == 4]
    if not sprites:
        raise SystemExit("找不到 sprite_*.png（先跑 prep_assets.py）")

    cfg = load_config(a.config)
    roi = [tuple(pt) for pt in cfg["zones"]["road_roi"]]

    H, W = plate.shape[:2]
    people, gt = build_people(a.people, a.fps, a.seconds, len(sprites), roi, a.seed)
    total = int(a.fps * a.seconds)
    out = resolve(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    if not writer.isOpened():
        raise SystemExit(f"cannot open writer: {out}")

    peak = 0
    for f in range(total):
        frame = plate.copy()
        active = 0
        for p in people:
            k = f - p["spawn"]
            if k < 0 or k > p["dur"]:
                continue
            active += 1
            u = k / max(1, p["dur"])
            bob = math.sin(u * math.pi * 8) * 0.004
            pth = p["path"]
            if pth[0] == "h":
                _, d, ny, xs, xe = pth
                nx = xs + (xe - xs) * u
                fy = ny + bob
            else:
                _, nx, d0, d1, y_top, y_bot = pth
                d = d0 + (d1 - d0) * u
                fy = y_top + d * (y_bot - y_top) + bob
            th = int(H * (0.10 + 0.16 * d))
            sp0 = sprites[p["sidx"]]
            sc = th / sp0.shape[0]
            tw = max(6, int(sp0.shape[1] * sc))
            sp = cv2.resize(sp0, (tw, th), interpolation=cv2.INTER_AREA)
            fx, fyp = int(nx * W), int(fy * H)
            cv2.ellipse(frame, (fx, fyp), (max(4, tw // 3), max(2, th // 20)), 0, 0, 360, (35, 35, 35), -1)
            alpha_blend(frame, sp, fx - tw // 2, fyp - th)
        peak = max(peak, active)
        cv2.putText(frame, f"t={f/a.fps:4.1f}s  on-screen={active}", (14, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        writer.write(frame)
    writer.release()

    gt_out = {"total_people": a.people, "peak_on_screen": peak, "by_direction": gt,
              "video": str(out), "fps": a.fps, "seconds": a.seconds, "seed": a.seed,
              "note": "by_direction 為產生時的意圖方向（近似），主要真值為 total_people。"}
    out.with_suffix(".gt.json").write_text(json.dumps(gt_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gt_out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
