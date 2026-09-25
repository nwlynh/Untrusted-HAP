#!/usr/bin/env python3
"""Organizer reference attack for v7's coupled three-stream construction.

The solver is intentionally kept out of the player bundle.  It demonstrates
that the release is hard-but-solvable: recover the hidden classes/bins from
the public observables, allocate every epoch/bin to eight triadic slots, then
perform class-preserving exact-bound swaps across all three calibration
streams.  This organiser implementation receives the labels only so regression
can test the verifier independently of a clustering implementation.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import socket
import sys
from pathlib import Path
from typing import Any, Sequence

from scipy.optimize import linear_sum_assignment


HERE = Path(__file__).resolve().parent
CHALLENGE = HERE.parent / "challenge"
sys.path.insert(0, str(CHALLENGE))
import common  # noqa: E402


PHASE_WEIGHT = 420.0
ETA_WEIGHT = 1600.0
LOCAL_SAMPLES = 8


def _streams(instance: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [instance["links_a"], instance["links_b"], instance["links_c"]]


def _binding(instance: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        "round_bins": [row["bin"] for row in instance["rounds"]],
        "link_classes": [[link["cls"] for link in stream] for stream in _streams(instance)],
    }


def phase_estimate(row: dict[str, Any]) -> float:
    """Estimate the net calibration phase from the disclosed quadratures."""
    signal_phase = math.atan2(row["a_p"] - row["b_p"], row["a_x"] - row["b_x"])
    observed_phase = math.atan2(row["z_p"], row["z_x"])
    return (observed_phase - signal_phase + math.pi) % (2.0 * math.pi) - math.pi


def _phase_means(streams: Sequence[Sequence[dict[str, Any]]]) -> list[list[float]]:
    means: list[list[float]] = []
    for stream in streams:
        rows: list[float] = []
        for class_id in range(common.CLASSES):
            values = [link["phase"] for link in stream if link["cls"] == class_id]
            rows.append(sum(values) / len(values))
        means.append(rows)
    return means


def assign_triad_slots(instance: dict[str, Any]) -> list[tuple[int, int, int]]:
    """Min-cost assignment of each cell's eight rounds to public triple slots."""
    rounds, streams = instance["rounds"], _streams(instance)
    phase_means = _phase_means(streams)
    triples: list[tuple[int, int, int] | None] = [None] * common.N
    for epoch in range(common.EPOCHS):
        for bin_id in range(common.BINS):
            round_ids = [
                t
                for t, row in enumerate(rounds)
                if row["epoch"] == epoch and row["bin"] == bin_id
            ]
            slots = common.TRIPLE_TEMPLATES[bin_id]
            if len(round_ids) != len(slots):
                raise ValueError("invalid private bin layout")
            cost = []
            for round_id in round_ids:
                estimate = phase_estimate(rounds[round_id])
                cost.append(
                    [
                        common.circular_distance(
                            estimate,
                            sum(
                                weight * phase_means[stream_id][class_id]
                                for stream_id, (weight, class_id) in enumerate(zip(common.WEIGHTS, slot))
                            ),
                        )
                        ** 2
                        for slot in slots
                    ]
                )
            row_indices, column_indices = linear_sum_assignment(cost)
            for row_index, column_index in zip(row_indices, column_indices):
                triples[round_ids[row_index]] = slots[column_index]
    if any(item is None for item in triples):
        raise AssertionError("slot assignment incomplete")
    return [item for item in triples if item is not None]


def _target_component(
    estimate: float,
    slot: tuple[int, int, int],
    stream_id: int,
    phase_means: Sequence[Sequence[float]],
) -> float:
    others = sum(
        weight * phase_means[other_id][slot[other_id]]
        for other_id, weight in enumerate(common.WEIGHTS)
        if other_id != stream_id
    )
    return (estimate - others) / common.WEIGHTS[stream_id]


def _match_streams(
    instance: dict[str, Any],
    triples: Sequence[tuple[int, int, int]],
    eta_weight: float,
) -> tuple[list[int], list[int], list[int]]:
    rounds, streams = instance["rounds"], _streams(instance)
    phase_means = _phase_means(streams)
    permutations: list[list[int]] = [[-1] * common.N for _ in range(3)]
    for stream_id, stream in enumerate(streams):
        for epoch in range(common.EPOCHS):
            for class_id in range(common.CLASSES):
                round_ids = [
                    t
                    for t, row in enumerate(rounds)
                    if row["epoch"] == epoch and triples[t][stream_id] == class_id
                ]
                link_ids = [
                    link_id
                    for link_id, link in enumerate(stream)
                    if link["epoch"] == epoch and link["cls"] == class_id
                ]
                if len(round_ids) != len(link_ids):
                    raise ValueError("template does not balance class supply")
                cost = []
                for round_id in round_ids:
                    target = _target_component(
                        phase_estimate(rounds[round_id]), triples[round_id], stream_id, phase_means
                    )
                    # High-quality bins benefit more from high eta, but the
                    # exact LCB still decides whether a swap is retained.
                    quality = 1.0 + 0.055 * rounds[round_id]["bin"]
                    cost.append(
                        [
                            PHASE_WEIGHT
                            * common.circular_distance(target, stream[link_id]["phase"]) ** 2
                            - eta_weight * quality * stream[link_id]["eta"]
                            for link_id in link_ids
                        ]
                    )
                row_indices, column_indices = linear_sum_assignment(cost)
                for row_index, column_index in zip(row_indices, column_indices):
                    permutations[stream_id][round_ids[row_index]] = link_ids[column_index]
    if any(value < 0 for permutation in permutations for value in permutation):
        raise AssertionError("link assignment incomplete")
    return tuple(permutations)  # type: ignore[return-value]


def score(instance: dict[str, Any], permutations: tuple[list[int], list[int], list[int]]) -> float:
    rounds, streams = instance["rounds"], _streams(instance)
    binding = _binding(instance)
    if not common.validate(rounds, streams, *permutations, **binding):
        return float("-inf")
    return common.bound(rounds, streams, *permutations, **binding)


def _refine(
    instance: dict[str, Any],
    triples: Sequence[tuple[int, int, int]],
    permutations: tuple[list[int], list[int], list[int]],
    passes: int,
    seed: int,
) -> tuple[list[int], list[int], list[int]]:
    """Exact-bound swaps that preserve every triple quota by construction."""
    rounds, streams = instance["rounds"], _streams(instance)
    binding = _binding(instance)
    mutable = [list(permutation) for permutation in permutations]
    best = score(instance, tuple(mutable))
    rng = random.Random(seed)
    for _ in range(passes):
        improved = False
        for stream_id in range(3):
            for epoch in range(common.EPOCHS):
                for class_id in range(common.CLASSES):
                    round_ids = [
                        t
                        for t, row in enumerate(rounds)
                        if row["epoch"] == epoch and triples[t][stream_id] == class_id
                    ]
                    pairs = [
                        (round_ids[left], round_ids[right])
                        for left in range(len(round_ids))
                        for right in range(left + 1, len(round_ids))
                    ]
                    rng.shuffle(pairs)
                    for left, right in pairs[:LOCAL_SAMPLES]:
                        mutable[stream_id][left], mutable[stream_id][right] = (
                            mutable[stream_id][right],
                            mutable[stream_id][left],
                        )
                        # Swapping within an epoch and an assigned class keeps
                        # all three quota templates valid, so avoid repeatedly
                        # paying the verifier's structural-validation cost.
                        candidate = common.bound(rounds, streams, *mutable, **binding)
                        if candidate > best + 1e-9:
                            best = candidate
                            improved = True
                        else:
                            mutable[stream_id][left], mutable[stream_id][right] = (
                                mutable[stream_id][right],
                                mutable[stream_id][left],
                            )
        if not improved:
            break
    return tuple(mutable)  # type: ignore[return-value]


def quota_phase_baseline(instance: dict[str, Any]) -> tuple[list[int], list[int], list[int]]:
    """A valid structural baseline which omits fading-aware optimisation."""
    triples = assign_triad_slots(instance)
    return _match_streams(instance, triples, eta_weight=0.0)


def build_submission(
    instance: dict[str, Any],
    eta_weight: float = ETA_WEIGHT,
    passes: int = 0,
) -> tuple[list[int], list[int], list[int]]:
    triples = assign_triad_slots(instance)
    initial = _match_streams(instance, triples, eta_weight=eta_weight)
    return _refine(instance, triples, initial, passes=passes, seed=0x7A17)


def attach_binding(instance: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    """Reattach an inferred or organizer-private binding to an artifact."""
    labels = binding["link_classes"]
    if len(binding["round_bins"]) != common.N or len(labels) != 3 or any(len(row) != common.N for row in labels):
        raise ValueError("binding does not match v7 shape")
    for round_id, bin_id in enumerate(binding["round_bins"]):
        instance["rounds"][round_id]["bin"] = bin_id
    for stream, stream_labels in zip(_streams(instance), labels):
        for link_id, class_id in enumerate(stream_labels):
            stream[link_id]["cls"] = class_id
    return instance


def load_private_instance(instance_path: Path, binding_path: Path) -> dict[str, Any]:
    """Load a public artifact locally and reattach organizer-only labels."""
    return attach_binding(json.loads(instance_path.read_text()), json.loads(binding_path.read_text()))


def submit(host: str, port: int, permutations: tuple[list[int], list[int], list[int]]) -> dict[str, Any]:
    payload = {"pi_a": permutations[0], "pi_b": permutations[1], "pi_c": permutations[2]}
    with socket.create_connection((host, port), timeout=20) as connection:
        connection.sendall(json.dumps(payload).encode() + b"\n")
        return json.loads(connection.recv(262144))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=Path, default=CHALLENGE / "instance.json")
    parser.add_argument("--binding", type=Path, default=HERE / "release_binding.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5007)
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--no-submit", action="store_true")
    args = parser.parse_args()
    instance = load_private_instance(args.instance, args.binding)
    baseline = quota_phase_baseline(instance)
    print(f"quota-aware phase baseline: {score(instance, baseline):+.3f}")
    answer = build_submission(instance, passes=args.passes)
    final = score(instance, answer)
    print(f"triadic exact refinement: {final:+.3f}")
    if final <= 0:
        raise SystemExit("solver did not reach a positive finite-size bound")
    if not args.no_submit:
        print(submit(args.host, args.port, answer))


if __name__ == "__main__":
    main()
