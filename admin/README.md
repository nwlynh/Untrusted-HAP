# untrusted-hap-hard-v7 — Triadic Covariance Binding

This is the complete 9/10 release bundle: 1,536 rounds, three independent
calibration permutations, and a hidden per-cell **three-way** quota. A
solution cannot optimize the calibration streams separately.

Release:

```bash
python3 organizer/generate_instance.py --seed 0x7a17
python3 organizer/regression.py
docker build -f deploy/Dockerfile -t untrusted-hap-hard-v7 .
docker run --rm -p 5007:5007 \
  -e FLAG='flag{...}' \
  -e BINDING_PATH=/run/secrets/untrusted_hap_v7_binding.json \
  -v "$PWD/organizer/release_binding.json:/run/secrets/untrusted_hap_v7_binding.json:ro" \
  untrusted-hap-hard-v7
```

Do not publish `organizer/` or `release_binding.json`. The public service has
one rejection response for malformed, quota-invalid, covariance-invalid, and
finite-size-invalid submissions.
