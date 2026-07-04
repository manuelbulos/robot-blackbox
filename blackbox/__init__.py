"""robot-blackbox: the flight recorder for robots.

Records synchronized robot telemetry, policy actions, and human
interventions on a shared clock, then turns them into reliability
metrics no one in the industry can produce today: interventions per
1,000 robot-hours, MTBF, failure clusters, and cross-version
regression detection.
"""

from blackbox.schema import (
    ActionRecord,
    EpisodeMeta,
    Frame,
    InterventionEvent,
    Outcome,
)
from blackbox.recorder import Recorder, Session

__all__ = [
    "ActionRecord",
    "EpisodeMeta",
    "Frame",
    "InterventionEvent",
    "Outcome",
    "Recorder",
    "Session",
]

__version__ = "0.1.0"
