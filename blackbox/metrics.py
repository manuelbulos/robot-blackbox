"""Reliability analytics over recorded sessions.

Produces the numbers the robotics industry cannot answer today:
- interventions per 1,000 robot-hours
- MTBF (mean time between failures)
- success / recovered / failure rates
- root-cause breakdown and operator recovery-time cost
- regression detection across model versions
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


@dataclass
class SessionData:
    episodes: list[dict]
    interventions: list[dict]
    frames: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, session_dir: str | Path, include_streams: bool = False) -> "SessionData":
        d = Path(session_dir)
        return cls(
            episodes=_load_jsonl(d / "episodes.jsonl"),
            interventions=_load_jsonl(d / "interventions.jsonl"),
            frames=_load_jsonl(d / "frames.jsonl") if include_streams else [],
            actions=_load_jsonl(d / "actions.jsonl") if include_streams else [],
        )


@dataclass
class ReliabilityReport:
    robot_hours: float
    n_episodes: int
    n_interventions: int
    interventions_per_1000h: float
    mtbf_hours: float | None  # None if no failures observed
    success_rate: float
    recovered_rate: float
    mean_recovery_seconds: float
    operator_minutes_total: float
    root_causes: dict[str, int]
    interventions_by_kind: dict[str, int]
    by_model_version: dict[str, dict]

    def summary_lines(self) -> list[str]:
        mtbf = f"{self.mtbf_hours:.1f} h" if self.mtbf_hours else "n/a (no failures)"
        return [
            f"Robot hours recorded:        {self.robot_hours:.1f}",
            f"Episodes (cycles):           {self.n_episodes}",
            f"Human interventions:         {self.n_interventions}",
            f"Interventions / 1,000 h:     {self.interventions_per_1000h:.0f}",
            f"MTBF:                        {mtbf}",
            f"Autonomous success rate:     {self.success_rate:.1%}",
            f"Human-recovered rate:        {self.recovered_rate:.1%}",
            f"Mean recovery time:          {self.mean_recovery_seconds:.0f} s",
            f"Operator time consumed:      {self.operator_minutes_total:.0f} min",
        ]


def analyze(data: SessionData) -> ReliabilityReport:
    episodes, interventions = data.episodes, data.interventions
    robot_seconds = sum(e["t_end"] - e["t_start"] for e in episodes)
    robot_hours = robot_seconds / 3600.0
    n_ep = len(episodes)
    n_iv = len(interventions)

    outcomes = Counter(e["outcome"] for e in episodes)
    recovery_times = [iv["t_end"] - iv["t_start"] for iv in interventions]

    by_version: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in episodes:
        grouped[e["model_version"]].append(e)
    # Interventions are attributed to the episode window they fall inside.
    iv_by_version: dict[str, int] = defaultdict(int)
    for iv in interventions:
        for e in episodes:
            if e["t_start"] <= iv["t_start"] <= e["t_end"]:
                iv_by_version[e["model_version"]] += 1
                break
    for version, eps in grouped.items():
        hours = sum(e["t_end"] - e["t_start"] for e in eps) / 3600.0
        n = len(eps)
        ok = sum(1 for e in eps if e["outcome"] == "success")
        by_version[version] = {
            "episodes": n,
            "robot_hours": round(hours, 2),
            "success_rate": round(ok / n, 4) if n else 0.0,
            "interventions": iv_by_version.get(version, 0),
            "interventions_per_1000h": round(iv_by_version.get(version, 0) / hours * 1000.0, 1)
            if hours > 0 else 0.0,
        }

    return ReliabilityReport(
        robot_hours=robot_hours,
        n_episodes=n_ep,
        n_interventions=n_iv,
        interventions_per_1000h=(n_iv / robot_hours * 1000.0) if robot_hours > 0 else 0.0,
        mtbf_hours=(robot_hours / n_iv) if n_iv else None,
        success_rate=outcomes.get("success", 0) / n_ep if n_ep else 0.0,
        recovered_rate=outcomes.get("recovered", 0) / n_ep if n_ep else 0.0,
        mean_recovery_seconds=(sum(recovery_times) / len(recovery_times)) if recovery_times else 0.0,
        operator_minutes_total=sum(recovery_times) / 60.0,
        root_causes=dict(Counter(iv.get("root_cause") or "unlabeled" for iv in interventions)),
        interventions_by_kind=dict(Counter(iv["kind"] for iv in interventions)),
        by_model_version=by_version,
    )


def detect_regressions(report: ReliabilityReport, threshold: float = 1.25) -> list[str]:
    """Flag model versions whose intervention rate is worse than the fleet best.

    `threshold` = how many times worse than the best version before we flag.
    """
    versions = {
        v: m for v, m in report.by_model_version.items() if m["robot_hours"] > 0
    }
    if len(versions) < 2:
        return []
    best_version, best = min(versions.items(), key=lambda kv: kv[1]["interventions_per_1000h"])
    warnings = []
    for version, m in versions.items():
        if version == best_version:
            continue
        rate, best_rate = m["interventions_per_1000h"], best["interventions_per_1000h"]
        if best_rate == 0:
            if rate > 0:
                warnings.append(
                    f"REGRESSION: {version} has {rate:.0f} interventions/1000h "
                    f"vs zero on {best_version}."
                )
        elif rate / best_rate >= threshold:
            warnings.append(
                f"REGRESSION: {version} intervention rate is {rate / best_rate:.1f}x "
                f"{best_version} ({rate:.0f} vs {best_rate:.0f} per 1,000 h)."
            )
    return warnings
