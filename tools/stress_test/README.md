# 人流計數壓測 / 評測工具

用「已知真值」的高密度人流影片驗證計數準確度。這是評測資料集的雛形——
每次改計數／追蹤／ROI 參數，都能一鍵回歸出「真值 vs 計數 vs 偵測率」的報告。

## 三步驟

```bash
# 1) 從一段真實錄影建立底圖 + 人形素材（只需做一次；輸出到 .tmp/stress_assets，不進 git）
.venv/Scripts/python.exe tools/stress_test/prep_assets.py .tmp/screen_111532.mp4 --cam-frac 0.63

# 2) 產生已知真值的壓測影片（N 個人各穿越 ROI 一次；輸出 crowd.mp4 + crowd.gt.json）
.venv/Scripts/python.exe tools/stress_test/make_crowd.py --people 40 --seconds 28

# 3) 跑分並對照真值（可帶多個 --config 做 A/B）
.venv/Scripts/python.exe tools/stress_test/score.py .tmp/stress_out/crowd.mp4 \
    --config configs/home_gate.local.yaml
```

## 報告怎麼看

- `召回%` = 計數 / 真值。100% 代表完全對上。
- `尖峰偵測` = pipeline 同時追蹤到的最多人數，反映 **YOLO 偵測上限**。
- **計數低、但尖峰偵測也低 → 瓶頸在偵測**（更大 imgsz／換 BoT-SORT ReID／升級模型），
  不是計數邏輯；計數低、尖峰偵測夠高 → 瓶頸在計數／身份合併。

## 注意

- 合成人形比真人難偵測，召回會被偵測端壓低；真實影片的絕對數字會更高。
  這裡的重點是**同一支影片下不同設定的相對差異**（例如修正前 vs 修正後）。
- ROI／出口由 `--config` 讀入，改場景 YAML 後人流會自動跟著新 ROI。
- 素材與影片都在 `.tmp/`（gitignore）。真實街景底圖請勿 commit。
