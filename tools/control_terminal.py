from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DEFAULT_CONFIG = "configs/home_gate.yaml"
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
MONITOR_SCRIPT = PROJECT_ROOT / "persondetectandfield.py"
REPLAY_SCRIPT = PROJECT_ROOT / "tools" / "replay_video.py"

PRESETS: dict[str, dict[str, Any]] = {
    "normal": {
        "display.show_count_debug": False,
        "display.show_road_roi": False,
        "display.show_direction_guides": True,
        "display.show_person_labels": False,
    },
    "debug": {
        "display.show_count_debug": True,
        "display.show_road_roi": True,
        "display.show_direction_guides": True,
        "display.show_person_labels": True,
    },
    "clean": {
        "display.show_count_debug": False,
        "display.show_road_roi": False,
        "display.show_direction_guides": False,
        "display.show_person_labels": False,
    },
    "calibrate": {
        "display.show_count_debug": True,
        "display.show_road_roi": True,
        "display.show_direction_guides": True,
        "display.show_person_labels": False,
    },
}


def require_yaml():
    if yaml is None:
        raise SystemExit("PyYAML is not installed. Please install requirements.txt first.")


def python_executable() -> str:
    if PYTHON_EXE.exists():
        return str(PYTHON_EXE)
    return sys.executable


def resolve_config(config: str | Path | None) -> Path:
    value = str(config or DEFAULT_CONFIG)
    path = Path(value)
    if not path.suffix:
        if path.parent == Path("."):
            path = CONFIG_DIR / f"{value}.yaml"
        elif path.is_absolute():
            path = path.with_suffix(".yaml")
        else:
            path = (PROJECT_ROOT / path).with_suffix(".yaml")
    elif not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise SystemExit(f"Config not found: {path}")
    return path.resolve()


def config_arg(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def list_configs() -> list[Path]:
    return sorted(CONFIG_DIR.glob("*.yaml"))


def load_yaml(path: Path) -> dict[str, Any]:
    require_yaml()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a YAML mapping: {path}")
    return data


def save_yaml(path: Path, data: dict[str, Any]):
    require_yaml()
    with path.open("w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def get_nested(data: dict[str, Any], dotted_key: str, default=None):
    current: Any = data
    for key in dotted_key.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def set_nested(data: dict[str, Any], dotted_key: str, value: Any):
    current = data
    parts = dotted_key.split(".")
    for key in parts[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[parts[-1]] = value


def parse_value(raw: str) -> Any:
    text = str(raw).strip()
    lowered = text.lower()
    if lowered in ("true", "on", "yes", "1"):
        return True
    if lowered in ("false", "off", "no", "0"):
        return False
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def summarize_config(path: Path) -> str:
    data = load_yaml(path)
    display = data.get("display", {})
    counting = data.get("counting", {})
    camera = data.get("camera", {})
    zones = counting.get("visible_exit_zones", {})
    lines = [
        f"Config: {config_arg(path)}",
        f"Camera RTSP: {camera.get('rtsp_url') or '(auto scan)'}",
        (
            "Display: "
            f"debug={display.get('show_count_debug', False)} "
            f"roi={display.get('show_road_roi', False)} "
            f"guides={display.get('show_direction_guides', False)} "
            f"labels={display.get('show_person_labels', False)}"
        ),
        (
            "Counting: "
            f"total_on={counting.get('total_count_on')} "
            f"missing_infer={counting.get('allow_missing_destination_infer')} "
            f"min_pts={counting.get('visible_exit_min_points')} "
            f"travel={counting.get('visible_exit_min_travel_ratio')} "
            f"delta={counting.get('visible_exit_min_delta')}"
        ),
        f"Visible exits: {', '.join(zones.keys()) if isinstance(zones, dict) else '(none)'}",
    ]
    return "\n".join(lines)


def apply_values(path: Path, values: dict[str, Any]):
    data = load_yaml(path)
    for dotted_key, value in values.items():
        set_nested(data, dotted_key, value)
    save_yaml(path, data)


def apply_preset(path: Path, preset: str):
    if preset not in PRESETS:
        choices = ", ".join(PRESETS)
        raise SystemExit(f"Unknown preset: {preset}. Choices: {choices}")
    apply_values(path, PRESETS[preset])
    print(f"[Control] Applied preset '{preset}' to {config_arg(path)}")


def toggle_value(path: Path, dotted_key: str):
    data = load_yaml(path)
    current = bool(get_nested(data, dotted_key, False))
    set_nested(data, dotted_key, not current)
    save_yaml(path, data)
    print(f"[Control] {dotted_key}: {current} -> {not current}")


def set_value(path: Path, dotted_key: str, value: Any):
    data = load_yaml(path)
    old_value = get_nested(data, dotted_key, "(missing)")
    set_nested(data, dotted_key, value)
    save_yaml(path, data)
    print(f"[Control] {dotted_key}: {old_value} -> {value}")


def run_child(command: list[str], config_path: Path):
    env = os.environ.copy()
    env["MONITOR_CONFIG"] = config_arg(config_path)
    print("[Control] MONITOR_CONFIG =", env["MONITOR_CONFIG"])
    print("[Control] Running:", " ".join(f'"{part}"' if " " in part else part for part in command))
    try:
        return subprocess.call(command, cwd=str(PROJECT_ROOT), env=env)
    except KeyboardInterrupt:
        print("\n[Control] Stopped.")
        return 130


def run_live(config_path: Path):
    command = [python_executable(), str(MONITOR_SCRIPT)]
    return run_child(command, config_path)


def run_replay(
    config_path: Path,
    video: str,
    debug: bool = False,
    output: str | None = None,
    summary: str | None = None,
    max_frames: int | None = None,
    every_n: int | None = None,
    no_output: bool = False,
):
    command = [
        python_executable(),
        str(REPLAY_SCRIPT),
        video,
        "--config",
        config_arg(config_path),
    ]
    if debug:
        command.append("--debug")
    if output:
        command.extend(["--output", output])
    if summary:
        command.extend(["--summary", summary])
    if max_frames is not None:
        command.extend(["--max-frames", str(max_frames)])
    if every_n is not None:
        command.extend(["--every-n", str(every_n)])
    if no_output:
        command.append("--no-output")
    return run_child(command, config_path)


def prompt(message: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{message}{suffix}: ").strip()
    return value if value else (default or "")


def choose_config(current: Path) -> Path:
    configs = list_configs()
    if not configs:
        raise SystemExit("No YAML files found in configs/.")
    print("\nAvailable configs:")
    for index, path in enumerate(configs, start=1):
        mark = "*" if path.resolve() == current.resolve() else " "
        print(f" {index}. {mark} {config_arg(path)}")
    raw = prompt("Choose config number", "1")
    try:
        index = int(raw)
        return configs[index - 1].resolve()
    except (ValueError, IndexError):
        print("[Control] Invalid selection.")
        return current


def choose_preset(config_path: Path):
    print("\nPresets:")
    print(" 1. normal    一般監控：只留方向線")
    print(" 2. debug     計數偵錯：ROI、zone、label 全開")
    print(" 3. clean     乾淨畫面：輔助線全關")
    print(" 4. calibrate 場域標定：ROI、zone、debug 開，person label 關")
    raw = prompt("Choose preset", "2").lower()
    mapping = {"1": "normal", "2": "debug", "3": "clean", "4": "calibrate"}
    preset = mapping.get(raw, raw)
    if preset in PRESETS:
        apply_preset(config_path, preset)
    else:
        print("[Control] Unknown preset.")


def replay_prompt(config_path: Path):
    video = prompt("Video path")
    if not video:
        print("[Control] Replay cancelled.")
        return
    debug_answer = prompt("Force debug overlay? y/n", "y").lower()
    max_frames_text = prompt("Max processed frames, blank for full video", "")
    every_n_text = prompt("Every N source frames, blank for auto", "")
    no_output_answer = prompt("No MP4 output? y/n", "n").lower()
    try:
        max_frames = int(max_frames_text) if max_frames_text else None
        every_n = int(every_n_text) if every_n_text else None
    except ValueError:
        print("[Control] Max frames and every-n must be numbers.")
        return
    run_replay(
        config_path,
        video,
        debug=debug_answer in ("y", "yes", "1", "true"),
        max_frames=max_frames,
        every_n=every_n,
        no_output=no_output_answer in ("y", "yes", "1", "true"),
    )


def menu(start_config: str | None = None):
    config_path = resolve_config(start_config)
    while True:
        print("\n" + "=" * 66)
        print("COEDX YAML Control Terminal")
        print("=" * 66)
        print(summarize_config(config_path))
        print("-" * 66)
        print(" 1. Switch YAML config")
        print(" 2. Apply preset")
        print(" 3. Toggle count debug")
        print(" 4. Toggle ROI display")
        print(" 5. Toggle direction guides")
        print(" 6. Toggle person labels")
        print(" 7. Run live monitor")
        print(" 8. Replay video")
        print(" 9. Show config summary")
        print(" 0. Exit")
        choice = prompt("Action", "0")

        if choice == "1":
            config_path = choose_config(config_path)
        elif choice == "2":
            choose_preset(config_path)
        elif choice == "3":
            toggle_value(config_path, "display.show_count_debug")
        elif choice == "4":
            toggle_value(config_path, "display.show_road_roi")
        elif choice == "5":
            toggle_value(config_path, "display.show_direction_guides")
        elif choice == "6":
            toggle_value(config_path, "display.show_person_labels")
        elif choice == "7":
            run_live(config_path)
        elif choice == "8":
            replay_prompt(config_path)
        elif choice == "9":
            print("\n" + summarize_config(config_path))
        elif choice == "0":
            return
        else:
            print("[Control] Unknown action.")


def build_parser():
    parser = argparse.ArgumentParser(description="YAML control terminal for the COEDX monitor.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config YAML path or name.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("menu", help="Open interactive menu.")
    subparsers.add_parser("list", help="List YAML configs.")
    subparsers.add_parser("show", help="Show config summary.")

    preset_parser = subparsers.add_parser("preset", help="Apply a display preset.")
    preset_parser.add_argument("name", choices=sorted(PRESETS))

    toggle_parser = subparsers.add_parser("toggle", help="Toggle a boolean YAML value.")
    toggle_parser.add_argument("key")

    set_parser = subparsers.add_parser("set", help="Set a YAML value.")
    set_parser.add_argument("key")
    set_parser.add_argument("value")

    subparsers.add_parser("live", help="Run live monitor with this config.")

    replay_parser = subparsers.add_parser("replay", help="Run replay_video.py with this config.")
    replay_parser.add_argument("video")
    replay_parser.add_argument("--debug", action="store_true")
    replay_parser.add_argument("--output")
    replay_parser.add_argument("--summary")
    replay_parser.add_argument("--max-frames", type=int)
    replay_parser.add_argument("--every-n", type=int)
    replay_parser.add_argument("--no-output", action="store_true")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    config_path = resolve_config(args.config)

    if args.command in (None, "menu"):
        menu(str(config_path))
    elif args.command == "list":
        for path in list_configs():
            print(config_arg(path))
    elif args.command == "show":
        print(summarize_config(config_path))
    elif args.command == "preset":
        apply_preset(config_path, args.name)
    elif args.command == "toggle":
        toggle_value(config_path, args.key)
    elif args.command == "set":
        set_value(config_path, args.key, parse_value(args.value))
    elif args.command == "live":
        raise SystemExit(run_live(config_path))
    elif args.command == "replay":
        raise SystemExit(
            run_replay(
                config_path,
                args.video,
                debug=args.debug,
                output=args.output,
                summary=args.summary,
                max_frames=args.max_frames,
                every_n=args.every_n,
                no_output=args.no_output,
            )
        )


if __name__ == "__main__":
    main()
