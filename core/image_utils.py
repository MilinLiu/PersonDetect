from __future__ import annotations

import cv2
import numpy as np


def enhance_night_frame(frame: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = cv2.merge([clahe.apply(l), a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def estimate_brightness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))
