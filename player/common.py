"""Exact verifier for *Triadic Covariance Binding* (v7).

This is deliberately toy CV-MDI post-processing code for a CTF; it is not a
security proof and must not be used in a QKD system.  The intended flaw is an
authenticated-per-epoch multiset commitment: three calibration streams can be
independently permuted within an epoch instead of being bound to Bell rounds.

The server keeps the round-bin and calibration-class labels private.  Public
code exposes the quota *shape* but not the labels needed to satisfy it.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Iterable, Sequence


N = 1536
EPOCHS = 12
BINS = 16
CLASSES = 4
PER_EPOCH = 128
PER_BIN_EPOCH = 8

# The three estimates are genuinely coupled in the correction; a correct
# phase match in only one stream is not enough to cross the finite-size bound.
WEIGHTS = (0.50, 0.30, 0.20)
KAPPA = 1.18
N0 = 1.85
BETA = 0.93
V_SIGNAL = 10.0
HOLEVO_C = 5.0
# Calibrated by organizer/regression.py: phase-only quota matching stays below
# zero, while the fading-aware three-stream construction has a >4-unit margin.
PENALTY = 340.0
TAU_FLOOR = 0.025
RHO_MIN = 0.62


def rotate(x: float, p: float, phi: float) -> tuple[float, float]:
    return (
        math.cos(phi) * x - math.sin(phi) * p,
        math.sin(phi) * x + math.cos(phi) * p,
    )


def circular_distance(left: float, right: float) -> float:
    delta = abs(left - right) % (2.0 * math.pi)
    return min(delta, 2.0 * math.pi - delta)


def triple_slots(bin_id: int) -> tuple[tuple[int, int, int], ...]:
    """The public, eight-slot triadic quota template for one bin.

    Every template has two appearances of every class in each stream, but the
    *joint* triples change with the bin.  This keeps each stream's marginal
    flow balanced while making independently chosen permutations insufficient.
    """
    if not 0 <= bin_id < BINS:
        raise ValueError("bad bin")
    row, col = divmod(bin_id, 4)
    a_shift = col
    b_shift = (row + 2 * col) % CLASSES
    c_shift = (3 * row + col) % CLASSES
    b_sign = -1 if row & 1 else 1
    c_sign = -1 if col & 1 else 1
    return tuple(
        (
            (u + a_shift) % CLASSES,
            (b_sign * u + b_shift + 2 * v) % CLASSES,
            (c_sign * u + c_shift + v) % CLASSES,
        )
        for v in range(2)
        for u in range(CLASSES)
    )


TRIPLE_TEMPLATES = tuple(triple_slots(bin_id) for bin_id in range(BINS))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _var(values: Sequence[float]) -> float:
    average = _mean(values)
    return sum((value - average) ** 2 for value in values) / len(values)


def _cov(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean, right_mean = _mean(left), _mean(right)
    return sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right)) / len(left)


def _private_metadata(
    rounds: Sequence[dict],
    streams: Sequence[Sequence[dict]],
    round_bins: Sequence[int] | None,
    link_classes: Sequence[Sequence[int]] | None,
) -> tuple[list[int] | None, list[list[int]] | None]:
    """Obtain organizer-only labels without placing them in the artifact."""
    if round_bins is None:
        try:
            round_bins = [row["bin"] for row in rounds]
        except KeyError:
            return None, None
    if link_classes is None:
        try:
            link_classes = [[link["cls"] for link in stream] for stream in streams]
        except KeyError:
            return None, None
    if (
        len(round_bins) != N
        or len(link_classes) != 3
        or any(len(classes) != N for classes in link_classes)
    ):
        return None, None
    if any(not isinstance(bin_id, int) or not 0 <= bin_id < BINS for bin_id in round_bins):
        return None, None
    if any(
        not isinstance(class_id, int) or not 0 <= class_id < CLASSES
        for classes in link_classes
        for class_id in classes
    ):
        return None, None
    return list(round_bins), [list(classes) for classes in link_classes]


def _well_formed_permutation(values: object) -> bool:
    return (
        isinstance(values, list)
        and len(values) == N
        and all(type(value) is int for value in values)
        and sorted(values) == list(range(N))
    )


def validate(
    rounds: Sequence[dict],
    streams: Sequence[Sequence[dict]],
    pi_a: object,
    pi_b: object,
    pi_c: object,
    round_bins: Sequence[int] | None = None,
    link_classes: Sequence[Sequence[int]] | None = None,
) -> bool:
    """Check all structural, epoch, and coupled three-stream quota rules."""
    if len(rounds) != N or len(streams) != 3 or any(len(stream) != N for stream in streams):
        return False
    if not all(_well_formed_permutation(permutation) for permutation in (pi_a, pi_b, pi_c)):
        return False
    assert isinstance(pi_a, list) and isinstance(pi_b, list) and isinstance(pi_c, list)
    bins, classes = _private_metadata(rounds, streams, round_bins, link_classes)
    if bins is None or classes is None:
        return False
    permutations = (pi_a, pi_b, pi_c)
    try:
        for round_id, row in enumerate(rounds):
            if not isinstance(row.get("epoch"), int):
                return False
            for stream, permutation in zip(streams, permutations):
                if stream[permutation[round_id]].get("epoch") != row["epoch"]:
                    return False
    except (IndexError, KeyError, TypeError):
        return False

    for epoch in range(EPOCHS):
        for bin_id in range(BINS):
            round_ids = [
                round_id
                for round_id, row in enumerate(rounds)
                if row["epoch"] == epoch and bins[round_id] == bin_id
            ]
            if len(round_ids) != PER_BIN_EPOCH:
                return False
            observed = Counter(
                (
                    classes[0][pi_a[round_id]],
                    classes[1][pi_b[round_id]],
                    classes[2][pi_c[round_id]],
                )
                for round_id in round_ids
            )
            if observed != Counter(TRIPLE_TEMPLATES[bin_id]):
                return False
    return True


def bound(
    rounds: Sequence[dict],
    streams: Sequence[Sequence[dict]],
    pi_a: Sequence[int],
    pi_b: Sequence[int],
    pi_c: Sequence[int],
    round_bins: Sequence[int] | None = None,
    link_classes: Sequence[Sequence[int]] | None = None,
) -> float:
    """Return the exact finite-size toy rate for a structurally valid input."""
    bins, _ = _private_metadata(rounds, streams, round_bins, link_classes)
    if bins is None:
        return float("-inf")
    permutations = (pi_a, pi_b, pi_c)
    total = 0.0
    try:
        for bin_id in range(BINS):
            round_ids = [round_id for round_id, value in enumerate(bins) if value == bin_id]
            if len(round_ids) != EPOCHS * PER_BIN_EPOCH:
                return float("-inf")
            sx = [rounds[t]["a_x"] - rounds[t]["b_x"] for t in round_ids]
            sp = [rounds[t]["a_p"] - rounds[t]["b_p"] for t in round_ids]
            corrected = []
            products = []
            for t in round_ids:
                phase = sum(
                    weight * stream[permutation[t]]["phase"]
                    for weight, stream, permutation in zip(WEIGHTS, streams, permutations)
                )
                corrected.append(rotate(rounds[t]["z_x"], rounds[t]["z_p"], -phase))
                products.append(math.prod(stream[permutation[t]]["eta"] for stream, permutation in zip(streams, permutations)))
            zx, zp = [value[0] for value in corrected], [value[1] for value in corrected]
            vsx, vsp, vzx, vzp = _var(sx), _var(sp), _var(zx), _var(zp)
            if min(vsx, vsp, vzx, vzp) <= 1e-9:
                return float("-inf")
            cxx, cpp = _cov(sx, zx), _cov(sp, zp)
            rho = (abs(cxx) / math.sqrt(vsx * vzx) + abs(cpp) / math.sqrt(vsp * vzp)) / 2.0
            if rho < RHO_MIN:
                return float("-inf")
            gain_x, gain_p = cxx / vsx, cpp / vsp
            residual = [
                ((zx[index] - gain_x * sx[index]) ** 2 + (zp[index] - gain_p * sp[index]) ** 2) / 2.0
                for index in range(len(round_ids))
            ]
            n = len(round_ids)
            tau_lcb = max(TAU_FLOOR, _mean(products) - KAPPA * math.sqrt(_var(products) / n))
            excess = max(0.0, _mean(residual) - N0)
            excess_lcb = excess + KAPPA * math.sqrt(_var(residual) / n)
            information = 0.50 * math.log2(
                1.0 + V_SIGNAL * rho * rho * tau_lcb / (1.0 + excess_lcb)
            )
            holevo = 0.095 * math.log2(1.0 + HOLEVO_C * ((1.0 - tau_lcb) + excess_lcb))
            total += n * (BETA * information - holevo)
    except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return float("-inf")
    return total - PENALTY
