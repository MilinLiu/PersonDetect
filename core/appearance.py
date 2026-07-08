from __future__ import annotations

import cv2
import numpy as np


class AppearanceCache:
    def __init__(self):
        pass

    @staticmethod
    def _extract(crop: np.ndarray):
        if crop is None or crop.size == 0:
            return None
        try:
            h, w = crop.shape[:2]
            if h < 20 or w < 10:
                return None
            hsv = cv2.cvtColor(cv2.resize(crop, (48, 96)), cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            feat = hist.flatten().astype(np.float32)
            norm = np.linalg.norm(feat)
            return feat / norm if norm > 0 else feat
        except Exception:
            return None

    def extract(self, crop: np.ndarray):
        return self._extract(crop)

    @staticmethod
    def similarity(feat_a, feat_b) -> float:
        if feat_a is None or feat_b is None:
            return 0.0
        return float(np.dot(feat_a, feat_b))
