"""CLI: `blackbox demo` runs the full pipeline end-to-end; `blackbox report` re-renders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blackbox.metrics import SessionData, analyze, detect_regressions
from blackbox.recorder import Recorder
from blackbox.report import render_report
from blackbox.sim import SimClock, SimConfig, run_simulation


def cmd_demo(args: argparse.Namespace) -> None:
    session_dir = Path(args.out)
    if session_dir.exists() and any(session_dir.iterdir()):
        print(f"error: {session_dir} is not empty; pick a fresh --out dir", file=sys.stderr)
        sys.exit(1)

    clock = SimClock()
    recorder = Recorder(session_dir, clock=clock)

    # Two model versions sharing one session: v1.2 baseline, then a "bad
    # update" v1.3 that regresses grasping — exactly what the regression
    # detector is for.
    run_simulation(recorder, clock, SimConfig(
        model_version="policy-v1.2.0",
        n_episodes=args.episodes,
        failure_rate=0.06,
        seed=7,
    ))
    run_simulation(recorder, clock, SimConfig(
        model_version="policy-v1.3.0",
        n_episodes=args.episodes,
        failure_rate=0.11,
        failure_mix={"grasp_slip": 5.0, "perception_miss": 1.0,
                     "joint_fault": 0.5, "collision": 0.5, "place_misalign": 1.0},
        seed=21,
    ))
    recorder.close()

    data = SessionData.load(session_dir)
    report = analyze(data)
    print(f"\nSession recorded to {session_dir}/\n")
    for line in report.summary_lines():
        print("  " + line)
    for warning in detect_regressions(report):
        print("\n  ⚠ " + warning)

    out = render_report(session_dir)
    print(f"\nDashboard: {out}\n")


def cmd_report(args: argparse.Namespace) -> None:
    data = SessionData.load(args.session)
    report = analyze(data)
    for line in report.summary_lines():
        print(line)
    for warning in detect_regressions(report):
        print("⚠ " + warning)
    out = render_report(args.session)
    print(f"Dashboard: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="blackbox",
                                     description="The flight recorder for robots.")
    sub = parser.add_subparsers(required=True)

    p_demo = sub.add_parser("demo", help="simulate a deployment and generate a report")
    p_demo.add_argument("--out", default="sessions/demo", help="session output dir")
    p_demo.add_argument("--episodes", type=int, default=200,
                        help="cycles per model version")
    p_demo.set_defaults(func=cmd_demo)

    p_rep = sub.add_parser("report", help="analyze an existing session")
    p_rep.add_argument("session", help="session directory")
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
