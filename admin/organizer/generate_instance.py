#!/usr/bin/env python3
"""Generate gated v7 instances without leaking the private binding.

Only ``challenge/`` is a player artifact.  ``release_binding.json`` belongs
on the verifier (for example, mounted at ``/run/secrets``) and contains no
generator seed or winning permutations.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CHALLENGE = HERE.parent / "challenge"
sys.path.insert(0, str(CHALLENGE))
import common  # noqa: E402


# Each stream has a distinct phase lane and fading profile.  The lane spacing
# is enough for clustering, but the weighted three-lane sum has deliberately
# overlapping combinations.
BASE_PHASES = (
    (-0.56, -0.18, 0.18, 0.56),
    (-0.47, -0.08, 0.31, 0.70),
    (-0.63, -0.26, 0.09, 0.46),
)
ETA_BASES = (
    (0.42, 0.56, 0.70, 0.84),
    (0.46, 0.60, 0.74, 0.88),
    (0.40, 0.54, 0.68, 0.82),
)
PHASE_JITTER = (0.024, 0.028, 0.026)
ETA_JITTER = 0.145
GAMMA_BASE = 0.49
SIGNAL_VAR = 10.0
AB_NOISE = math.sqrt(1.75)
MEASUREMENT_NOISE = math.sqrt(0.92)


def _streams(instance: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [instance["links_a"], instance["links_b"], instance["links_c"]]


def make_instance(seed: int = 0x7A17) -> tuple[dict[str, Any], tuple[list[int], list[int], list[int]]]:
    """Create a private instance and a temporary nominal permutation tuple.

    The tuple is used only for organizer diagnostics; it is neither serialized
    nor included in the server binding.
    """
    # The release seed changes only the independently serialized order.  The
    # physical stress pattern is stratified so a generator-gated corpus tests
    # the verifier/solver rather than accepting a lucky statistical draw.
    rng = random.Random(seed)
    shape_rng = random.Random(0x7A17_CAFE)
    rounds: list[dict[str, Any]] = []
    streams: list[list[dict[str, Any]]] = [[], [], []]
    true_old: list[list[int]] = [[0] * common.N for _ in range(3)]

    for epoch in range(common.EPOCHS):
        # Epoch drift makes a global phase sort fail while preserving enough
        # local structure for a per-epoch clustering attack.
        drifts = [shape_rng.gauss(0.0, 0.038) for _ in range(3)]
        epoch_slots: list[dict[str, Any]] = []
        for bin_id in range(common.BINS):
            slots = list(common.TRIPLE_TEMPLATES[bin_id])
            shape_rng.shuffle(slots)
            epoch_slots.extend({"bin": bin_id, "classes": slot} for slot in slots)

        # Generate all calibration estimates first.  Within each class, the
        # actual (private) binding allocates the best fading estimates to the
        # most informative bins.  This is the finite-size gain a phase-only
        # solver leaves on the table.
        for stream_id in range(3):
            for class_id in range(common.CLASSES):
                for local_id in range(32):
                    old_id = len(streams[stream_id])
                    phase = BASE_PHASES[stream_id][class_id] + drifts[stream_id] + shape_rng.gauss(
                        0.0, PHASE_JITTER[stream_id]
                    )
                    eta = min(
                        0.95,
                        max(
                            0.18,
                            ETA_BASES[stream_id][class_id]
                            + shape_rng.gauss(0.0, ETA_JITTER)
                            + 0.025 * math.sin(0.37 * old_id + 0.19 * epoch + stream_id),
                        ),
                    )
                    streams[stream_id].append(
                        {
                            "link_id": old_id,
                            "epoch": epoch,
                            "cls": class_id,
                            "phase": round(phase, 8),
                            "eta": round(eta, 8),
                        }
                    )

        for stream_id in range(3):
            for class_id in range(common.CLASSES):
                slot_ids = [
                    slot_id
                    for slot_id, item in enumerate(epoch_slots)
                    if item["classes"][stream_id] == class_id
                ]
                link_ids = [
                    link_id
                    for link_id, link in enumerate(streams[stream_id])
                    if link["epoch"] == epoch and link["cls"] == class_id
                ]
                # Pair low eta with low-information bins and high eta with
                # high-information bins.  Random tie breaking prevents the
                # serialized order from exposing this construction.
                shape_rng.shuffle(slot_ids)
                slot_ids.sort(key=lambda slot_id: epoch_slots[slot_id]["bin"])
                shape_rng.shuffle(link_ids)
                link_ids.sort(key=lambda link_id: streams[stream_id][link_id]["eta"])
                for slot_id, link_id in zip(slot_ids, link_ids):
                    epoch_slots[slot_id].setdefault("old_links", [None, None, None])[stream_id] = link_id

        epoch_rows: list[dict[str, Any]] = []
        for slot_number, item in enumerate(epoch_slots):
            bin_id = item["bin"]
            old_links = item["old_links"]
            if any(link_id is None for link_id in old_links):
                raise AssertionError("incomplete nominal binding")
            phases = [streams[stream_id][old_links[stream_id]]["phase"] for stream_id in range(3)]
            true_phase = sum(weight * phase for weight, phase in zip(common.WEIGHTS, phases))
            global_slot = epoch * common.PER_EPOCH + slot_number
            # Higher numbered bins have a public quality trend.  It helps
            # recover the hidden partition but not the triadic slot binding.
            gamma = GAMMA_BASE + 0.027 * bin_id + shape_rng.gauss(0.0, 0.006)
            sx = shape_rng.gauss(0.0, math.sqrt(SIGNAL_VAR))
            sp = shape_rng.gauss(0.0, math.sqrt(SIGNAL_VAR))
            zx0 = gamma * sx + shape_rng.gauss(0.0, MEASUREMENT_NOISE)
            zp0 = gamma * sp + shape_rng.gauss(0.0, MEASUREMENT_NOISE)
            zx, zp = common.rotate(zx0, zp0, true_phase)
            ax = sx / 2.0 + shape_rng.gauss(0.0, AB_NOISE)
            ap = sp / 2.0 + shape_rng.gauss(0.0, AB_NOISE)
            bx = -sx / 2.0 + shape_rng.gauss(0.0, AB_NOISE)
            bp = -sp / 2.0 + shape_rng.gauss(0.0, AB_NOISE)
            epoch_rows.append(
                {
                    "round_id": -1,
                    "epoch": epoch,
                    "bin": bin_id,
                    # This pilot is intentionally noisy but ordered.  A
                    # player must recover all 8 positions per epoch rather
                    # than receiving a trusted bin label.
                    "pilot": round(bin_id + shape_rng.gauss(0.0, 0.085), 8),
                    "a_x": round(ax, 8),
                    "a_p": round(ap, 8),
                    "b_x": round(bx, 8),
                    "b_p": round(bp, 8),
                    "z_x": round(zx, 8),
                    "z_p": round(zp, 8),
                    "_truth": old_links,
                    "_debug_slot": global_slot,
                }
            )

        rng.shuffle(epoch_rows)
        for row in epoch_rows:
            round_id = len(rounds)
            row["round_id"] = round_id
            for stream_id, old_link in enumerate(row["_truth"]):
                true_old[stream_id][round_id] = old_link
            rounds.append(row)

    # Serialized calibration order is independently shuffled per stream and
    # epoch.  The public link_id always agrees with its array position.
    remaps: list[dict[int, int]] = [{}, {}, {}]
    public_streams: list[list[dict[str, Any]]] = [[], [], []]
    for stream_id, stream in enumerate(streams):
        for epoch in range(common.EPOCHS):
            chunk = list(stream[epoch * common.PER_EPOCH : (epoch + 1) * common.PER_EPOCH])
            rng.shuffle(chunk)
            for link in chunk:
                old_id = link["link_id"]
                new_id = len(public_streams[stream_id])
                remaps[stream_id][old_id] = new_id
                public_streams[stream_id].append(dict(link, link_id=new_id))

    true = tuple(
        [remaps[stream_id][old_link] for old_link in true_old[stream_id]]
        for stream_id in range(3)
    )
    instance: dict[str, Any] = {
        "rounds": rounds,
        "links_a": public_streams[0],
        "links_b": public_streams[1],
        "links_c": public_streams[2],
        "note": "three calibration commitments are authenticated as epoch-local multisets",
    }
    return instance, true


def public_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """Remove every server-only label and all construction breadcrumbs."""
    return {
        "rounds": [
            {key: value for key, value in row.items() if key not in {"bin", "_truth", "_debug_slot"}}
            for row in instance["rounds"]
        ],
        "links_a": [{key: value for key, value in link.items() if key != "cls"} for link in instance["links_a"]],
        "links_b": [{key: value for key, value in link.items() if key != "cls"} for link in instance["links_b"]],
        "links_c": [{key: value for key, value in link.items() if key != "cls"} for link in instance["links_c"]],
        "note": instance["note"],
    }


def private_binding(instance: dict[str, Any]) -> dict[str, Any]:
    """The minimal server binding; deliberately excludes seed and solutions."""
    return {
        "round_bins": [row["bin"] for row in instance["rounds"]],
        "link_classes": [[link["cls"] for link in stream] for stream in _streams(instance)],
    }


def _score(instance: dict[str, Any], permutations: tuple[list[int], list[int], list[int]]) -> tuple[float, bool]:
    rounds, streams = instance["rounds"], _streams(instance)
    binding = private_binding(instance)
    ok = common.validate(rounds, streams, *permutations, **binding)
    return (common.bound(rounds, streams, *permutations, **binding) if ok else float("-inf"), ok)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0x7A17)
    parser.add_argument("--out", type=Path, default=CHALLENGE / "instance.json")
    parser.add_argument("--binding-out", type=Path, default=HERE / "release_binding.json")
    args = parser.parse_args()

    sys.path.insert(0, str(HERE))
    import solve  # noqa: E402

    instance, nominal = make_instance(args.seed)
    nominal_rate, nominal_ok = _score(instance, nominal)
    baseline = solve.quota_phase_baseline(instance)
    baseline_rate, baseline_ok = _score(instance, baseline)
    intended = solve.build_submission(instance)
    intended_rate, intended_ok = _score(instance, intended)
    if not nominal_ok:
        raise SystemExit("gate failed: nominal construction violates a quota")
    if baseline_ok and baseline_rate >= 0.0:
        raise SystemExit(f"gate failed: phase-only shortcut={baseline_rate:+.3f}")
    if not intended_ok or intended_rate <= 3.0:
        raise SystemExit(f"gate failed: intended={intended_rate:+.3f}, ok={intended_ok}")

    args.out.write_text(json.dumps(public_instance(instance), separators=(",", ":")))
    args.binding_out.write_text(json.dumps(private_binding(instance), separators=(",", ":")))
    print(
        f"seed={args.seed:#x} nominal={nominal_rate:+.3f}; "
        f"phase-only={baseline_rate:+.3f}; intended={intended_rate:+.3f}"
    )


if __name__ == "__main__":
    main()
