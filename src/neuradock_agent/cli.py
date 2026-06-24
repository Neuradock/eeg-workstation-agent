from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .agent import AgentInputs, execute_request, route_intent
from .artifacts import write_batch_clean_npz
from .demo import generate_visual_load_demo_file
from .io import (
    parse_trial_selection,
    read_neuradock_input,
    read_neuradock_txt,
)
from .llm_config import load_or_prompt_llm_config, prompt_for_llm_config
from .online import serve_online_dashboard
from .profile import PROFILE, __version__
from .realtime import run_device_doctor
from .workflows import (
    run_alpha_dynamics,
    run_psd_bandpower,
    run_signal_quality,
    run_visual_cognitive_load,
    run_visual_cognitive_load_comparison,
    summarize_run,
)


def _read_text_with_retry(
    path: Path,
    attempts: int = 8,
    initial_delay_sec: float = 0.1,
) -> str:
    """Read a newly written file despite transient Windows access locks."""

    delay = initial_delay_sec
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            transient = isinstance(exc, PermissionError) or winerror in {5, 32}
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2.0, 0.5)
    raise RuntimeError("Unreachable text-read retry state.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neuradock-agent",
        description=(
            "Local-first visual cognitive-load workflows for NeuraDock EEG hardware."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="Run the no-hardware visual-load demo.")
    demo.add_argument("--output-root", default="runs")
    demo.add_argument("--duration", type=float, default=24.0)

    analyze = sub.add_parser(
        "analyze",
        aliases=["analysis"],
        help="Analyze one or more NeuraDock recordings.",
    )
    analyze.add_argument(
        "inputs",
        nargs="+",
        help=(
            "TXT/NPY files, directories, or quoted glob patterns such as "
            "data/*.txt."
        ),
    )
    analyze.add_argument(
        "--workflow",
        nargs="+",
        default=["quality"],
        metavar="NAME",
        help=(
            "Workflow: quality, alpha dynamics, visual cognition index, "
            "visual cognition comparison, or psd."
        ),
    )
    analyze.add_argument("--window-sec", type=float, default=4.0)
    analyze.add_argument("--step-sec", type=float, default=1.0)
    analyze.add_argument("--output-root", default="runs")
    analyze.add_argument(
        "--exclude-trials",
        default="",
        metavar="LIST",
        help="Exclude one-based NPY trials, for example 2,5,10-12.",
    )
    analyze.add_argument(
        "--exclude-rest-trials",
        default="",
        metavar="LIST",
        help="Comparison only: one-based trials to exclude from the first input.",
    )
    analyze.add_argument(
        "--exclude-task-trials",
        default="",
        metavar="LIST",
        help="Comparison only: one-based trials to exclude from the second input.",
    )
    analyze.add_argument(
        "--condition-labels",
        nargs=2,
        default=("Rest", "Task"),
        metavar=("REFERENCE", "COMPARISON"),
        help="Comparison labels for the first and second input.",
    )
    analyze.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively discover TXT and NPY files inside input directories.",
    )

    doctor = sub.add_parser("doctor", help="Diagnose a live NeuraDock TCP stream.")
    doctor.add_argument("--ip", required=True)
    doctor.add_argument("--port", required=True, type=int)
    doctor.add_argument("--windows", type=int, default=3)
    doctor.add_argument("--output-root", default="runs")

    serve = sub.add_parser(
        "serve",
        help="Start the online visual cognitive-load API and HTML dashboard.",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--demo-file",
        default=None,
        help=(
            "Optional TXT file streamed into the dashboard. When omitted, "
            "the Agent generates a deterministic synthetic replay."
        ),
    )
    serve.add_argument("--window-sec", type=float, default=4.0)
    serve.add_argument("--step-sec", type=float, default=1.0)

    online = sub.add_parser(
        "online",
        help="Connect to live NeuraDock data and open the workload dashboard.",
    )
    online.add_argument("--ip", required=True, help="NeuraDock realtime stream IP.")
    online.add_argument(
        "--port",
        required=True,
        type=int,
        help="NeuraDock realtime stream port.",
    )
    online.add_argument("--host", default="127.0.0.1")
    online.add_argument("--dashboard-port", type=int, default=8765)
    online.add_argument("--window-sec", type=float, default=4.0)
    online.add_argument("--step-sec", type=float, default=1.0)
    online.add_argument(
        "--no-open",
        action="store_true",
        help="Start the server without opening the browser automatically.",
    )

    ask = sub.add_parser("ask", help="Route natural language to a reviewed workflow.")
    ask.add_argument("request")
    ask.add_argument("--file")
    ask.add_argument("--file2")
    ask.add_argument(
        "--exclude-trials",
        default="",
        help="One-based NPY trials to exclude from --file.",
    )
    ask.add_argument(
        "--exclude-file2-trials",
        default="",
        help="One-based NPY trials to exclude from --file2.",
    )
    ask.add_argument("--ip")
    ask.add_argument("--port", type=int)
    ask.add_argument(
        "--llm",
        action="store_true",
        help="Use the saved LLM for workflow selection and result explanation.",
    )
    ask.add_argument("--output-root", default="runs")

    sub.add_parser("profile", help="Show the fixed NeuraDock hardware profile.")
    return parser


def _print_result(run) -> None:
    print("")
    print("NeuraDock workflow complete")
    trace_path = run.run_dir / "agent_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        print(f"Workflow: {trace.get('intent', 'unknown')}")
    print(f"Summary : {summarize_run(run)}")
    print(f"Report  : {run.report_path}")
    print(f"Results : {run.results_path}")
    for figure in run.figure_paths:
        print(f"Figure  : {figure}")
    for data_path in run.data_paths:
        print(f"Data    : {data_path}")
    interpretation = run.run_dir / "llm_interpretation.md"
    if interpretation.exists():
        print(f"LLM     : {interpretation}")


def _print_llm_interpretation(run) -> None:
    path = run.run_dir / "llm_interpretation.md"
    if not path.exists():
        return
    try:
        content = _read_text_with_retry(path).strip()
    except OSError as exc:
        print("")
        print("LLM interpretation was saved but could not be displayed immediately.")
        print(f"File: {path}")
        print(f"Reason: {exc}")
        return
    print("")
    print(content)


def _resolve_analyze_inputs(values: List[str], recursive: bool = False) -> List[Path]:
    """Expand files, directories, and shell-independent glob patterns."""

    resolved: List[Path] = []
    seen = set()

    def add_file(path: Path) -> None:
        target = path.expanduser().resolve()
        key = str(target).casefold()
        if target.is_file() and key not in seen:
            resolved.append(target)
            seen.add(key)

    def add_directory(path: Path) -> None:
        iterator = path.rglob("*") if recursive else path.iterdir()
        txt_files = (
            child
            for child in iterator
            if child.is_file()
            and child.suffix.casefold() in {".txt", ".npy"}
        )
        for child in sorted(txt_files, key=lambda item: str(item).casefold()):
            add_file(child)

    for value in values:
        expanded = str(Path(value).expanduser())
        if glob.has_magic(expanded):
            matches = [Path(item) for item in glob.glob(expanded, recursive=recursive)]
            txt_matches = [
                item
                for item in matches
                if item.is_dir()
                or item.suffix.casefold() in {".txt", ".npy"}
            ]
            if not txt_matches:
                raise FileNotFoundError(
                    f"No TXT or NPY files matched input pattern: {value}"
                )
            for match in sorted(txt_matches):
                add_directory(match) if match.is_dir() else add_file(match)
            continue

        candidate = Path(expanded)
        if candidate.is_dir():
            add_directory(candidate)
        elif candidate.is_file():
            add_file(candidate)
        else:
            raise FileNotFoundError(f"Analyze input not found: {candidate.resolve()}")

    if not resolved:
        raise ValueError("No TXT or NPY recordings were found in the analyze inputs.")
    return resolved


def _normalize_workflow(value: object) -> str:
    parts = value if isinstance(value, list) else [str(value)]
    name = " ".join(str(part) for part in parts).strip().casefold()
    aliases = {
        "quality": "quality",
        "alpha": "alpha_dynamics",
        "alpha dynamics": "alpha_dynamics",
        "alpha-dynamics": "alpha_dynamics",
        "alpha_dynamics": "alpha_dynamics",
        "psd": "psd",
        "visual cognition index": "visual_cognition_index",
        "visual-cognition-index": "visual_cognition_index",
        "visual_cognition_index": "visual_cognition_index",
        "visual cognition comparison": "visual_cognition_comparison",
        "visual cognitive load comparison": "visual_cognition_comparison",
        "visual-cognition-comparison": "visual_cognition_comparison",
        "visual_cognition_comparison": "visual_cognition_comparison",
    }
    try:
        return aliases[name]
    except KeyError as exc:
        raise ValueError(
            "Unknown workflow. Choose quality, alpha dynamics, visual cognition "
            "index, visual cognition comparison, or psd."
        ) from exc


def _batch_run_name(source: Path, workflow: str) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._-")
    safe_stem = safe_stem or "recording"
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    workflow_names = {
        "quality": "signal_quality",
        "alpha_dynamics": "alpha_dynamics",
        "psd": "psd_bandpower",
        "visual_cognition_index": "visual_cognitive_load",
        "visual_cognition_comparison": "visual_cognitive_load_comparison",
    }
    workflow_name = workflow_names[workflow]
    return f"{stamp}_{safe_stem}_{workflow_name}"


def _run_analyze_batch(args: argparse.Namespace) -> int:
    workflow = _normalize_workflow(args.workflow)
    files = _resolve_analyze_inputs(args.inputs, recursive=args.recursive)
    common_excluded = set(parse_trial_selection(args.exclude_trials))

    if workflow == "visual_cognition_comparison":
        if len(files) != 2:
            raise ValueError(
                "Visual cognition comparison requires exactly two inputs in "
                "Rest-then-Task order."
            )
        rest_excluded = tuple(
            sorted(
                common_excluded
                | set(parse_trial_selection(args.exclude_rest_trials))
            )
        )
        task_excluded = tuple(
            sorted(
                common_excluded
                | set(parse_trial_selection(args.exclude_task_trials))
            )
        )
        rest = read_neuradock_input(files[0], exclude_trials=rest_excluded)
        task = read_neuradock_input(files[1], exclude_trials=task_excluded)
        run = run_visual_cognitive_load_comparison(
            rest,
            task,
            args.output_root,
            window_sec=args.window_sec,
            step_sec=args.step_sec,
            condition_labels=tuple(args.condition_labels),
        )
        _print_result(run)
        return 0

    if args.exclude_rest_trials or args.exclude_task_trials:
        raise ValueError(
            "--exclude-rest-trials and --exclude-task-trials require the "
            "visual cognition comparison workflow."
        )
    is_batch = len(files) > 1
    successes = []
    failures = []
    clean_entries = []

    if is_batch:
        print(f"NeuraDock batch analysis: {len(files)} files")

    for index, source in enumerate(files, start=1):
        if is_batch:
            print("")
            print(f"[{index}/{len(files)}] Processing: {source}")
        try:
            recording = read_neuradock_input(
                source,
                exclude_trials=tuple(sorted(common_excluded)),
            )
            run_name = _batch_run_name(source, workflow) if is_batch else None
            if workflow == "quality":
                run = run_signal_quality(
                    recording,
                    args.output_root,
                    run_name=run_name,
                )
            elif workflow == "alpha_dynamics":
                run = run_alpha_dynamics(
                    recording,
                    args.output_root,
                    run_name=run_name,
                    window_sec=args.window_sec,
                    step_sec=args.step_sec,
                )
            elif workflow == "psd":
                run = run_psd_bandpower(
                    recording,
                    args.output_root,
                    run_name=run_name,
                )
            else:
                run = run_visual_cognitive_load(
                    recording,
                    args.output_root,
                    window_sec=args.window_sec,
                    step_sec=args.step_sec,
                    run_name=run_name,
                )
            _print_result(run)
            successes.append(
                {
                    "source": str(source),
                    "run_dir": str(run.run_dir),
                    "report": str(run.report_path),
                    "results": str(run.results_path),
                    "figures": [str(path) for path in run.figure_paths],
                    "data": [str(path) for path in run.data_paths],
                }
            )
            if (
                workflow == "quality"
                and source.suffix.casefold() == ".txt"
                and run.data_paths
            ):
                clean_entries.append((source, run.data_paths[0]))
        except (FileNotFoundError, ValueError, OSError) as exc:
            failures.append({"source": str(source), "error": str(exc)})
            print(f"Error processing {source}: {exc}", file=sys.stderr)

    if is_batch:
        batch_data_path = None
        if workflow == "quality" and clean_entries:
            batch_data_path = write_batch_clean_npz(
                Path(args.output_root) / "clean_eeg_data_batch.npz",
                clean_entries,
            )
        print("")
        print("NeuraDock batch complete")
        print(f"Successful: {len(successes)}")
        print(f"Failed    : {len(failures)}")
        if batch_data_path is not None:
            print(f"Batch data: {batch_data_path}")

    return 1 if failures else 0


def _deterministic_menu() -> int:
    print("")
    print("1. No-hardware demo")
    print("2. Check one recording")
    print("3. Alpha dynamics")
    print("4. Offline visual cognitive load")
    print("5. Device Doctor")
    print("6. Compare Rest and Task visual cognitive load")
    choice = input("Choose 1-6: ").strip()
    output_root = input("Output directory [runs]: ").strip() or "runs"
    if choice == "1":
        demo_path = generate_visual_load_demo_file(
            Path(output_root) / "demo_inputs",
        )
        run = run_visual_cognitive_load(
            read_neuradock_txt(demo_path),
            output_root=output_root,
        )
    elif choice in {"2", "3"}:
        path = input("NeuraDock recording path: ").strip()
        recording = read_neuradock_input(path)
        run = (
            run_signal_quality(recording, output_root)
            if choice == "2"
            else run_alpha_dynamics(recording, output_root)
        )
    elif choice == "4":
        recording = read_neuradock_input(
            input("NeuraDock recording path: ").strip()
        )
        run = run_visual_cognitive_load(recording, output_root)
    elif choice == "5":
        ip = input("Device IP: ").strip()
        port = int(input("Device port: ").strip())
        run = run_device_doctor(ip, port, output_root=output_root)
    elif choice == "6":
        rest = read_neuradock_input(input("Rest EEG path: ").strip())
        task = read_neuradock_input(input("Task EEG path: ").strip())
        run = run_visual_cognitive_load_comparison(
            rest,
            task,
            output_root,
        )
    else:
        print("Unknown selection.")
        return 2
    _print_result(run)
    return 0


def _print_llm_menu(model: str) -> None:
    print("")
    print(f"LLM mode ready. Current model: {model}")
    print("")
    print("What can I do for you?")
    print("1. Check EEG signal quality")
    print("2. Analyze Alpha dynamics")
    print("3. Estimate offline visual cognitive load")
    print("4. Diagnose a live NeuraDock device")
    print("5. Run the no-hardware demonstration")
    print("6. Compare Rest and Task visual cognitive load")
    print("")
    print("Type 1-6 or describe your request in natural language.")
    print(
        "Commands: /file PATH, /file2 PATH, /exclude-trials LIST, "
        "/exclude-file2-trials LIST, /output PATH, /config LLM, "
        "/mode local, /help, /exit"
    )


def _llm_mode() -> int:
    config = load_or_prompt_llm_config()
    current_file: Optional[Path] = None
    second_file: Optional[Path] = None
    excluded_trials: Tuple[int, ...] = ()
    excluded_second_trials: Tuple[int, ...] = ()
    output_root = Path("runs")
    menu_requests = {
        "1": "Check the EEG recording's signal quality.",
        "2": "Analyze posterior Alpha dynamics for the EEG recording.",
        "3": "Estimate offline visual cognitive load for the EEG recording.",
        "4": "Diagnose the live NeuraDock device.",
        "5": "Run the no-hardware demonstration.",
        "6": "Compare Rest and Task visual cognitive load using two EEG recordings.",
    }
    _print_llm_menu(config.model)

    while True:
        try:
            request = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExited LLM mode.")
            return 0
        if not request:
            continue
        normalized = request.casefold()
        if normalized in {"/exit", "/quit"}:
            return 0
        if normalized == "/mode local":
            return _deterministic_menu()
        if normalized == "/config llm":
            config = prompt_for_llm_config()
            _print_llm_menu(config.model)
            continue
        if normalized.startswith("/file "):
            candidate = Path(request[6:].strip().strip('"')).expanduser().resolve()
            if not candidate.is_file():
                print(f"File not found: {candidate}")
                continue
            current_file = candidate
            print(f"Current EEG file: {current_file}")
            continue
        if normalized.startswith("/file2 "):
            candidate = Path(request[7:].strip().strip('"')).expanduser().resolve()
            if not candidate.is_file():
                print(f"File not found: {candidate}")
                continue
            second_file = candidate
            print(f"Second EEG file: {second_file}")
            continue
        if normalized.startswith("/exclude-trials "):
            excluded_trials = parse_trial_selection(request[16:].strip())
            print(f"Excluded trials for first file: {excluded_trials or 'none'}")
            continue
        if normalized.startswith("/exclude-file2-trials "):
            excluded_second_trials = parse_trial_selection(
                request[22:].strip()
            )
            print(
                "Excluded trials for second file: "
                f"{excluded_second_trials or 'none'}"
            )
            continue
        if normalized.startswith("/output "):
            output_root = Path(request[8:].strip().strip('"')).expanduser()
            print(f"Output directory: {output_root.resolve()}")
            continue
        if normalized == "/help":
            _print_llm_menu(config.model)
            continue
        request = menu_requests.get(normalized, request)

        local_hint = route_intent(request)
        ip = None
        port = None
        if local_hint == "device_doctor":
            ip = input("Device IP: ").strip()
            port = int(input("Device port: ").strip())
        elif local_hint == "visual_cognitive_load_comparison":
            if current_file is None:
                value = input("Rest EEG file path: ").strip().strip('"')
                candidate = Path(value).expanduser().resolve()
                if not value or not candidate.is_file():
                    print(f"File not found: {candidate}")
                    continue
                current_file = candidate
            if second_file is None:
                value = input("Task EEG file path: ").strip().strip('"')
                candidate = Path(value).expanduser().resolve()
                if not value or not candidate.is_file():
                    print(f"File not found: {candidate}")
                    continue
                second_file = candidate
        elif local_hint != "demo" and current_file is None:
            value = input("EEG TXT or NPY file path: ").strip().strip('"')
            if not value:
                print("No EEG file selected. Use /file PATH first.")
                continue
            candidate = Path(value).expanduser().resolve()
            if not candidate.is_file():
                print(f"File not found: {candidate}")
                continue
            current_file = candidate

        print("Selecting a reviewed workflow and running local deterministic analysis...")
        try:
            run = execute_request(
                request,
                AgentInputs(
                    file=current_file,
                    file2=second_file,
                    ip=ip,
                    port=port,
                    exclude_trials=excluded_trials,
                    exclude_file2_trials=excluded_second_trials,
                ),
                output_root,
                use_llm=True,
                llm_config=config,
            )
        except (FileNotFoundError, ValueError, ConnectionError, OSError) as exc:
            print(f"Request failed: {exc}")
            continue
        _print_result(run)
        _print_llm_interpretation(run)


def _interactive() -> int:
    print("NeuraDock Agent v0.1")
    print("Local deterministic EEG analysis with optional privacy-bounded LLM assistance.")
    print("")
    print("Enter /mode LLM to start LLM mode.")
    print("Enter /menu for the local menu or /exit to quit.")
    while True:
        command = input("neuradock> ").strip()
        normalized = command.casefold()
        if normalized == "/mode llm":
            return _llm_mode()
        if normalized in {"/menu", "/mode local"}:
            return _deterministic_menu()
        if normalized in {"/exit", "/quit"}:
            return 0
        print("Unknown command. Use /mode LLM, /menu, or /exit.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        try:
            return _interactive()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 130
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    try:
        if args.command == "demo":
            inputs = Path(args.output_root) / "demo_inputs"
            demo_path = generate_visual_load_demo_file(inputs, args.duration)
            run = run_visual_cognitive_load(
                read_neuradock_txt(demo_path),
                output_root=args.output_root,
            )
            _print_result(run)
            return 0
        if args.command in {"analyze", "analysis"}:
            return _run_analyze_batch(args)
        if args.command == "doctor":
            run = run_device_doctor(
                args.ip, args.port, args.windows, args.output_root
            )
            _print_result(run)
            return 0
        if args.command == "serve":
            demo_file = (
                Path(args.demo_file).expanduser().resolve()
                if args.demo_file
                else generate_visual_load_demo_file(
                    Path("runs") / "demo_inputs",
                    duration_sec=90.0,
                    file_name="synthetic_visual_load_replay.txt",
                )
            )
            serve_online_dashboard(
                host=args.host,
                port=args.port,
                demo_file=demo_file,
                window_sec=args.window_sec,
                step_sec=args.step_sec,
            )
            return 0
        if args.command == "online":
            serve_online_dashboard(
                host=args.host,
                port=args.dashboard_port,
                demo_file=None,
                device_ip=args.ip,
                device_port=args.port,
                window_sec=args.window_sec,
                step_sec=args.step_sec,
                open_browser=not args.no_open,
            )
            return 0
        if args.command == "ask":
            llm_config = load_or_prompt_llm_config() if args.llm else None
            run = execute_request(
                args.request,
                AgentInputs(
                    file=args.file,
                    file2=args.file2,
                    ip=args.ip,
                    port=args.port,
                    exclude_trials=parse_trial_selection(args.exclude_trials),
                    exclude_file2_trials=parse_trial_selection(
                        args.exclude_file2_trials
                    ),
                ),
                args.output_root,
                use_llm=args.llm,
                llm_config=llm_config,
            )
            _print_result(run)
            if args.llm:
                _print_llm_interpretation(run)
            return 0
        if args.command == "profile":
            print(json.dumps(PROFILE.to_dict(), indent=2))
            return 0
    except (FileNotFoundError, ValueError, ConnectionError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2
