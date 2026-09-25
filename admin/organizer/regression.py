#!/usr/bin/env python3
"""Release gate for v7: triadic solve, shortcuts, and artifact hygiene."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "challenge"))
sys.path.insert(0, str(HERE))
import common  # noqa: E402
from generate_instance import make_instance, private_binding, public_instance  # noqa: E402
from recovery_audit import recover_binding  # noqa: E402
from solve import attach_binding, build_submission, quota_phase_baseline, score  # noqa: E402


# These seeds exercise twenty independently shuffled serializations of the
# same stratified physical stress pattern.  Each must meet the same margin.
REGRESSION_SEEDS = tuple(range(0x7A17, 0x7A17 + 20))


def _streams(instance: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [instance["links_a"], instance["links_b"], instance["links_c"]]


def check(seed: int) -> tuple[int, float, float, bool, bool, bool, bool, bool]:
    instance, nominal = make_instance(seed)
    rounds, streams = instance["rounds"], _streams(instance)
    binding = private_binding(instance)
    nominal_ok = common.validate(rounds, streams, *nominal, **binding)
    identity = ([*range(common.N)], [*range(common.N)], [*range(common.N)])
    identity_rejected = not common.validate(rounds, streams, *identity, **binding)
    public = public_instance(instance)
    no_public_labels = (
        all("bin" not in row and "_truth" not in row for row in public["rounds"])
        and all("cls" not in link for stream in _streams(public) for link in stream)
        and "round_bins" not in public
        and "link_classes" not in public
    )
    recovered = recover_binding(public)
    recovery_exact = recovered == binding
    recovered_instance = attach_binding(public, recovered)
    phase_only = quota_phase_baseline(recovered_instance)
    baseline = score(recovered_instance, phase_only)
    intended = build_submission(recovered_instance)
    coupled = score(recovered_instance, intended)
    reused_rejected = not common.validate(rounds, streams, intended[0], intended[0], intended[0], **binding)
    return (
        seed,
        baseline,
        coupled,
        nominal_ok,
        identity_rejected,
        reused_rejected,
        no_public_labels,
        recovery_exact,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=lambda value: int(value, 0))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    seeds = tuple(args.seeds) if args.seeds else REGRESSION_SEEDS
    if not seeds:
        raise SystemExit("empty regression shard")
    workers = max(1, min(args.workers, len(seeds)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(check, seeds))
    for seed, baseline, coupled, nominal, identity, reused, hygiene, recovery in rows:
        print(
            f"{seed:#x} phase-only={baseline:+.3f} triadic={coupled:+.3f} "
            f"nominal={nominal} identity={identity} reused={reused} artifact={hygiene} recovery={recovery}"
        )
    if not all(
        baseline < 0.0
        and coupled > 3.0
        and nominal
        and identity
        and reused
        and hygiene
        and recovery
        for _, baseline, coupled, nominal, identity, reused, hygiene, recovery in rows
    ):
        raise SystemExit("FAIL release gate")
    print(
        f"PASS {len(rows)} seeds; phase-only best={max(row[1] for row in rows):+.3f}; "
        f"triadic worst={min(row[2] for row in rows):+.3f}"
    )


if __name__ == "__main__":
    main()
