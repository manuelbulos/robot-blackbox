"""Failure clustering: group interventions by their telemetry signature.

Operators rarely label root causes consistently (or at all). This module
featurizes the telemetry window preceding each intervention and clusters
the failures, so "what keeps going wrong" emerges from the data itself.

Hand-rolled k-means on numpy: zero extra dependencies, and failure
featurization matters far more than the clustering algorithm here.
"""

from __future__ import annotations

import numpy as np

from blackbox.metrics import SessionData

WINDOW_S = 5.0  # telemetry seconds before the intervention to featurize

PHASE_INDEX = {"approach": 0, "grasp": 1, "transfer": 2, "place": 3}


def featurize(data: SessionData) -> tuple[np.ndarray, list[dict]]:
    """One feature row per intervention from its preceding telemetry window."""
    frames = sorted(data.frames, key=lambda f: f["t"])
    times = np.array([f["t"] for f in frames])
    rows, kept = [], []
    for iv in data.interventions:
        lo, hi = np.searchsorted(times, [iv["t_start"] - WINDOW_S, iv["t_start"]])
        window = frames[lo:hi]
        if not window:
            continue
        vel = np.array([f["joint_velocities"] for f in window])
        force = np.array([f["gripper_force"] for f in window])
        rows.append([
            float(np.abs(vel).mean()),        # jerkiness
            float(np.abs(vel).max()),
            float(force.mean()),               # grip signature (low=slip, high=jam)
            float(force.std()),
            float(PHASE_INDEX.get(iv["task_phase"], -1)),
            float(iv["t_end"] - iv["t_start"]),  # recovery cost
        ])
        kept.append(iv)
    return np.array(rows), kept


def kmeans(x: np.ndarray, k: int, iters: int = 50, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    # Normalize features so recovery-seconds don't dominate
    mu, sigma = x.mean(axis=0), x.std(axis=0) + 1e-9
    z = (x - mu) / sigma
    centers = z[rng.choice(len(z), size=min(k, len(z)), replace=False)]
    labels = np.zeros(len(z), dtype=int)
    for _ in range(iters):
        dists = np.linalg.norm(z[:, None] - centers[None], axis=2)
        new_labels = dists.argmin(axis=1)
        if (new_labels == labels).all():
            break
        labels = new_labels
        for i in range(len(centers)):
            members = z[labels == i]
            if len(members):
                centers[i] = members.mean(axis=0)
    return labels


def cluster_failures(data: SessionData, k: int = 4) -> list[dict]:
    """Cluster interventions; report each cluster with its dominant traits."""
    x, interventions = featurize(data)
    if len(x) < k:
        return []
    labels = kmeans(x, k)
    clusters = []
    for i in range(k):
        idx = np.where(labels == i)[0]
        if not len(idx):
            continue
        members = [interventions[j] for j in idx]
        causes = {}
        for m in members:
            c = m.get("root_cause") or "unlabeled"
            causes[c] = causes.get(c, 0) + 1
        phases = {}
        for m in members:
            phases[m["task_phase"]] = phases.get(m["task_phase"], 0) + 1
        clusters.append({
            "cluster": i,
            "count": len(members),
            "dominant_cause": max(causes, key=causes.get),
            "dominant_phase": max(phases, key=phases.get),
            "mean_recovery_s": round(float(x[idx, 5].mean()), 1),
            "mean_grip_force": round(float(x[idx, 2].mean()), 2),
        })
    return sorted(clusters, key=lambda c: -c["count"])
