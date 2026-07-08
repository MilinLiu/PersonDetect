
import argparse
import math
import os
import random
from pathlib import Path
from typing import List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent
LOCAL_TMP_DIR = BASE_DIR / ".tmp"
LOCAL_TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMP", str(LOCAL_TMP_DIR))
os.environ.setdefault("TEMP", str(LOCAL_TMP_DIR))
os.environ.setdefault("YOLO_CONFIG_DIR", str(LOCAL_TMP_DIR / "Ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(LOCAL_TMP_DIR / "matplotlib"))

import cv2
import numpy as np

PERSON_EXT = ".png"


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def parse_points(value: str) -> List[Tuple[float, float]]:
    points = []
    for pair in value.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        try:
            x, y = [float(v.strip()) for v in pair.split(",", 1)]
        except Exception as exc:
            raise argparse.ArgumentTypeError(
                "Polygon points must look like x,y;x,y;x,y"
            ) from exc
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise argparse.ArgumentTypeError("Polygon coordinates must be between 0 and 1")
        points.append((x, y))
    if len(points) < 3:
        raise argparse.ArgumentTypeError("A polygon needs at least 3 points")
    return points


def point_in_polygon_norm(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        intersects = (yi > y) != (yj > y)
        if intersects:
            x_cross = (xj - xi) * (y - yi) / max(1e-9, yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def alpha_blend(bg: np.ndarray, fg_bgra: np.ndarray, x: int, y: int) -> None:
    """把 BGRA 前景疊到 BGR 背景，超出畫面的部分自動裁切。"""
    h, w = fg_bgra.shape[:2]
    H, W = bg.shape[:2]

    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    if x1 >= x2 or y1 >= y2:
        return

    fx1, fy1 = x1 - x, y1 - y
    fx2, fy2 = fx1 + (x2 - x1), fy1 + (y2 - y1)

    fg = fg_bgra[fy1:fy2, fx1:fx2, :3].astype(np.float32)
    alpha = fg_bgra[fy1:fy2, fx1:fx2, 3:4].astype(np.float32) / 255.0
    roi = bg[y1:y2, x1:x2].astype(np.float32)
    bg[y1:y2, x1:x2] = (fg * alpha + roi * (1 - alpha)).astype(np.uint8)


def make_soft_mask(h: int, w: int) -> np.ndarray:
    """沒有 segmentation 時使用柔邊橢圓遮罩，避免硬切方框太明顯。"""
    mask = np.zeros((h, w), dtype=np.uint8)
    center = (w // 2, int(h * 0.52))
    axes = (max(2, int(w * 0.46)), max(2, int(h * 0.50)))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.5, w * 0.05), sigmaY=max(1.5, h * 0.04))
    return mask


def crop_to_bgra(frame: np.ndarray, box: Tuple[int, int, int, int], mask: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = box
    x1, y1 = clamp(x1, 0, W - 1), clamp(y1, 0, H - 1)
    x2, y2 = clamp(x2, x1 + 1, W), clamp(y2, y1 + 1, H)
    crop = frame[y1:y2, x1:x2].copy()
    h, w = crop.shape[:2]
    if h < 25 or w < 10:
        return None

    if mask is None:
        alpha = make_soft_mask(h, w)
    else:
        alpha = mask[y1:y2, x1:x2].copy()
        if alpha.shape[:2] != (h, w):
            alpha = cv2.resize(alpha, (w, h))
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=1.4, sigmaY=1.4)

    return np.dstack([crop, alpha])


def save_sprite(sprite: np.ndarray, out_dir: str, idx: int) -> str:
    # 去除透明邊界
    a = sprite[:, :, 3]
    ys, xs = np.where(a > 15)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("empty alpha")
    x1, x2 = xs.min(), xs.max() + 1
    y1, y2 = ys.min(), ys.max() + 1
    sprite = sprite[y1:y2, x1:x2]
    out_path = os.path.join(out_dir, f"person_{idx:04d}{PERSON_EXT}")
    cv2.imwrite(out_path, sprite)
    return out_path


def create_fallback_sprites(out_dir: str, count: int = 12) -> int:
    ensure_dir(out_dir)
    colors = [
        (48, 87, 214),
        (48, 145, 86),
        (202, 92, 52),
        (115, 78, 173),
        (56, 130, 170),
        (188, 70, 112),
    ]
    for idx in range(count):
        h = random.randint(95, 135)
        w = random.randint(34, 52)
        sprite = np.zeros((h, w, 4), dtype=np.uint8)
        body = colors[idx % len(colors)]
        skin = (72, 118, 184)
        dark = (42, 44, 48)
        cx = w // 2
        head_r = max(7, w // 5)
        cv2.ellipse(sprite, (cx, head_r + 6), (head_r, head_r + 2), 0, 0, 360, (*skin, 255), -1)
        cv2.ellipse(sprite, (cx, int(h * 0.48)), (max(8, w // 4), int(h * 0.24)), 0, 0, 360, (*body, 255), -1)
        hip_y = int(h * 0.68)
        foot_y = h - 7
        cv2.line(sprite, (cx - 5, hip_y), (cx - w // 5, foot_y), (*dark, 255), max(4, w // 9))
        cv2.line(sprite, (cx + 5, hip_y), (cx + w // 5, foot_y), (*dark, 255), max(4, w // 9))
        cv2.line(sprite, (cx - w // 5, int(h * 0.37)), (cx - w // 2 + 3, int(h * 0.58)), (*body, 235), max(3, w // 12))
        cv2.line(sprite, (cx + w // 5, int(h * 0.37)), (cx + w // 2 - 3, int(h * 0.58)), (*body, 235), max(3, w // 12))
        alpha = sprite[:, :, 3]
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=0.45, sigmaY=0.45)
        sprite[:, :, 3] = alpha
        save_sprite(sprite, out_dir, idx)
    return count


def extract_with_yolo(input_path: str, out_dir: str, max_sprites: int, sample_every: int, conf: float) -> int:
    try:
        from ultralytics import YOLO
    except Exception as e:
        print("[WARN] 沒有安裝 ultralytics，改用 OpenCV HOG 偵測。")
        return -1

    # Prefer the local project model so the script works without downloading.
    candidates = [
        Path(input_path).resolve().parent / "yolo26s.pt",
        Path("yolo26s.pt"),
        Path("yolov8n-seg.pt"),
        Path("yolov8n.pt"),
    ]
    model = None
    for candidate in candidates:
        try:
            model = YOLO(str(candidate))
            break
        except Exception:
            continue
    if model is None:
        print("[WARN] 無法載入 YOLO 模型，改用 OpenCV HOG 偵測。")
        return -1

    cap = cv2.VideoCapture(input_path)
    idx = 0
    saved = 0
    while cap.isOpened() and saved < max_sprites:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every != 0:
            idx += 1
            continue

        results = model.predict(frame, conf=conf, classes=[0], verbose=False)
        for r in results:
            boxes = [] if r.boxes is None else r.boxes.xyxy.cpu().numpy().astype(int)
            masks = None
            if getattr(r, "masks", None) is not None and r.masks is not None:
                masks = r.masks.data.cpu().numpy()
            for i, b in enumerate(boxes):
                x1, y1, x2, y2 = b.tolist()
                # 過濾比例不像人的框
                bw, bh = x2 - x1, y2 - y1
                if bh < 30 or bw < 8 or bh / max(1, bw) < 1.1:
                    continue
                mask = None
                if masks is not None and i < len(masks):
                    m = (masks[i] * 255).astype(np.uint8)
                    m = cv2.resize(m, (frame.shape[1], frame.shape[0]))
                    mask = m
                sprite = crop_to_bgra(frame, (x1, y1, x2, y2), mask)
                if sprite is None:
                    continue
                try:
                    save_sprite(sprite, out_dir, saved)
                    saved += 1
                except Exception:
                    pass
                if saved >= max_sprites:
                    break
        idx += 1
    cap.release()
    return saved


def extract_with_hog(input_path: str, out_dir: str, max_sprites: int, sample_every: int) -> int:
    if not hasattr(cv2, "HOGDescriptor") or not hasattr(cv2, "HOGDescriptor_getDefaultPeopleDetector"):
        print("[WARN] OpenCV HOG 不可用，無法抽取真人素材。")
        return -1

    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    cap = cv2.VideoCapture(input_path)
    idx = 0
    saved = 0
    while cap.isOpened() and saved < max_sprites:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every != 0:
            idx += 1
            continue

        # HOG 在小人/監視器高角度會比較不準，但不需額外套件。
        small = frame
        boxes, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        for (x, y, w, h), weight in zip(boxes, weights):
            if weight < 0.25:
                continue
            pad_x, pad_y = int(w * 0.08), int(h * 0.04)
            sprite = crop_to_bgra(frame, (x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y), None)
            if sprite is None:
                continue
            try:
                save_sprite(sprite, out_dir, saved)
                saved += 1
            except Exception:
                pass
            if saved >= max_sprites:
                break
        idx += 1
    cap.release()
    return saved


def load_sprites(sprites_dir: str) -> List[np.ndarray]:
    paths = sorted(Path(sprites_dir).glob(f"*{PERSON_EXT}"))
    sprites = []
    for p in paths:
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is None:
            continue
        if img.ndim != 3 or img.shape[2] != 4:
            continue
        if img.shape[0] < 20 or img.shape[1] < 8:
            continue
        sprites.append(img)
    return sprites


def augment_sprite(sprite: np.ndarray) -> np.ndarray:
    sp = sprite.copy()
    if random.random() < 0.5:
        sp = cv2.flip(sp, 1)
    # 亮度/對比微調，讓複製人比較不明顯。
    rgb = sp[:, :, :3].astype(np.float32)
    alpha = sp[:, :, 3]
    contrast = random.uniform(0.88, 1.12)
    brightness = random.uniform(-18, 18)
    rgb = np.clip(rgb * contrast + brightness, 0, 255).astype(np.uint8)
    sp[:, :, :3] = rgb
    sp[:, :, 3] = alpha
    return sp


class Agent:
    def __init__(self, W, H, roi_top, roi_bottom, sprites, direction, walkable_polygon=None):
        self.W = W
        self.H = H
        self.roi_top = int(H * roi_top)
        self.roi_bottom = int(H * roi_bottom)
        self.sprites = sprites
        self.direction_mode = direction
        self.walkable_polygon = walkable_polygon
        self.reset(initial=True)

    def choose_y_base(self):
        for _ in range(80):
            y_base = random.randint(self.roi_top, self.roi_bottom)
            if self.walkable_polygon is None:
                return y_base
            nx = random.uniform(0.03, 0.97)
            ny = y_base / max(1, self.H)
            if point_in_polygon_norm(nx, ny, self.walkable_polygon):
                return y_base
        return random.randint(self.roi_top, self.roi_bottom)

    def reset(self, initial=False):
        self.sprite = augment_sprite(random.choice(self.sprites))
        self.y_base = self.choose_y_base()
        depth = (self.y_base - self.roi_top) / max(1, (self.roi_bottom - self.roi_top))
        self.scale = random.uniform(0.45, 0.85) + depth * random.uniform(0.35, 0.75)
        self.scale = max(0.25, self.scale)
        self.speed = random.uniform(0.8, 3.8) * (0.6 + depth * 0.9)
        if self.direction_mode == "left":
            self.dir = -1
        elif self.direction_mode == "right":
            self.dir = 1
        else:
            self.dir = random.choice([-1, 1])
        self.x = -random.uniform(50, 260) if self.dir > 0 else self.W + random.uniform(50, 260)
        if initial:
            self.x += random.uniform(-self.W * 0.6, self.W * 0.6)
        self.phase = random.random() * math.tau
        self.opacity = random.uniform(0.88, 1.0)

    def step(self):
        self.x += self.dir * self.speed
        self.phase += 0.08
        if self.x < -250 or self.x > self.W + 250:
            self.reset(initial=False)

    def draw_shadow(self, frame, x, y, w, h):
        shadow_w = int(w * 0.55)
        shadow_h = max(3, int(h * 0.055))
        sx = int(x + w * 0.5)
        sy = int(y + h * 0.96)
        overlay = frame.copy()
        cv2.ellipse(overlay, (sx, sy), (shadow_w // 2, shadow_h), 0, 0, 360, (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    def draw(self, frame):
        h0, w0 = self.sprite.shape[:2]
        target_h = int(h0 * self.scale)
        target_w = int(w0 * self.scale)
        if target_h < 12 or target_w < 5:
            return
        sp = cv2.resize(self.sprite, (target_w, target_h), interpolation=cv2.INTER_AREA)
        sp[:, :, 3] = np.clip(sp[:, :, 3].astype(np.float32) * self.opacity, 0, 255).astype(np.uint8)

        bob = int(math.sin(self.phase) * max(1, target_h * 0.015))
        x = int(self.x)
        y = int(self.y_base - target_h + bob)
        if self.walkable_polygon is not None:
            foot_x = (x + target_w * 0.5) / max(1, self.W)
            foot_y = (y + target_h) / max(1, self.H)
            if not point_in_polygon_norm(foot_x, foot_y, self.walkable_polygon):
                return
        self.draw_shadow(frame, x, y, target_w, target_h)
        alpha_blend(frame, sp, x, y)


def generate_video(input_path: str, output_path: str, sprites: List[np.ndarray], people: int, roi: Tuple[float, float], direction: str, max_seconds: float, walkable_polygon=None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"無法開啟影片：{input_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limit_frames = total_frames
    if max_seconds and max_seconds > 0:
        limit_frames = min(limit_frames or int(max_seconds * fps), int(max_seconds * fps))

    if W <= 0 or H <= 0:
        cap.release()
        raise RuntimeError("Video has invalid dimensions")

    ensure_dir(str(Path(output_path).parent or "."))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (W, H))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot create output video: {output_path}")

    agents = [Agent(W, H, roi[0], roi[1], sprites, direction, walkable_polygon) for _ in range(people)]
    frame_idx = 0
    progress_every = max(1, int(fps * 5))
    print(f"開始產生影片：{people} 人，長度約 {limit_frames / fps:.0f} 秒，輸出到 {output_path}")
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if limit_frames and frame_idx >= limit_frames:
            break

        for agent in agents:
            agent.step()
            agent.draw(frame)
        writer.write(frame)
        frame_idx += 1
        if frame_idx % progress_every == 0:
            print(f"進度：{frame_idx / fps:.0f} 秒 / {limit_frames / fps:.0f} 秒")

    writer.release()
    cap.release()


def parse_roi(value: str) -> Tuple[float, float]:
    try:
        top, bottom = [float(v.strip()) for v in value.split(",", 1)]
    except Exception as exc:
        raise argparse.ArgumentTypeError("ROI must be two numbers like 0.45,0.95") from exc
    if not 0 <= top < bottom <= 1:
        raise argparse.ArgumentTypeError("ROI numbers must satisfy 0 <= top < bottom <= 1")
    return top, bottom


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract person sprites and synthesize a crowd into a video.")
    parser.add_argument("--input", default="1010.mp4", help="Input video path")
    parser.add_argument("--output", default="crowd_test_1010_60s.mp4", help="Output video path")
    parser.add_argument("--sprites-dir", default="crowd_test_sprites", help="Folder for extracted person PNG sprites")
    parser.add_argument("--people", type=int, default=30, help="Number of synthetic people")
    parser.add_argument("--max-seconds", type=float, default=60, help="Limit output length; 0 means full input video")
    parser.add_argument("--roi", type=parse_roi, default=(0.45, 0.95), help="Walking area as top,bottom ratios")
    parser.add_argument(
        "--walkable-polygon",
        type=parse_points,
        default=parse_points("0.02,0.98;0.19,0.36;0.72,0.36;0.98,0.98"),
        help="Normalized polygon where synthetic feet are allowed, e.g. x,y;x,y;x,y",
    )
    parser.add_argument("--direction", choices=["left", "right", "both"], default="both", help="Walking direction")
    parser.add_argument("--extract", action="store_true", help="Extract sprites before generating the video")
    parser.add_argument("--no-auto-extract", action="store_true", help="Do not auto-extract when the sprites folder is empty")
    parser.add_argument("--allow-fallback-sprites", action="store_true", help="Allow generated placeholder people when real sprites cannot be extracted")
    parser.add_argument("--max-sprites", type=int, default=80, help="Maximum sprites to extract")
    parser.add_argument("--sample-every", type=int, default=10, help="Sample every N frames during extraction")
    parser.add_argument("--conf", type=float, default=0.35, help="YOLO confidence threshold")
    parser.add_argument("--hog-only", action="store_true", help="Use OpenCV HOG instead of YOLO for extraction")
    return parser


def resolve_from_script_dir(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(Path(__file__).resolve().parent / path)


def generate_video(input_path: str, output_path: str, sprites: List[np.ndarray], people: int, roi: Tuple[float, float], direction: str, max_seconds: float, walkable_polygon=None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limit_frames = total_frames
    if max_seconds and max_seconds > 0:
        limit_frames = min(limit_frames or int(max_seconds * fps), int(max_seconds * fps))

    if W <= 0 or H <= 0:
        cap.release()
        raise RuntimeError("Video has invalid dimensions")

    ensure_dir(str(Path(output_path).parent or "."))
    writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot create output video: {output_path}")

    agents = [Agent(W, H, roi[0], roi[1], sprites, direction, walkable_polygon) for _ in range(people)]
    frame_idx = 0
    progress_every = max(1, int(fps * 5))
    total_seconds = limit_frames / fps if limit_frames else 0
    print(f"Rendering crowd video: {people} people, about {total_seconds:.0f}s", flush=True)
    print(f"Output: {output_path}", flush=True)

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if limit_frames and frame_idx >= limit_frames:
            break

        for agent in agents:
            agent.step()
            agent.draw(frame)
        writer.write(frame)
        frame_idx += 1

        if frame_idx % progress_every == 0:
            print(f"Progress: {frame_idx / fps:.0f}s / {total_seconds:.0f}s", flush=True)

    writer.release()
    cap.release()


def main() -> None:
    args = build_parser().parse_args()
    args.input = resolve_from_script_dir(args.input)
    args.output = resolve_from_script_dir(args.output)
    args.sprites_dir = resolve_from_script_dir(args.sprites_dir)
    if not Path(args.input).exists():
        raise RuntimeError(f"找不到輸入影片：{args.input}")
    args.sample_every = max(1, args.sample_every)
    ensure_dir(args.sprites_dir)

    sprites = load_sprites(args.sprites_dir)
    should_extract = args.extract or (not sprites and not args.no_auto_extract)
    if should_extract:
        if args.hog_only:
            saved = extract_with_hog(args.input, args.sprites_dir, args.max_sprites, args.sample_every)
        else:
            saved = extract_with_yolo(args.input, args.sprites_dir, args.max_sprites, args.sample_every, args.conf)
            if saved < 0:
                saved = extract_with_hog(args.input, args.sprites_dir, args.max_sprites, args.sample_every)
            if saved <= 0:
                if args.allow_fallback_sprites:
                    print("[WARN] 沒有偵測到可用真人素材，改用內建假人素材。")
                    saved = create_fallback_sprites(args.sprites_dir, min(args.max_sprites, 12))
                else:
                    raise RuntimeError(
                        "No real person sprites could be extracted. Use a source video with "
                        "clear real people, lower --conf, or pass --allow-fallback-sprites "
                        "only for visual smoke tests."
                    )
        print(f"Extracted {saved} sprite(s) into {args.sprites_dir}")
        sprites = load_sprites(args.sprites_dir)

    if not sprites:
        if args.allow_fallback_sprites:
            print("[WARN] 沒有現成人像素材，建立內建假人素材。")
            create_fallback_sprites(args.sprites_dir, min(args.max_sprites, 12))
            sprites = load_sprites(args.sprites_dir)
        else:
            raise RuntimeError(
                "No real person sprites found. Run with --extract and a video containing "
                "clear real people, or use --allow-fallback-sprites only for smoke tests."
            )

    generate_video(
        input_path=args.input,
        output_path=args.output,
        sprites=sprites,
        people=max(1, args.people),
        roi=args.roi,
        direction=args.direction,
        max_seconds=args.max_seconds,
        walkable_polygon=args.walkable_polygon,
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
