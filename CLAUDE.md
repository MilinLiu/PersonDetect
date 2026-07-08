# CLAUDE.md

校園路口人流／車流監控系統：RTSP 攝影機 → YOLO 偵測 + ByteTrack 追蹤 + 輕量 ReID → ROI／出口線判方向 → WebSocket 推到網頁儀表板 + CSV。未來要擴充成「校園行為辨識系統」（人流／教室行為／行車安全／打架），詳見 `docs/system_architecture.md`。

使用者偏好**繁體中文**說明與 UI。

## 進入點與關鍵路徑

- 主程式：`persondetectandfield.py`（`InferenceThread` = 追蹤 + 計數核心；`main()` = 組裝）
- 前端：`網頁監控.html`（連 `ws://localhost:8765`）；老師端：`teacher_remote_viewer.html`
- 設定讀取：`core/config.py`（`DEFAULT_CONFIG` + YAML deep-merge）
- 場景設定：`configs/home_gate.yaml`、覆蓋檔 `configs/home_gate.local.yaml`
- 模型：`yolo26s.pt`（有 CUDA 用 GPU，否則 CPU）
- 純計算模組：`analyzers/geometry.py`（ROI／線段交會／IoU）、`analyzers/vehicle_flow.py`、`analyzers/visualization.py`
- 週邊：`core/camera_source.py`（RTSP 讀幀重連）、`core/appearance.py`（ReID 特徵）、`server/websocket_server.py`、`server/traffic_logger.py`
- 回放測試：`tools/replay_video.py`；venv：`.venv/Scripts/python.exe`

## 怎麼跑

```bat
run_monitor.bat                       # 啟動後端（會自動選 .local.yaml，見下）
```

```bash
# 固定影片回放（改計數邏輯必用；務必指定跟 live 相同的設定檔）
.venv/Scripts/python.exe tools/replay_video.py <video.mp4> --config configs/home_gate.local.yaml --debug

# 語法檢查
.venv/Scripts/python.exe -m py_compile persondetectandfield.py core/config.py
```

壓測／評測：`tools/stress_test/`（產生已知真值的高密度人流影片並跑分，見該資料夾 README）。

## 設定檔優先序（重要）

1. `run_monitor.bat` 若偵測到 `configs/home_gate.local.yaml` 存在，會設定 `MONITOR_CONFIG` 指向它 → **`.local.yaml` 蓋過 `home_gate.yaml`**。
2. 否則用環境變數 `MONITOR_CONFIG`，再否則預設 `configs/home_gate.yaml`。
3. `tools/replay_video.py` 預設吃 `home_gate.yaml`——要對照 live 行為請手動 `--config configs/home_gate.local.yaml`。

**調參數要改實際生效的那份**（通常是 `.local.yaml`）。`core/config.py` 的 `DEFAULT_CONFIG` 是後備值，缺鍵會自動補上。

## 計數不變量（不可違反）

- **總人流不是 YOLO/ByteTrack 的 raw track id 數。** raw id 會一直疊加、重複計數。總人流是「唯一身份通過計數條件」的數（`roi_person_count`）。
- **對帳關係必須維持**：
  - `total_count_on: exit_crossing` → `總人流 = 三方向和(assigned)`。
  - `total_count_on: roi_entry`（目前 live 用這個）→ `總人流 = 三方向和 + 待判定(pending)`。
  - 亦即 `總人流 = 往宿舍 + 往星巴門 + 往體育門 + 待判定`，改任何計數路徑都要能對得起來。
- **不可退回單一水平線進出計數**：三叉路口需要三個方向判定（dorm／starbucks／sports），這是刻意設計。
- **身份關聯不可放寬成「距離近就合併」**：短暫遺失（`reassoc_recent_sec`）才可純幾何接續；間隔較久必須外觀相似（`reassoc_appearance_min`）＋空間合理。放寬會把不同人（尤其制服）併成同一身份 → 嚴重漏記。
- 畫面上**不顯示 track id**（`show_person_labels: false`），避免 ID 疊加造成混亂。

## 統計欄位語意（payload / 前端）

- `current_count`：該幀畫面中可見人數
- `total_count`：總人流（`roi_person_count`）
- `detected_total_count`：建立過的唯一身份數（偵測面指標，非計數面）
- `assigned_destination_count`：已判定方向人數 = 三方向和
- `pending_destination_count`：已進 ROI 但尚未判定方向
- `to_dorm_count` / `to_starbucks_count` / `to_sports_count`：往宿舍／往星巴門／往體育門
- `interval_count`：本統計時段新增總人流
- `dominant_destination`：最多人去向
- `peak_count` / `avg_count`：尖峰／平均可見人數；`mode` / `brightness`：日夜／亮度
- 車流模式（`analysis_mode: vehicles`）會把車種塞進 `to_*` 欄位以重用前端——讀值時注意語意不同。

## 常見調參對照（症狀 → 先看哪個鍵）

設定鍵在生效的 YAML（通常 `configs/home_gate.local.yaml`）。改完務必用回放/壓測驗證。

| 症狀 | 先調 |
| --- | --- |
| 走過去很多人卻漏記（低估） | `tracking.reassoc_appearance_min`↑、`reassoc_recent_sec`↓、`track_max_missing_sec`↓；或 `model.tracker: botsort.yaml` |
| 同一人被重複計數（高估） | `reassoc_recent_sec`↑、`match_iou_thresh`↓、`match_distance_ratio`↑ |
| 遠處／夜間漏偵測 | `model.conf`↓、`model.imgsz`↑ |
| FPS 太低 | `model.imgsz`↓（960→832/768）、`video.inference_fps`↓ |
| 方向判定太慢／太少判 | `counting.visible_exit_min_points`↓、`visible_exit_min_track_sec`↓、`destination_min_travel_ratio`↓ |
| 方向判定錯 | 校正 `zones.road_roi`、`zones.exits`、`counting.visible_exit_zones` |
| 尖峰偵測遠低於實際人數 | 偵測端瓶頸：`imgsz`↑／換模型／`botsort.yaml`，非計數參數 |

## 驗證約定

**改動計數／追蹤／ROI／出口判定的邏輯前後，一定要用固定影片跑 `tools/replay_video.py` 比對 `total_count`／`assigned`／`pending`**，確認沒有改壞（過度合併→漏記，或碎裂→重複計數）。不要只靠 `py_compile`。真實攝影機以使用者自己的環境為準（Codex 環境可能掃不到攝影機，不要據此判定程式壞掉）。

## 文件索引（docs/）

- `docs/system_architecture.md`：資料流與各模組責任、校園行為系統的擴充方向
- `docs/count_debug_and_replay.md`：計數除錯與回放流程
- `docs/control_terminal.md`：控制終端（`control_terminal.bat`）用法
- `docs/remote_cross_network_demo.md`：跨網路遠端展示
- `README.md`：完整背景說明（資訊較多、部分較舊；與本檔衝突時以本檔為準）
