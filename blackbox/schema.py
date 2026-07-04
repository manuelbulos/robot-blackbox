"""Episode data model.

Everything is recorded against a single monotonic session clock
(`t` = seconds since session start) so video, telemetry, actions, and
interventions can be replayed and cross-referenced exactly. Records are
persisted as JSONL, one file per stream, so a session directory is
greppable, diffable, and trivially ingestible by downstream tools
(pandas, LeRobot-style dataset converters, etc.).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RECOVERED = "recovered"  # failed, then recovered by a human
    ABORTED = "aborted"


class InterventionType(str, Enum):
    PAUSE = "pause"                 # operator paused the robot
    RESET = "reset"                 # cycle restarted from scratch
    TELEOP = "teleop"               # operator took manual control
    PHYSICAL_ASSIST = "physical"    # operator physically fixed the scene
    EMERGENCY_STOP = "estop"


@dataclass
class Frame:
    """One tick of robot state on the shared clock."""

    t: float
    joint_positions: list[float]
    joint_velocities: list[float]
    gripper_force: float
    gripper_aperture: float
    tcp_pose: list[float]  # tool-center-point [x, y, z, rx, ry, rz]
    camera_frame_id: str | None = None  # reference to an external frame store


@dataclass
class ActionRecord:
    """A policy output, tied to the model version that produced it."""

    t: float
    action: list[float]
    model_version: str
    task_phase: str  # e.g. "approach" | "grasp" | "transfer" | "place"
    confidence: float | None = None


@dataclass
class InterventionEvent:
    """A human stepping in. This is the record the industry doesn't keep."""

    t_start: float
    t_end: float
    kind: InterventionType
    operator_id: str
    task_phase: str
    root_cause: str | None = None  # filled by operator or by clustering
    note: str = ""

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


@dataclass
class EpisodeMeta:
    """One task attempt (cycle) inside a session."""

    episode_id: str
    task: str
    robot_id: str
    model_version: str
    t_start: float
    t_end: float = 0.0
    outcome: Outcome = Outcome.SUCCESS
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def to_jsonl(record: Any) -> str:
    d = asdict(record)
    # Enums serialize as their value
    for k, v in d.items():
        if isinstance(v, Enum):
            d[k] = v.value
    return json.dumps(d, separators=(",", ":"))
