# 智慧路燈人流監控專題 README

這份 README 是給之後在本專案開新聊天、接手修改程式的人看的。請先讀完這份，再動 `persondetectandfield.py` 或 `網頁監控.html`。

## 工作範圍

- 專案資料夾：`D:\COEDX`
- 使用者明確要求：只允許存取與修改 `D:\COEDX` 內的專案資料。
- 主要程式：`D:\COEDX\persondetectandfield.py`
- 前端頁面：`D:\COEDX\網頁監控.html`
- 主要 YOLO 模型：`D:\COEDX\yolo26l.pt`
- 目前場景設定檔：`D:\COEDX\configs\home_gate.yaml`
- 設定讀取程式：`D:\COEDX\core\config.py`
- 攝影機讀取模組：`D:\COEDX\core\camera_source.py`
- 影像工具模組：`D:\COEDX\core\image_utils.py`
- ReID 外觀工具：`D:\COEDX\core\appearance.py`
- 模型工具模組：`D:\COEDX\core\model_utils.py`
- 啟動輔助模組：`D:\COEDX\core\runtime.py`
- WebSocket 模組：`D:\COEDX\server\websocket_server.py`
- CSV/歷史紀錄模組：`D:\COEDX\server\traffic_logger.py`
- 幾何/ROI 輔助：`D:\COEDX\analyzers\geometry.py`
- 車流狀態統計：`D:\COEDX\analyzers\vehicle_flow.py`
- 畫框/疊圖工具：`D:\COEDX\analyzers\visualization.py`
- Python venv：`D:\COEDX\.venv`

## 專題目標

這是一個校園路口的人流監控系統，用 RTSP 攝影機影像搭配 YOLO 偵測行人，透過 WebSocket 把即時影像與統計資料送到網頁端。

目前監控場景是三叉路口，使用者定義的目的地如下：

- 左邊：`往宿舍`
- 右邊：`往星巴門`
- 前方：`往體育門`
- 如果人從人行道往前走，也歸類為 `往體育門`

重要設計方向：不要只看「哪邊來的人多」，而是要看「人最後往哪邊走」。

## 執行方式

第一次安裝或更新套件：

```bat
D:\COEDX\install_deps.bat
```

啟動後端：

```bat
D:\COEDX\run_monitor.bat
```

前端直接開：

```text
D:\COEDX\網頁監控.html
```

前端會連到：

```text
ws://localhost:8765
```

後端 WebSocket 監聽：

```text
0.0.0.0:8765
```

## 設定檔化狀態

目前第一階段已把「容易因攝影機或場地改變」的參數搬到：

```text
D:\COEDX\configs\home_gate.yaml
```

包含：

- RTSP 掃描網段、port、帳號、密碼、串流路徑
- WebSocket host 與 port
- YOLO 權重、imgsz、conf
- 道路 ROI、人行道補充區、出口線
- 日夜模式、警報門檻、CSV/歷史資料長度

`persondetectandfield.py` 仍保留原本的變數名稱與主流程，只是改成透過 `core\config.py` 讀取設定。若 `PyYAML` 尚未安裝、設定檔不存在或格式錯誤，程式會退回內建預設值，避免影響既有啟動流程。

目前也已先把低風險工具與外圍流程拆出去：

- `core\camera_source.py`：RTSP 攝影機連線、讀幀、重連
- `core\image_utils.py`：夜間增強、亮度估計
- `core\appearance.py`：輕量 ReID 外觀特徵
- `core\model_utils.py`：YOLO warm-up
- `core\runtime.py`：啟動前檢查、攝影機 IP 掃描、關閉清理
- `server\websocket_server.py`：WebSocket 影像與控制訊息傳輸
- `server\traffic_logger.py`：CSV header、事件 append、定時人流/車流紀錄
- `analyzers\geometry.py`：bbox、ROI、出口線交會、距離與路徑平均等純計算
- `analyzers\vehicle_flow.py`：車流 track 狀態、累積數、時段數、尖峰與平均
- `analyzers\visualization.py`：人流/車流畫框、路徑、ROI 與出口線疊圖

目前 `persondetectandfield.py` 主要還保留設定常數、`InferenceThread` 與 `main()` 組裝流程。`InferenceThread` 已先把車流狀態、幾何工具、畫框疊圖抽出去；人流目的地判定仍保留在主檔，因為它直接影響總人流、待判定與三方向統計。之後若要再拆，建議先用固定影片回放測試，避免改壞計數邏輯。

若要測另一個場景，可以複製：

```text
D:\COEDX\configs\school_gate_example.yaml
```

再透過環境變數指定設定檔：

```powershell
$env:MONITOR_CONFIG = "configs\school_gate_example.yaml"
D:\COEDX\.venv\Scripts\python.exe D:\COEDX\persondetectandfield.py
```

## 目前環境與 GPU

已建立 `.venv`。目前 CUDA 版 PyTorch 安裝設定在：

- `requirements.txt`：一般套件
- `requirements-cuda.txt`：CUDA PyTorch

目前 CUDA requirements：

```text
--index-url https://download.pytorch.org/whl/cu126
torch==2.10.0
torchvision==0.25.0
torchaudio==2.10.0
```

後端會用：

```python
MODEL_DEVICE = 0 if torch.cuda.is_available() else "cpu"
```

也就是有 CUDA GPU 時使用 GPU，否則退回 CPU。

之前已驗證過的使用者機器 GPU：

```text
NVIDIA GeForce RTX 4070 Ti
torch 2.10.0+cu126
CUDA available = True
```

## RTSP 攝影機

後端目前會掃描：

```text
192.168.0.1 ~ 192.168.0.254
port 554
```

找到攝影機後組成 RTSP URL：

```text
rtsp://adminuser:00000000@{camera_ip}:554/stream2
```

注意：Codex 這邊曾經試跑時找不到攝影機，但使用者自己可以跑起來。不要直接判定程式壞掉，可能只是執行環境、網路權限或攝影機連線狀態不同。

## 核心計數邏輯

使用者回報過的問題：

- 人被框到後消失，再次被框到時可能重複記數。
- YOLO/ByteTrack 的 ID 會一直增加，畫面 ID 看起來很亂。
- 有些人明明走進畫面，但計數器沒有加，直到走出去也完全沒增加。
- 總人流與三個方向統計有時對不起來。

目前的修正方向：

- 不顯示追蹤 ID：`SHOW_PERSON_LABELS = False`
- `總人流` 不等於 YOLO raw ID 數，而是已通過出口判定的人流數。
- 人進入有效監控區後先放在 `待判定`，不會立刻加到 `總人流`。
- 人跨出三個出口線，或可見路徑已明確進入左/右/前出口區時，才會加到 `總人流` 與目的地統計。
- 預設關閉「消失後推論目的地」，避免計數器在看不見人的奇怪時間點跳動。
- 觸發計數的那個人會在畫面上短暫顯示 `COUNT +1 dorm/starbucks/sports`。

前端與後端的統計關係目前應該維持：

```text
總人流 = 往宿舍 + 往星巴門 + 往體育門
已觀察人流 = 總人流 + 待判定
```

### 統計欄位語意

- `current_count`：目前畫面中可見的人數
- `total_count`：已跨出口或明確進入出口區的人流總數，也就是 `roi_person_count`
- `assigned_destination_count`：已判定目的地的人數
- `pending_destination_count`：已進入監控區但尚未跨出口/尚未判定目的地的人數
- `to_dorm_count`：往宿舍
- `to_starbucks_count`：往星巴門
- `to_sports_count`：往體育門
- `interval_count`：目前統計時段內新增總人流
- `dominant_destination`：目前最多人去的方向

## ROI 與目的地判定

所有 ROI 與線段座標都是 normalized 座標，格式是 `(x, y)`，左上角是 `(0, 0)`，右下角是 `(1, 1)`。

目前道路 ROI：

```python
ROAD_ROI_NORM = [
    (0.02, 0.98),
    (0.19, 0.36),
    (0.72, 0.36),
    (0.98, 0.98),
]
```

目前 ROI 容錯：

```python
ROAD_ROI_MARGIN_RATIO = 0.05
```

這是為了解決「人有被框到，但腳底中心點剛好不在 ROI 內就完全不追蹤」的問題。現在程式不只看腳底中心點，會看人體下半部多個取樣點，並允許靠近 ROI 邊界的框先進入 `待判定`；真正的 `總人流 +1` 預設會發生在出口判定時。

人行道補充區：

```python
FORWARD_WALKWAY_ZONES_NORM = [
    (0.00, 0.36, 0.24, 0.84),
    (0.58, 0.38, 0.99, 0.84),
]
```

目的地出口線：

```python
EXIT_LINES_NORM = {
    "dorm": ((0.02, 0.98), (0.19, 0.36)),
    "sports": ((0.19, 0.36), (0.72, 0.36)),
    "starbucks": ((0.72, 0.36), (0.98, 0.98)),
}
```

目的地對應：

```text
dorm      -> 往宿舍
starbucks -> 往星巴門
sports    -> 往體育門
```

目前預設不把 ROI 線畫在畫面上：

```python
SHOW_ROAD_ROI = False
```

如果要除錯路口判斷，可以暫時改成 `True`。

## YOLO 與追蹤參數

目前為了改善夜間、小目標與遠處行人漏偵測，已調整：

```python
BYTETRACK_CONF = 0.28
YOLO_IMGSZ = 960
```

這會比 `imgsz=640` 更吃 GPU，但比較不容易漏掉遠處或較小的人。

其他追蹤與 ReID 參數：

```python
REID_THRESH = 0.82
REID_EXPIRE_SEC = 60
REID_MAX_SIZE = 200
TRACK_MAX_MISSING_SEC = 12.0
TRACK_ID_TTL_SEC = 30.0
MATCH_IOU_THRESH = 0.18
MATCH_DISTANCE_RATIO = 0.16
DESTINATION_MIN_TRAVEL_RATIO = 0.075
DESTINATION_MIN_TRACK_SEC = 0.5
DESTINATION_MISSING_INFER_SEC = 2.0
DESTINATION_HISTORY_SIZE = 36
```

調整建議：

- 如果還會漏人：可再稍微降低 `BYTETRACK_CONF`，但誤判會變多。
- 如果 FPS 太低：先把 `YOLO_IMGSZ` 往下調，例如 832 或 768。
- 如果同一個人重複計數：優先看 `TRACK_MAX_MISSING_SEC`、`REID_THRESH`、`MATCH_DISTANCE_RATIO`。
- 如果方向判斷太慢：看 `DESTINATION_MISSING_INFER_SEC`。
- 如果方向判斷錯：先調 `ROAD_ROI_NORM`、`FORWARD_WALKWAY_ZONES_NORM`、`EXIT_LINES_NORM`。

## 影像與日夜模式

後端設定：

```python
INFERENCE_FPS = 15
OUTPUT_WIDTH = 854
OUTPUT_HEIGHT = 480
JPEG_QUALITY = 60
NIGHT_BRIGHTNESS_THRESHOLD = 85
NIGHT_MODE_HYSTERESIS = 10
```

亮度低於門檻會進夜間模式，後端會做簡單影像增強。前端會顯示日間/夜間狀態與亮度。

## 前端功能

目前前端是 `D:\COEDX\網頁監控.html`，主要功能：

- 即時影像顯示
- 連線狀態
- 日間/夜間模式 badge
- 目前人數
- 尖峰人數
- 最多人去向
- 總人流
- 往宿舍 / 往星巴門 / 往體育門
- 待判定
- 本時段人流
- FPS
- 目的地占比條
- 時段流量圖表
- 前端 CSV 匯出
- 人流警報

警報門檻：

```python
ALERT_THRESHOLD = 6
```

如果 `current_count` 超過門檻，前端會顯示紅色警告。

前端 CSV 匯出欄位包含：

```text
時間
時段新增
時段往宿舍
時段往星巴門
時段往體育門
總人流
已判定
待判定
當前
往宿舍
往星巴門
往體育門
最多目的地
尖峰
```

## 後端 CSV 紀錄

後端會自動寫入：

```text
D:\COEDX\traffic_logs\traffic_summary.csv
D:\COEDX\traffic_logs\traffic_events.csv
```

時段紀錄間隔：

```python
INTERVAL_MINUTES = 5
```

前端圖表記憶長度：

```python
HISTORY_MAX_POINTS = 96
```

注意：`HISTORY_MAX_POINTS` 只限制前端圖表傳輸用的記憶資料，不代表 CSV 會被覆蓋。CSV 是持續 append，用來保留長時間紀錄。

`traffic_summary.csv` 是每 5 分鐘摘要一次。  
`traffic_events.csv` 是每次判定某個人的目的地時記一筆事件。

## 測試與輔助檔案

可用語法檢查：

```bat
D:\COEDX\.venv\Scripts\python.exe -m py_compile D:\COEDX\persondetectandfield.py D:\COEDX\mock_stream_server.py
```

測 CUDA：

```bat
D:\COEDX\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

輔助檔案：

- `mock_stream_server.py`：模擬 WebSocket 資料，可用來測前端。
- `preview_frontend.js`：用假 WebSocket 資料預覽前端畫面。
- `frontend_preview.png`：之前的前端預覽截圖。

## 已討論且已做進去的功能

- 建立 venv 與安裝套件
- 安裝 CUDA PyTorch
- YOLO 使用 GPU 推論
- 移除畫面上的 ID 顯示，避免 ID 一直疊加造成混亂
- 以 ROI + 三個出口判定目的地
- 由「哪邊來的人多」改成「往哪邊走的人多」
- 人先進 `待判定`，跨出口或明確進入出口區後才補到 `總人流 / 目的地`
- 左右人行道往前走可判定為 `往體育門`
- 自動日夜模式
- 前端三欄核心統計
- 尖峰人數
- 最多人去向
- 可設定警報門檻
- 後端 CSV 持續記錄
- 前端 CSV 匯出
- 前端 UI 改成比較像監控儀表板

## 最近一次重要修正

### 2026-06-03：右往左往宿舍漏判與計數可視化

使用者提供影片：

```text
C:\Users\milin\Videos\螢幕錄製內容\螢幕錄製 2026-06-03 185040.mp4
```

現象：

- 一群人從右往左走，但 `往宿舍` 計數沒有明顯作動。
- 之前 `總人流` 可能在進 ROI 或消失推論時跳動，使用者難以看出是哪個人觸發 `+1`。

修正：

- 新增 `counting.total_count_on: exit_crossing`，預設在出口判定時才讓 `總人流 +1`。
- 新增 `counting.allow_missing_destination_infer: false`，預設不再用消失後推論偷偷補目的地。
- 新增可見路徑出口區判定：右往左進入左側出口區會判為 `dorm`。
- 為了減少群體遮擋漏判，左出口可見判定已放寬：短軌跡只要進入 `dorm_visible_exit_x` 並明確往左，就可觸發 `Dorm`。
- 後續又改成三方向共用的 `visible_exit_zones`：`dorm`、`starbucks`、`sports` 都可設定自己的出口觸發區與移動方向條件，避免只修單邊。
- 觸發計數的行人框會短暫高亮並顯示 `COUNT +1 dorm/starbucks/sports`。

相關設定在 `configs\home_gate.yaml`：

```yaml
counting:
  visible_exit_min_points: 2
  visible_exit_min_track_sec: 0.2
  visible_exit_min_travel_ratio: 0.025
  visible_exit_min_delta: 0.012
  dorm_visible_exit_x: 0.46
  dorm_strict_exit_x: 0.38
  visible_exit_zones:
    dorm:
      x_max: 0.50
      y_min: 0.34
      y_max: 0.98
      dx_max: -0.006
      dominant_axis: x
      axis_ratio: 0.20
    starbucks:
      x_min: 0.50
      y_min: 0.34
      y_max: 0.98
      dx_min: 0.006
      dominant_axis: x
      axis_ratio: 0.20
    sports:
      x_min: 0.12
      x_max: 0.82
      y_max: 0.64
      dy_max: -0.006
      dominant_axis: y
      axis_ratio: 0.20
```

注意：

- 這版更重視「肉眼能對上誰觸發計數」。
- 如果追蹤中斷導致完全沒有跨線/出口區證據，該人會留在 `待判定`，不會在消失後突然加總。

使用者回報：

> 有些人走進畫面，但計數器沒有記數，直到走出去也沒有任何增加。

原因：

舊版只用「腳底中心點」是否落在道路 ROI 內決定要不要計入 `roi_person_count`。如果 YOLO 框偏移、人在邊界、人行道、腳底被裁切或夜間框底不準，就可能完全不被計入。

修正：

- 加入 `_zone_probe_points()`，用人體下半部多個點判斷。
- 加入 `_box_zone_hit()`，合併道路 ROI、ROI 邊界容錯、人行道補充區。
- `BYTETRACK_CONF` 降到 `0.28`。
- `YOLO_IMGSZ` 提高到 `960`。

測試結果：

- 道路中央：會計數
- 左人行道：會計數
- 右人行道：會計數
- ROI 邊界附近：會計數
- 非監控區畫面上方：不計數

## 給未來接手者的注意事項

- 使用者偏好繁體中文說明與 UI。
- 不要把功能改回單純水平線進出計數，因為三叉路口需要三個目的地判定。
- 不要只用 YOLO raw track id 當總人數，這會造成 ID 疊加與重複計數問題。
- 不要讓平均人數佔據核心位置，使用者覺得「往哪邊走的人多」更重要。
- 若修改 ROI 或目的地判定，請同步更新這份 README。
- 若要實測真實攝影機，優先用使用者自己的環境跑 `run_monitor.bat`，Codex 的網路環境可能掃不到攝影機。
