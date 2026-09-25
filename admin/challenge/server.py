#!/usr/bin/env python3
"""Non-diagnostic TCP verifier for Triadic Covariance Binding (v7)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socketserver
from typing import Any

from common import N, bound, validate


HERE = Path(__file__).resolve().parent
INSTANCE = json.loads((HERE / "instance.json").read_text())
DEFAULT_BINDING = HERE.parent / "organizer" / "release_binding.json"
BINDING_PATH = Path(os.environ.get("BINDING_PATH", str(DEFAULT_BINDING)))

try:
    BINDING = json.loads(BINDING_PATH.read_text())
    ROUND_BINS = BINDING["round_bins"]
    LINK_CLASSES = BINDING["link_classes"]
except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"missing or invalid private binding: {BINDING_PATH}") from exc

STREAMS = [INSTANCE["links_a"], INSTANCE["links_b"], INSTANCE["links_c"]]
if (
    len(INSTANCE["rounds"]) != N
    or any(len(stream) != N for stream in STREAMS)
    or len(ROUND_BINS) != N
    or len(LINK_CLASSES) != 3
    or any(len(classes) != N for classes in LINK_CLASSES)
):
    raise SystemExit("private binding does not match v7 artifact")

FLAG = os.environ.get("FLAG", "flag{development_only}")
REJECT = {"ok": False, "error": "submission rejected"}


def submission_result(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"pi_a", "pi_b", "pi_c"}:
        return REJECT
    permutations = (payload["pi_a"], payload["pi_b"], payload["pi_c"])
    if any(
        not isinstance(permutation, list)
        or len(permutation) != N
        or any(type(value) is not int for value in permutation)
        for permutation in permutations
    ):
        return REJECT
    if not validate(INSTANCE["rounds"], STREAMS, *permutations, ROUND_BINS, LINK_CLASSES):
        return REJECT
    if bound(INSTANCE["rounds"], STREAMS, *permutations, ROUND_BINS, LINK_CLASSES) <= 0.0:
        return REJECT
    return {"ok": True, "flag": FLAG}


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            result = submission_result(json.loads(self.rfile.readline(4_000_000)))
        except Exception:
            result = REJECT
        self.wfile.write(json.dumps(result, separators=(",", ":")).encode() + b"\n")


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", int(os.environ.get("PORT", "5007"))), Handler) as server:
        server.serve_forever()
