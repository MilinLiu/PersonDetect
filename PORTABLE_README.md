# COEDX 可移植版使用說明

這個壓縮包是移植到其他 Windows 電腦用的精簡版。它不包含 `.venv`，所以解壓縮後需要在新電腦重新建立 Python 環境。

## 壓縮包內包含

- 主程式：`persondetectandfield.py`
- 前端監控頁：`網頁監控.html`
- 老師端遠端觀看器：`teacher_remote_viewer.html`
- YAML 設定：`configs/`
- 核心模組：`core/`、`analyzers/`、`server/`
- 工具：`tools/`
- 文件：`README.md`、`docs/`
- 必要模型：`yolo26s.pt`
- 新電腦安裝腳本：`SETUP_ON_NEW_PC.bat`
- 控制終端：`control_terminal.bat`

## 壓縮包沒有包含

- `.venv`
- `__pycache__`
- `.tmp`
- 測試輸出影片 `replay_outputs`
- 正式/測試紀錄 `traffic_logs`
- 未使用的大模型 `yolo26l.pt`、`yolo26m.pt`

## 第一次在新電腦執行

1. 先安裝 Python 3。
2. 解壓縮這個資料夾。
3. 在資料夾內執行：

```powershell
.\SETUP_ON_NEW_PC.bat
```

這會建立 `.venv` 並下載需要的套件。PyTorch/CUDA 會比較大，下載時間可能很久。

## 移交前注意帳密

`configs/home_gate.yaml` 可能包含目前攝影機的 RTSP 帳號、密碼或 IP 設定。如果這個 zip 要傳給老師或組員以外的人，請先檢查：

```text
configs/home_gate.yaml
configs/school_gate_example.yaml
```

不想公開的帳密請先改成範例值。

## 啟動系統

安裝完成後執行：

```powershell
.\control_terminal.bat
```

常用指令：

```powershell
.\control_terminal.bat --config home_gate live
.\control_terminal.bat --config home_gate preset debug
.\control_terminal.bat --config home_gate replay "C:\path\to\video.mp4" --debug
```

## 遠端展示

如果要給不同網路的人看，先啟動主程式，再開 tunnel：

```powershell
.\start_remote_tunnel.bat
```

把 `https://xxxxx.trycloudflare.com` 貼到 `teacher_remote_viewer.html` 即可。

注意：目前 WebSocket 沒有密碼，tunnel 只建議 meeting 期間短暫開啟。
