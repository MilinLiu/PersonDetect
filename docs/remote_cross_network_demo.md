# 跨網域遠端展示流程

目標：你的電腦在學校或家裡跑辨識系統，老師在不同網路用瀏覽器看到即時辨識畫面。

## 結論

不同網域時，老師端只有一個 HTML 檔是不夠的，因為老師的電腦無法直接連到你電腦的 `localhost:8765`。你需要多一個 tunnel，把你電腦的 WebSocket 服務暫時變成公開網址。

建議架構：

```text
攝影機/影片 -> 你的辨識電腦 -> localhost:8765 WebSocket -> tunnel 公開網址 -> 老師端 teacher_remote_viewer.html
```

老師端只需要：

```text
D:\COEDX\teacher_remote_viewer.html
```

或你把這個 HTML 檔傳給老師。

## 最推薦方案：Cloudflare Quick Tunnel

優點：

- 不需要改路由器
- 不需要開防火牆 port forwarding
- 可以產生臨時公開網址
- 適合 meeting demo

限制：

- 需要在你的電腦安裝 `cloudflared`
- Quick Tunnel 是測試/開發用途，不適合長期正式部署
- 你的目前 WebSocket 沒有登入驗證，所以公開網址只建議 meeting 期間短暫使用

## Demo 步驟

### 1. 啟動辨識系統

在第一個 PowerShell：

```powershell
.\control_terminal.bat --config home_gate preset debug
.\control_terminal.bat --config home_gate live
```

這會啟動本機 WebSocket：

```text
ws://localhost:8765
```

### 2. 開 tunnel

在第二個 PowerShell：

```powershell
cloudflared tunnel --url http://localhost:8765
```

如果你的電腦沒有全域 `cloudflared` 指令，可以用專案內的版本：

```powershell
.\tools\cloudflared.exe tunnel --url http://localhost:8765
```

或直接執行：

```powershell
.\start_remote_tunnel.bat
```

終端機會印出類似：

```text
https://something-random.trycloudflare.com
```

### 3. 老師端打開單檔 viewer

老師電腦打開：

```text
teacher_remote_viewer.html
```

把 tunnel URL 貼進上方欄位。可以貼 `https://...`，viewer 會自動轉成 WebSocket 的 `wss://...`。

例如：

```text
https://something-random.trycloudflare.com
```

或：

```text
wss://something-random.trycloudflare.com
```

### 4. Demo 結束後關閉

結束後請關掉：

- `persondetectandfield.py`
- `cloudflared tunnel`

這樣公開連線就會失效。

## 替代方案：ngrok

如果你用 ngrok：

```powershell
ngrok http 8765
```

ngrok 會給你一個 `https://...` 網址。老師端一樣打開 `teacher_remote_viewer.html`，貼上網址即可。

## 替代方案：Tailscale Funnel

如果你已經有 Tailscale，可以用 Funnel 把本機服務公開出去。不過它需要 Tailscale 帳號、MagicDNS、HTTPS 與 Funnel 權限設定，第一次設定比 Cloudflare Quick Tunnel 麻煩。

## 安全提醒

目前 WebSocket 沒有密碼驗證。只要拿到 tunnel URL 的人，就可能看到畫面，也能按 viewer 裡的人流/車流切換。

meeting 展示可以接受的低風險做法：

- 只在報告時開 tunnel
- 不把 URL 貼到公開群組
- Demo 完馬上 Ctrl+C 關閉 tunnel

如果之後真的要給老師長期看，我會建議再加一層 access token 或改成 Cloudflare Access。
