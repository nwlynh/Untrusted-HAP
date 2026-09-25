#!/usr/bin/env python3
"""Public-observable recovery audit for the v7 release design.

This file is organizer material, not part of the challenge handout.  It proves
the hidden labels are inferable from intended public signals rather than being
an arbitrary server secret: sort each epoch's pilot lane into 16 cells and
sort each calibration phase lane into its four 32-record clusters.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "challenge"))
import common  # noqa: E402


def recover_binding(public: dict[str, Any]) -> dict[str, list[Any]]:
    rounds = public["rounds"]
    stream_keys = ("links_a", "links_b", "links_c")
    if len(rounds) != common.N or any(len(public[key]) != common.N for key in stream_keys):
        raise ValueError("not a v7 public artifact")
    round_bins = [-1] * common.N
    for epoch in range(common.EPOCHS):
        round_ids = [round_id for round_id, row in enumerate(rounds) if row["epoch"] == epoch]
        if len(round_ids) != common.PER_EPOCH:
            raise ValueError("bad epoch shape")
        round_ids.sort(key=lambda round_id: rounds[round_id]["pilot"])
        for rank, round_id in enumerate(round_ids):
            round_bins[round_id] = rank // common.PER_BIN_EPOCH

    link_classes: list[list[int]] = []
    for key in stream_keys:
        stream = public[key]
        classes = [-1] * common.N
        for epoch in range(common.EPOCHS):
            link_ids = [link_id for link_id, link in enumerate(stream) if link["epoch"] == epoch]
            if len(link_ids) != common.PER_EPOCH:
                raise ValueError("bad epoch shape")
            link_ids.sort(key=lambda link_id: stream[link_id]["phase"])
            for rank, link_id in enumerate(link_ids):
                classes[link_id] = rank // 32
        link_classes.append(classes)
    return {"round_bins": round_bins, "link_classes": link_classes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=Path, default=HERE.parent / "challenge" / "instance.json")
    parser.add_argument("--binding", type=Path, default=HERE / "release_binding.json")
    args = parser.parse_args()
    recovered = recover_binding(json.loads(args.instance.read_text()))
    expected = json.loads(args.binding.read_text())
    if recovered != expected:
        raise SystemExit("recovery audit failed")
    print("PASS: public pilot/phase lanes recover the release binding exactly")


if __name__ == "__main__":
    main()
