"""End-to-end tests: simulate, record, analyze, cluster, render."""

import json

from blackbox.clustering import cluster_failures
from blackbox.metrics import SessionData, analyze, detect_regressions
from blackbox.recorder import Recorder
from blackbox.report import render_report
from blackbox.sim import SimClock, SimConfig, run_simulation


def _make_session(tmp_path, failure_rate=0.2, n_episodes=60, version="v1"):
    clock = SimClock()
    rec = Recorder(tmp_path, clock=clock)
    run_simulation(rec, clock, SimConfig(
        model_version=version, n_episodes=n_episodes, failure_rate=failure_rate))
    return rec, clock


def test_records_all_streams(tmp_path):
    rec, _ = _make_session(tmp_path / "s")
    rec.close()
    for stream in ("frames", "actions", "interventions", "episodes"):
        lines = (tmp_path / "s" / f"{stream}.jsonl").read_text().splitlines()
        assert lines, f"{stream} is empty"
        json.loads(lines[0])  # valid JSONL


def test_metrics_are_consistent(tmp_path):
    rec, _ = _make_session(tmp_path / "s")
    rec.close()
    data = SessionData.load(tmp_path / "s")
    report = analyze(data)
    assert report.n_episodes == 60
    assert report.robot_hours > 0
    assert 0 < report.n_interventions < 60
    # every intervention implies a recovered (non-success) episode
    assert report.success_rate + report.recovered_rate <= 1.0 + 1e-9
    assert report.interventions_per_1000h > 0
    assert report.mtbf_hours is not None


def test_intervention_marks_episode_recovered(tmp_path):
    rec, _ = _make_session(tmp_path / "s", failure_rate=1.0, n_episodes=5)
    rec.close()
    data = SessionData.load(tmp_path / "s")
    assert all(e["outcome"] == "recovered" for e in data.episodes)


def test_regression_detection(tmp_path):
    clock = SimClock()
    rec = Recorder(tmp_path / "s", clock=clock)
    run_simulation(rec, clock, SimConfig(model_version="good", n_episodes=80,
                                         failure_rate=0.03, seed=1))
    run_simulation(rec, clock, SimConfig(model_version="bad", n_episodes=80,
                                         failure_rate=0.30, seed=2))
    rec.close()
    report = analyze(SessionData.load(tmp_path / "s"))
    warnings = detect_regressions(report)
    assert warnings and "bad" in warnings[0]


def test_clustering_finds_groups(tmp_path):
    rec, _ = _make_session(tmp_path / "s", failure_rate=0.5, n_episodes=100)
    rec.close()
    data = SessionData.load(tmp_path / "s", include_streams=True)
    clusters = cluster_failures(data)
    assert clusters
    assert sum(c["count"] for c in clusters) == len(data.interventions)


def test_report_renders(tmp_path):
    rec, _ = _make_session(tmp_path / "s")
    rec.close()
    out = render_report(tmp_path / "s")
    html = out.read_text()
    assert "Interventions / 1,000 robot-h" in html
    assert "chart.js" in html.lower()
