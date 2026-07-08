"""把壓測影片跑過計數 pipeline，對照真值輸出報告（計數誤差 / 偵測率）。

沿用 tools/replay_video.py 產生 summary，再與 <video>.gt.json 比對。
可一次帶多個設定檔做 A/B（例如修正前 vs 修正後）。

範例：
  .venv/Scripts/python.exe tools/stress_test/score.py .tmp/stress_out/crowd.mp4 \
      --config configs/home_gate.local.yaml
  # A/B：
  .venv/Scripts/python.exe tools/stress_test/score.py .tmp/stress_out/crowd.mp4 \
      --config before.yaml --config after.yaml
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPLAY = PROJECT_ROOT / "tools" / "replay_video.py"


def resolve(path_value: str) -> Path:
    p = Path(path_value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def run_replay(video: Path, config: str, mode: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        summary_path = Path(td) / "summary.json"
        cmd = [sys.executable, str(REPLAY), str(video),
               "--config", config, "--mode", mode,
               "--no-output", "--summary", str(summary_path),
               "--log-dir", str(Path(td) / "logs"), "--progress-every", "0"]
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return json.loads(summary_path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--gt", help="真值 JSON（預設 <video>.gt.json）")
    ap.add_argument("--config", action="append", required=True, help="可重複，做 A/B")
    ap.add_argument("--mode", default="people", choices=["people", "vehicles"])
    a = ap.parse_args()

    video = resolve(a.video)
    if not video.exists():
        raise SystemExit(f"video not found: {video}")
    gt_path = resolve(a.gt) if a.gt else video.with_suffix(".gt.json")
    if not gt_path.exists():
        raise SystemExit(f"ground-truth not found: {gt_path}")
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    total_gt = int(gt["total_people"])
    peak_gt = int(gt.get("peak_on_screen", 0))

    print(f"影片：{video.name}")
    print(f"真值：總人數={total_gt}  尖峰同框={peak_gt}\n")
    header = f"{'設定檔':<28}{'計數':>6}{'誤差':>7}{'召回%':>8}{'尖峰偵測':>9}{'已判方向':>9}{'待判定':>8}"
    print(header)
    print("-" * len(header))
    for config in a.config:
        summ = run_replay(video, config, a.mode)
        fc = summ.get("final_counts", {})
        counted = int(fc.get("total_count", 0))
        peak_det = int(fc.get("peak_count", 0))
        assigned = int(fc.get("assigned_destination_count", 0))
        pending = int(fc.get("pending_destination_count", 0))
        err = counted - total_gt
        recall = 100.0 * counted / total_gt if total_gt else 0.0
        name = Path(config).name
        print(f"{name:<28}{counted:>6}{err:>+7}{recall:>7.0f}%{peak_det:>9}{assigned:>9}{pending:>8}")
    print("\n說明：召回% = 計數/真值（100% 為完全對上）；尖峰偵測 = pipeline 同時追蹤到的最多人數，")
    print("      反映 YOLO 偵測上限。計數遠低於真值但尖峰偵測也低 → 瓶頸在偵測，不是計數邏輯。")


if __name__ == "__main__":
    main()
