# Organizer notes — v7

Keep this directory and `release_binding.json` private. Distribute only
`challenge/`; the binding is a verifier secret and contains the hidden round
bins plus the three link-class arrays.

The intended path is:

1. Recover each epoch's eight-round bin cells from `pilot`.
2. Cluster each calibration stream into its four phase/fading lanes.
3. Solve an eight-node triadic-slot assignment per `(epoch, bin)`.
4. Run three class-preserving min-cost assignments, trading phase residual
   against fading quality; optional exact-bound swaps polish the result.

`regression.py` checks twenty shuffled serializations. A quota-valid
phase-only baseline remains negative (`-3.398`), while the triadic
fading-aware construction stays above `+4.134`. Identity, reusing one stream
for all three, and artifact label leakage are release blockers.
`recovery_audit.py` confirms the intended pilot/phase clustering path
reconstructs the server binding exactly from the public artifact.
