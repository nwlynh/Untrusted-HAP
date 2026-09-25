# Triadic Covariance Binding

**Category:** Crypto / constrained statistical post-processing
**Difficulty:** 9/10

**Flag format:** `BKSEC{...}`

The HAP authenticated three calibration streams, but it committed each stream
only as a multiset inside an epoch. The individual calibration records are not
bound to the Bell round they were meant to calibrate.

Submit one JSON object to TCP port `5007`:

```json
{"pi_a": [0, 1, "..."], "pi_b": [0, 1, "..."], "pi_c": [0, 1, "..."]}
```

Each array must be an epoch-preserving permutation of `0..1535`. The verifier
has a private eight-round bin assignment and private four-class calibration
labels. It checks a public, bin-specific **joint three-stream quota** before
evaluating a finite-size covariance bound.

The `pilot` field is a deliberately noisy public indication of the hidden bin
order. Calibration phase and transmissivity fields are public. No label, rate,
per-bin score, or failure subtype is disclosed by the service.

This is toy CTF code, not a QKD implementation or security proof.
