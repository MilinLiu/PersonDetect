from __future__ import annotations

import numpy as np


def warmup_model(model, imgsz: int, device):
    print("[Model] 執行 CUDA warm-up...")
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(3):
        model.predict(dummy, classes=[0], verbose=False, imgsz=imgsz, device=device)
    print("[Model] Warm-up 完成 ✅")
