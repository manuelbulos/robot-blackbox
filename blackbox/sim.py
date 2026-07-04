"""Simulated 6-DoF arm running pick-and-place cycles with injectable failures.

This exists so the whole pipeline runs end-to-end without hardware.
The failure modes and their signatures are modeled on what real pilots
report (grasp slips, perception misses, joint faults, collisions), so the
downstream clustering and metrics behave like they would on real data.
The same Recorder API works unchanged against a ROS 2 or vendor adapter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from blackbox.recorder import Recorder
from blackbox.schema import InterventionType, Outcome

PHASES = ["approach", "grasp", "transfer", "place"]

# Failure mode -> (phase where it strikes, intervention kind, typical recovery seconds)
FAILURE_MODES = {
    "grasp_slip":      ("grasp",    InterventionType.RESET,           25.0),
    "perception_miss": ("approach", InterventionType.RESET,           15.0),
    "joint_fault":     ("transfer", InterventionType.EMERGENCY_STOP,  90.0),
    "collision":       ("transfer", InterventionType.PHYSICAL_ASSIST, 45.0),
    "place_misalign":  ("place",    InterventionType.TELEOP,          30.0),
}


@dataclass
class SimConfig:
    robot_id: str = "arm-01"
    task: str = "bin-pick"
    model_version: str = "policy-v1.2.0"
    n_episodes: int = 200
    cycle_seconds: float = 45.0
    failure_rate: float = 0.075  # ~1 failure every 13 cycles
    # Relative likelihood of each failure mode for this model version.
    failure_mix: dict[str, float] | None = None
    hz: float = 2.0  # frame logging rate (kept low so demos stay small)
    seed: int = 7


class SimClock:
    """Fake monotonic clock so 200 cycles 'run' instantly but timestamps are real."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _arm_frame(rng: np.ndarray, phase: str, failing: bool) -> dict:
    """Plausible joint state; failures leave a signature in force/velocity."""
    base = np.sin(rng) * 1.5
    vel = np.cos(rng) * 0.4
    force = 12.0 if phase in ("grasp", "transfer") else 1.5
    if failing:
        vel = vel * 3.0 + np.random.normal(0, 0.5, 6)  # jerky motion
        force = force * (0.2 if phase == "grasp" else 2.5)  # slip or jam
    return dict(
        joint_positions=base.round(4).tolist(),
        joint_velocities=vel.round(4).tolist(),
        gripper_force=round(float(force + np.random.normal(0, 0.3)), 3),
        gripper_aperture=round(random.uniform(0.0, 0.08), 4),
        tcp_pose=np.random.normal(0, 0.5, 6).round(4).tolist(),
    )


def run_simulation(recorder: Recorder, clock: SimClock, config: SimConfig) -> None:
    """Run `n_episodes` pick-place cycles, injecting failures per config."""
    random.seed(config.seed)
    np.random.seed(config.seed)
    mix = config.failure_mix or {m: 1.0 for m in FAILURE_MODES}
    modes, weights = zip(*mix.items())

    for _ in range(config.n_episodes):
        fail_mode = None
        if random.random() < config.failure_rate:
            fail_mode = random.choices(modes, weights=weights)[0]
        fail_phase = FAILURE_MODES[fail_mode][0] if fail_mode else None

        with recorder.episode(
            task=config.task,
            robot_id=config.robot_id,
            model_version=config.model_version,
        ) as ep:
            phase_dt = config.cycle_seconds / len(PHASES)
            rng = np.random.uniform(0, 3.14, 6)
            for phase in PHASES:
                failing = phase == fail_phase
                n_ticks = max(1, int(phase_dt * config.hz))
                for _ in range(n_ticks):
                    clock.advance(1.0 / config.hz)
                    ep.log_frame(**_arm_frame(rng, phase, failing))
                    ep.log_action(
                        action=np.random.normal(0, 0.2, 6).round(4).tolist(),
                        task_phase=phase,
                        confidence=round(random.uniform(0.55, 0.75) if failing
                                         else random.uniform(0.86, 0.99), 3),
                    )
                if failing:
                    _, kind, recovery_s = FAILURE_MODES[fail_mode]
                    with ep.intervention(
                        kind=kind,
                        operator_id=f"op-{random.randint(1, 4)}",
                        task_phase=phase,
                        root_cause=fail_mode,
                        note=f"scripted {fail_mode} during {phase}",
                    ):
                        clock.advance(recovery_s * random.uniform(0.7, 1.4))
                    break  # cycle ends after recovery

            ep.set_outcome(Outcome.RECOVERED if fail_mode else Outcome.SUCCESS)
