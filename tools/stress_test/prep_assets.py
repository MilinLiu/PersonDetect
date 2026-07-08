"""從一段真實攝影機錄影，建立壓測用素材：
  1) plate.jpg   —— 乾淨街景底圖（時間中值，把移動的人濾掉）
  2) sprite_*.png —— YOLO 認得的人形剪影（帶柔邊 alpha）

用途：讓合成人流貼在「有真實脈絡」的底圖上，YOLO 才偵測得到；
底圖的 ROI/透視也與實際攝影機一致。

注意：輸出到 .tmp/stress_assets（預設，已被 gitignore）。真實街景不建議 commit。

範例：
  .venv/Scripts/python.exe tools/stress_test/prep_assets.py .tmp/screen_111532.mp4 --cam-frac 0.63
"""
from __future__ import annotations
import argparse, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT))

import cv2
import numpy as np


def resolve(path_value: str) -> Path:
    p = Path(path_value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="來源錄影（含真實街景）")
    ap.add_argument("--assets-dir", default=".tmp/stress_assets")
    ap.add_argument("--cam-frac", type=float, default=1.0,
                    help="攝影機畫面佔左邊的比例；儀表板錄影用 0.63，純攝影機用 1.0")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--plate-frames", type=int, default=48)
    ap.add_argument("--max-sprites", type=int, default=24)
    ap.add_argument("--sprite-conf", type=float, default=0.45)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--weights", default="yolo26s.pt")
    a = ap.parse_args()

    src = resolve(a.source)
    if not src.exists():
        raise SystemExit(f"source not found: {src}")
    out = resolve(a.assets_dir)
    out.mkdir(parents=True, exist_ok=True)
    W, H = a.width, a.height

    def cam(fr):
        return fr[:, : int(fr.shape[1] * a.cam_frac)]

    # ---- 1) 乾淨底圖：時間中值 ----
    cap = cv2.VideoCapture(str(src))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    want = set(np.linspace(0, max(1, n - 1), a.plate_frames).astype(int).tolist())
    samples, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i in want:
            samples.append(cv2.resize(cam(fr), (W, H)))
        i += 1
    cap.release()
    if not samples:
        raise SystemExit("no frames read from source")
    plate = np.median(np.stack(samples), axis=0).astype(np.uint8)
    cv2.imwrite(str(out / "plate.jpg"), plate)
    print(f"[plate] {len(samples)} frames -> {out/'plate.jpg'}")

    # ---- 2) 抽取人形素材 ----
    from ultralytics import YOLO
    model = YOLO(str(resolve(a.weights)))
    model.fuse()
    cap = cv2.VideoCapture(str(src))
    saved, i = 0, 0
    while True:
        ok, fr = cap.read()
        if not ok or saved >= a.max_sprites:
            break
        if i % 12 == 0:
            region = cam(fr)
            r = model.predict(region, conf=a.sprite_conf, imgsz=a.imgsz, classes=[0], verbose=False)[0]
            if r.boxes is not None:
                for b in r.boxes.xyxy.cpu().numpy().astype(int):
                    x1, y1, x2, y2 = b
                    w, h = x2 - x1, y2 - y1
                    if h < 70 or w < 20 or not (1.3 <= h / max(1, w) <= 4.2):
                        continue
                    crop = region[max(0, y1):y2, max(0, x1):x2].copy()
                    ch, cw = crop.shape[:2]
                    mask = np.zeros((ch, cw), np.uint8)
                    cv2.ellipse(mask, (cw // 2, int(ch * 0.5)), (int(cw * 0.48), int(ch * 0.5)), 0, 0, 360, 255, -1)
                    mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, cw * 0.06))
                    cv2.imwrite(str(out / f"sprite_{saved:02d}.png"), np.dstack([crop, mask]))
                    saved += 1
                    if saved >= a.max_sprites:
                        break
        i += 1
    cap.release()
    print(f"[sprites] extracted {saved} -> {out}")
    if saved == 0:
        print("[warn] 沒抽到人形素材：換一段有清楚真人的錄影，或調低 --sprite-conf。")


if __name__ == "__main__":
    main()
