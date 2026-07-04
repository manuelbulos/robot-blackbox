"""The recorder: shared-clock capture of everything the robot does.

Usage:

    rec = Recorder(session_dir="sessions/plant-a")
    with rec.episode(task="bin-pick", robot_id="arm-01", model_version="v1.2") as ep:
        for state in robot:                # your control loop
            ep.log_frame(...)
            ep.log_action(...)
        # when a human steps in:
        with ep.intervention(kind=InterventionType.RESET, operator_id="op-7",
                             task_phase="grasp", root_cause="grasp_slip"):
            recover()
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from blackbox.schema import (
    ActionRecord,
    EpisodeMeta,
    Frame,
    InterventionEvent,
    InterventionType,
    Outcome,
    to_jsonl,
)


class Session:
    """A recording session: one robot, one site, one continuous run."""

    def __init__(self, session_dir: str | Path, clock=time.monotonic):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._t0 = clock()
        self._files = {
            name: open(self.dir / f"{name}.jsonl", "a", buffering=1)
            for name in ("frames", "actions", "interventions", "episodes")
        }

    def now(self) -> float:
        """Seconds since session start on the shared monotonic clock."""
        return self._clock() - self._t0

    def write(self, stream: str, record) -> None:
        self._files[stream].write(to_jsonl(record) + "\n")

    def close(self) -> None:
        for f in self._files.values():
            f.close()


class EpisodeHandle:
    """Logging surface for one task attempt."""

    def __init__(self, session: Session, meta: EpisodeMeta):
        self._session = session
        self.meta = meta
        self._intervened = False

    def log_frame(self, **kwargs) -> None:
        self._session.write("frames", Frame(t=self._session.now(), **kwargs))

    def log_action(self, **kwargs) -> None:
        kwargs.setdefault("model_version", self.meta.model_version)
        self._session.write("actions", ActionRecord(t=self._session.now(), **kwargs))

    @contextmanager
    def intervention(
        self,
        kind: InterventionType,
        operator_id: str,
        task_phase: str,
        root_cause: str | None = None,
        note: str = "",
    ):
        """Wrap the human-recovery block; timing is captured automatically."""
        t_start = self._session.now()
        try:
            yield
        finally:
            event = InterventionEvent(
                t_start=t_start,
                t_end=self._session.now(),
                kind=kind,
                operator_id=operator_id,
                task_phase=task_phase,
                root_cause=root_cause,
                note=note,
            )
            self._session.write("interventions", event)
            self._intervened = True

    def set_outcome(self, outcome: Outcome) -> None:
        self.meta.outcome = outcome


class Recorder:
    def __init__(self, session_dir: str | Path, clock=time.monotonic):
        self.session = Session(session_dir, clock=clock)

    @contextmanager
    def episode(self, task: str, robot_id: str, model_version: str):
        meta = EpisodeMeta(
            episode_id=uuid.uuid4().hex[:12],
            task=task,
            robot_id=robot_id,
            model_version=model_version,
            t_start=self.session.now(),
        )
        handle = EpisodeHandle(self.session, meta)
        try:
            yield handle
        finally:
            meta.t_end = self.session.now()
            # A success that required a human is not a success.
            if handle._intervened and meta.outcome == Outcome.SUCCESS:
                meta.outcome = Outcome.RECOVERED
            self.session.write("episodes", meta)

    def close(self) -> None:
        self.session.close()
