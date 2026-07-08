from __future__ import annotations

import concurrent.futures
import socket
import subprocess

import cv2
import torch


def preflight_check(model_device):
    print("[Check] 執行啟動前檢查...")

    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.decode(errors="ignore").splitlines()[0]
            print(f"[Check] 系統 FFMPEG ✅ ({version_line[:60]})")
        else:
            print("[Check] 系統 FFMPEG 未安裝（使用 OpenCV 內建版本）✅")
    except FileNotFoundError:
        print("[Check] 系統 FFMPEG 未在 PATH（使用 OpenCV 內建版本）✅")
    except Exception:
        print("[Check] 系統 FFMPEG 未在 PATH（使用 OpenCV 內建版本）✅")

    try:
        print(f"[Check] OpenCV 版本：{cv2.__version__} ✅")
    except Exception as e:
        print(f"[Check] OpenCV 異常：{e}")

    try:
        if torch.cuda.is_available():
            print(f"[Check] CUDA 可用 ✅ (GPU: {torch.cuda.get_device_name(0)})")
        else:
            print("[Check] CUDA 不可用（將使用 CPU）")
    except Exception:
        print("[Check] CUDA 檢查失敗")

    print(f"[Check] 推理裝置：{model_device}\n")
    print("[Check] 啟動前檢查完成\n")


def find_camera_ip(base_ip: str = "192.168.0.", port: int = 554) -> str | None:
    print(f"[Scan] 掃描 {base_ip}1~254 port {port}...")

    def check(ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        r = s.connect_ex((ip, port))
        s.close()
        return ip if r == 0 else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as ex:
        for ip in ex.map(check, [f"{base_ip}{i}" for i in range(1, 255)]):
            if ip:
                print(f"[Scan] 找到攝影機：{ip}")
                return ip

    return None


def cleanup_resources(vcap=None, inf_thread=None, server=None):
    print("\n[Cleanup] 關閉中...")

    if inf_thread:
        inf_thread.stop()
        inf_thread.join(timeout=5.0)
        if inf_thread.is_alive():
            print("[Cleanup] ⚠️ 推理執行緒逾時，繼續關閉")
        else:
            print("[Cleanup] 推理執行緒已停止")

    if vcap:
        vcap.stop()
        print("[Cleanup] 攝影機已關閉")

    if server:
        try:
            server.close()
        except Exception:
            pass
        print("[Cleanup] WebSocket 伺服器已關閉")

    print("[Cleanup] 完成 ✅")
