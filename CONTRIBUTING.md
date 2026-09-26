# Contributing

Use Python 3.11 and `uv sync --frozen --extra dev`. Before submitting changes, run:

```bash
uv run ruff format src tests scripts
uv run ruff check src tests scripts
uv run pytest -q
```

Changes to task generation, collision construction, dynamics, tolerances or metrics change the
benchmark protocol. Update the protocol version, refresh frozen suites and calibration evidence,
and describe the impact on score comparability. Never loosen thresholds simply to make a failed
reference pass; diagnose geometry, loads, solver settings and timestep convergence first.

Include a physically meaningful negative control with new mechanism families. Preserve the
separation between candidate execution and evaluation. New provider integrations must not expose
credentials to workers or introduce hidden retries.

Contributions are licensed under the repository's MIT license. Third-party assets or code must
have their provenance and compatible license documented. Do not contribute private benchmark
holdouts or secrets to the public calibration suite.

