from __future__ import annotations

import asyncio
import concurrent.futures
import json
import queue as stdlib_queue
import time
from typing import Any

import websockets


async def video_ai_stream(
    websocket,
    inf_thread: Any,
    shutdown_event,
    traffic_history: list[dict],
    vehicle_history: list[dict],
    vehicle_mode: str = "vehicles",
):
    print("✅ 網頁已連線！")
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    send_lock = asyncio.Lock()

    async def safe_send(payload):
        async with send_lock:
            await websocket.send(json.dumps(payload))

    async def receive_controls():
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "set_mode":
                    inf_thread.set_analysis_mode(data.get("mode"))
                elif data.get("type") == "get_history":
                    mode = inf_thread._normalize_analysis_mode(data.get("mode"))
                    history = vehicle_history if mode == vehicle_mode else traffic_history
                    await safe_send({
                        "type": "history",
                        "analysis_mode": mode,
                        "history_scope": "full",
                        "history": list(history),
                        "time": time.strftime("%H:%M:%S"),
                        "ts_ms": int(time.time() * 1000),
                    })
        except websockets.exceptions.ConnectionClosed:
            pass

    def blocking_get():
        try:
            return inf_thread.result_q.get(timeout=1.0)
        except stdlib_queue.Empty:
            return None

    receiver_task = asyncio.create_task(receive_controls())
    try:
        while not shutdown_event.is_set():
            payload = await loop.run_in_executor(executor, blocking_get)
            if payload is None:
                continue
            await safe_send(payload)
    except websockets.exceptions.ConnectionClosed:
        print("⚠️ 網頁已關閉連線")
    except Exception as e:
        print(f"❌ WebSocket 錯誤: {e}")
    finally:
        receiver_task.cancel()
        executor.shutdown(wait=False)
