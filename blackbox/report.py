"""Static HTML dashboard: the reliability report a robot company can
hand to its customer, insurer, or safety auditor.

Single self-contained file (Chart.js via CDN), no server needed.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from blackbox.clustering import cluster_failures
from blackbox.metrics import ReliabilityReport, SessionData, analyze, detect_regressions

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>robot-blackbox — Reliability Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --good: #3fb950; --warn: #d29922; --bad: #f85149;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: var(--bg); color: var(--text);
         font: 15px/1.5 -apple-system, "Segoe UI", sans-serif; padding: 32px; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 16px; margin: 28px 0 12px; }}
  .sub {{ color: var(--muted); margin: 4px 0 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 10px; padding: 16px 18px; }}
  .card .v {{ font-size: 26px; font-weight: 700; }}
  .card .k {{ color: var(--muted); font-size: 12.5px; text-transform: uppercase;
              letter-spacing: .04em; margin-top: 2px; }}
  .good {{ color: var(--good); }} .warn {{ color: var(--warn); }} .bad {{ color: var(--bad); }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .panel {{ background: var(--card); border: 1px solid var(--border);
            border-radius: 10px; padding: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; font-size: 12.5px; text-transform: uppercase; }}
  .alert {{ background: rgba(248,81,73,.1); border: 1px solid var(--bad);
            border-radius: 10px; padding: 12px 16px; margin: 8px 0; color: var(--bad); }}
  .footer {{ color: var(--muted); font-size: 12.5px; margin-top: 36px; }}
  canvas {{ max-height: 260px; }}
</style>
</head>
<body>
<h1>Reliability Report</h1>
<p class="sub">{session_name} &middot; generated {today} &middot; robot-blackbox v0.1</p>

<div class="cards">
  <div class="card"><div class="v">{iv_per_1000h:.0f}</div><div class="k">Interventions / 1,000 robot-h</div></div>
  <div class="card"><div class="v">{mtbf}</div><div class="k">MTBF (mean time between failures)</div></div>
  <div class="card"><div class="v {success_class}">{success_rate:.1%}</div><div class="k">Autonomous success rate</div></div>
  <div class="card"><div class="v">{robot_hours:.0f} h</div><div class="k">Robot hours recorded</div></div>
  <div class="card"><div class="v">{n_interventions}</div><div class="k">Human interventions</div></div>
  <div class="card"><div class="v">{operator_minutes:.0f} min</div><div class="k">Operator time consumed</div></div>
</div>

{regression_alerts}

<h2>Failure root causes</h2>
<div class="grid2">
  <div class="panel"><canvas id="causes"></canvas></div>
  <div class="panel"><canvas id="kinds"></canvas></div>
</div>

<h2>Model version comparison</h2>
<div class="panel">
<table>
<tr><th>Version</th><th>Episodes</th><th>Robot-h</th><th>Success</th><th>Interventions</th><th>Per 1,000 h</th></tr>
{version_rows}
</table>
</div>

<h2>Failure clusters (from telemetry signatures)</h2>
<div class="panel">
<table>
<tr><th>#</th><th>Count</th><th>Dominant cause</th><th>Phase</th><th>Mean recovery</th><th>Mean grip force</th></tr>
{cluster_rows}
</table>
</div>

<p class="footer">Every metric on this page is computed from synchronized
telemetry, policy actions, and operator interventions recorded on a shared
clock. Evidence, not estimates.</p>

<script>
const style = getComputedStyle(document.documentElement);
Chart.defaults.color = style.getPropertyValue('--muted');
Chart.defaults.borderColor = style.getPropertyValue('--border');
new Chart(document.getElementById('causes'), {{
  type: 'bar',
  data: {{ labels: {cause_labels}, datasets: [{{ label: 'Interventions by root cause',
    data: {cause_values}, backgroundColor: '#58a6ff' }}] }},
  options: {{ plugins: {{ legend: {{ display: true }} }} }}
}});
new Chart(document.getElementById('kinds'), {{
  type: 'doughnut',
  data: {{ labels: {kind_labels}, datasets: [{{ label: 'By intervention type',
    data: {kind_values},
    backgroundColor: ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff'] }}] }},
  options: {{ plugins: {{ legend: {{ position: 'right' }} }} }}
}});
</script>
</body>
</html>
"""


def render_report(session_dir: str | Path, out_path: str | Path | None = None) -> Path:
    session_dir = Path(session_dir)
    data = SessionData.load(session_dir, include_streams=True)
    report: ReliabilityReport = analyze(data)
    clusters = cluster_failures(data)
    regressions = detect_regressions(report)

    version_rows = "\n".join(
        f"<tr><td>{v}</td><td>{m['episodes']}</td><td>{m['robot_hours']}</td>"
        f"<td>{m['success_rate']:.1%}</td><td>{m['interventions']}</td>"
        f"<td>{m['interventions_per_1000h']}</td></tr>"
        for v, m in sorted(report.by_model_version.items())
    )
    cluster_rows = "\n".join(
        f"<tr><td>{c['cluster']}</td><td>{c['count']}</td><td>{c['dominant_cause']}</td>"
        f"<td>{c['dominant_phase']}</td><td>{c['mean_recovery_s']} s</td>"
        f"<td>{c['mean_grip_force']}</td></tr>"
        for c in clusters
    ) or "<tr><td colspan=6>Not enough failures to cluster (a good problem).</td></tr>"

    alerts = "\n".join(f'<div class="alert">{w}</div>' for w in regressions)

    html = _TEMPLATE.format(
        session_name=session_dir.name,
        today=date.today().isoformat(),
        iv_per_1000h=report.interventions_per_1000h,
        mtbf=f"{report.mtbf_hours:.1f} h" if report.mtbf_hours else "n/a",
        success_rate=report.success_rate,
        success_class="good" if report.success_rate >= 0.95
                      else "warn" if report.success_rate >= 0.85 else "bad",
        robot_hours=report.robot_hours,
        n_interventions=report.n_interventions,
        operator_minutes=report.operator_minutes_total,
        regression_alerts=alerts,
        version_rows=version_rows,
        cluster_rows=cluster_rows,
        cause_labels=json.dumps(list(report.root_causes.keys())),
        cause_values=json.dumps(list(report.root_causes.values())),
        kind_labels=json.dumps(list(report.interventions_by_kind.keys())),
        kind_values=json.dumps(list(report.interventions_by_kind.values())),
    )
    out = Path(out_path) if out_path else session_dir / "report.html"
    out.write_text(html)
    return out
