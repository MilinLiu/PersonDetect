# YAML 控制終端

`tools/control_terminal.py` 是目前的控制台入口，可以用互動選單切換 YAML、套用顯示 preset、啟動即時監控，或直接跑影片回放。

## 最簡單用法

在 `D:\COEDX` 執行：

```powershell
.\control_terminal.bat
```
會看到互動選單：
```text
1. Switch YAML config
2. Apply preset
3. Toggle count debug
4. Toggle ROI display
5. Toggle direction guides
6. Toggle person labels
7. Run live monitor
8. Replay video
9. Show config summary
0. Exit
```
## 常用 preset

| preset | 用途 | 會改哪些顯示設定 |
| --- | --- | --- |
| `normal` | 平常監控 | 關 debug、關 ROI、開方向線、關 person label |
| `debug` | 找漏判原因 | 開 debug、開 ROI、開方向線、開 person label |
| `clean` | 乾淨展示畫面 | debug/ROI/方向線/person label 全關 |
| `calibrate` | 標定場域 ROI | 開 debug、開 ROI、開方向線、關 person label |

互動選單中選 `2` 就可以套用 preset。

也可以直接一行指令：

```powershell
.\control_terminal.bat --config home_gate preset debug
.\control_terminal.bat --config home_gate preset normal
```

`--config home_gate` 會自動對到：

```text
D:\COEDX\configs\home_gate.yaml
```

## 一鍵啟動即時監控

用家門口設定啟動：

```powershell
.\control_terminal.bat --config home_gate live
```

用校內範例設定啟動：

```powershell
.\control_terminal.bat --config school_gate_example live
```

控制終端會自動幫這次啟動設定：

```text
MONITOR_CONFIG=configs\home_gate.yaml
```

所以不用再手動打 `$env:MONITOR_CONFIG = ...`。

## 一鍵跑影片回放

最常用的偵錯回放：

```powershell
.\control_terminal.bat --config home_gate replay "C:\Users\milin\Videos\螢幕錄製內容\螢幕錄製 2026-06-03 185040.mp4" --debug
```

只跑前 300 個處理 frame：

```powershell
.\control_terminal.bat --config home_gate replay "C:\path\to\case.mp4" --debug --max-frames 300
```

指定輸出檔：

```powershell
.\control_terminal.bat --config home_gate replay "C:\path\to\case.mp4" --debug --output "replay_outputs\case_annotated.mp4" --summary "replay_outputs\case_summary.json"
```

如果只是想快速看統計、不輸出 MP4：

```powershell
.\control_terminal.bat --config home_gate replay "C:\path\to\case.mp4" --debug --no-output
```

## 單獨切換某個 YAML 開關

```powershell
.\control_terminal.bat --config home_gate toggle display.show_count_debug
.\control_terminal.bat --config home_gate toggle display.show_road_roi
.\control_terminal.bat --config home_gate toggle display.show_direction_guides
.\control_terminal.bat --config home_gate toggle display.show_person_labels
```

也可以直接指定值：

```powershell
.\control_terminal.bat --config home_gate set display.show_count_debug true
.\control_terminal.bat --config home_gate set display.show_count_debug false
```

## 檢查目前 YAML 狀態

列出所有 YAML：

```powershell
.\control_terminal.bat list
```

看某份 YAML 摘要：

```powershell
.\control_terminal.bat --config home_gate show
```

## 注意事項

- 控制終端會直接修改你選到的 YAML 檔。
- `live` 和 `replay` 都會用你選到的 YAML 啟動，不需要另外設定環境變數。
- 回放輸出預設在 `D:\COEDX\replay_outputs`，不會寫進正式的 `traffic_logs`。
