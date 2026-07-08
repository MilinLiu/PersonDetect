# 計數偵錯與影片回放

這份文件說明新增的兩個實作功能：

- `display.show_count_debug`：在即時畫面上顯示 ROI/出口 zone/個人軌跡狀態。
- `tools/replay_video.py`：用本機影片跑同一套 `InferenceThread`，輸出標註影片與 JSON 摘要。

如果想用選單操作，不想手動改 YAML 或輸入完整 replay 指令，可以先開：

```powershell
.\control_terminal.bat
```

控制終端的完整說明在 `docs/control_terminal.md`。

## 開啟即時偵錯畫面

在目前使用的 YAML 裡把這個值改成 `true`：

```yaml
display:
  show_road_roi: false
  show_direction_guides: true
  show_person_labels: false
  show_count_debug: true
```

啟動方式不變：

```powershell
.\.venv\Scripts\python.exe .\persondetectandfield.py
```

如果你要用另一份場景設定：

```powershell
$env:MONITOR_CONFIG = "configs\school_gate_example.yaml"
.\.venv\Scripts\python.exe .\persondetectandfield.py
```

## 偵錯畫面怎麼看

| 畫面元素 | 意義 |
| --- | --- |
| `walkway 1/2` | ROI 外圍的緩衝通道，人在這裡仍可被視為接近可計數區 |
| `exit Dorm / exit Sports / exit Star Gate` | visible exit zone，短軌跡進入這些區域並符合方向條件時可觸發目的地 |
| `P12 watch` | 已追蹤到人，但尚未進入可計數狀態 |
| `P12 pending` | 已進入 ROI 或出口緩衝區，正在等待目的地成立 |
| `P12 dest Dorm` | 這個人已完成目的地計數 |
| `pts` | 目前保留的軌跡點數 |
| `dx/dy` | 最近軌跡的 normalized 移動方向；往左通常 `dx` 為負，往右為正，往上通常 `dy` 為負 |
| 左上角 `COUNT DEBUG` | 當下總數、已分配、待分配、各門口累積與 visible exit 門檻 |

## 用影片回放測試

最常用的測試命令：

```powershell
.\.venv\Scripts\python.exe .\tools\replay_video.py "C:\Users\milin\Videos\螢幕錄製內容\螢幕錄製 2026-06-03 185040.mp4" --debug
```

指定輸出檔與摘要檔：

```powershell
.\.venv\Scripts\python.exe .\tools\replay_video.py "C:\path\to\case.mp4" --debug --output "replay_outputs\case_annotated.mp4" --summary "replay_outputs\case_summary.json"
```

只跑前 300 個處理 frame：

```powershell
.\.venv\Scripts\python.exe .\tools\replay_video.py "C:\path\to\case.mp4" --debug --max-frames 300
```

手動指定每幾張來源 frame 跑一次推論：

```powershell
.\.venv\Scripts\python.exe .\tools\replay_video.py "C:\path\to\case.mp4" --debug --every-n 3
```

## 輸出位置

預設會輸出到：

```text
D:\COEDX\replay_outputs\replay_影片檔名_時間.mp4
D:\COEDX\replay_outputs\replay_影片檔名_時間.json
D:\COEDX\replay_outputs\logs\replay_traffic_events.csv
```

回放事件 CSV 會放在 `replay_outputs/logs`，不會寫進正式的 `traffic_logs`。

## 回放工具的判讀方式

回放完成後請先看三個東西：

| 檢查項目 | 看哪裡 | 判斷重點 |
| --- | --- | --- |
| 哪個人加一 | 輸出 MP4 的 `COUNT +1 ... #total` | 是否能直觀看出是哪個人觸發 |
| 為什麼沒加 | debug 標籤的 `watch/pending/dest` 與 `dx/dy` | 人是否有進入 exit zone，方向是否符合 |
| 最終統計 | JSON 的 `final_counts` | `total_count`、`assigned_destination_count`、`pending_destination_count` 是否合理 |

如果某段影片有漏判，現在可以先用 `--debug` 輸出標註影片，再根據畫面調整 `configs/home_gate.yaml` 裡的 `visible_exit_zones`、`visible_exit_min_delta` 或 `visible_exit_min_travel_ratio`。
