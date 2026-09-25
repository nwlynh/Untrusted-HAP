# untrusted-hap-hard-v7 — Triadic Covariance Binding

This is the 9/10 successor to `../untrusted-hap-hard-v6`. It raises the
challenge from one permutation and adaptive bins to 1,536 rounds, three
independent calibration permutations, and a hidden per-cell **three-way**
quota. A solution can no longer optimize calibration streams separately.

Release:

```bash
python3 organizer/generate_instance.py --seed 0x7a17
python3 organizer/regression.py
docker build -t untrusted-hap-hard-v7 challenge
docker run --rm -p 5007:5007 \
  -e FLAG='flag{...}' \
  -e BINDING_PATH=/run/secrets/untrusted_hap_v7_binding.json \
  -v "$PWD/organizer/release_binding.json:/run/secrets/untrusted_hap_v7_binding.json:ro" \
  untrusted-hap-hard-v7
```

Do not publish `organizer/` or `release_binding.json`. The public service has
one rejection response for malformed, quota-invalid, covariance-invalid, and
finite-size-invalid submissions.
