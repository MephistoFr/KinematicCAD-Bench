# Local validation record

Validated on 2026-09-22 using the actual native CAD and physics libraries.

- Automated tests: **41 passed, 1 skipped** (Docker-only test).
- Public calibration: **5/5 reference designs passed**, two load/direction trials per family, each at dt and dt/2.
- Linear replay: identical full report SHA-256, including all four trajectory hashes.
- Static analysis and formatting: Ruff passed.
- Offline HTML: rendered in headless Chrome and visually inspected; embedded JavaScript passed Node syntax checking.
- Distribution: source archive and wheel built; wheel includes the offline viewer, source includes contracts and schemas.

## Physical results

| Family | Verdict | Worst position RMS | Worst penetration (mm) | Quality |
| --- | --- | --- | --- | --- |
| linear | passed | 0.0194578 mm | 0.0476203 | 0.702185 |
| spur | passed | 0.00205935 rad | 0.0104025 | 0.957091 |
| slider_crank | passed | 0.000312214 mm | 0 | 0.998795 |
| cam | passed | 0.0261848 mm | 0.0490364 | 0.260301 |
| planetary | passed | 0.00275355 rad | 0.0269645 | 0.920167 |

These are calibration designs, not measured LLM performance or a public model leaderboard.

## Reproducibility identifiers

- Suite SHA-256: `2ecd67c9be8aef04e896af9fd02af20250381b79e43741b955cc419142507ab5`
- Implementation SHA-256: `371e7396e0d215c3f4c8298bde84d80fc9ba108e3318ac65658cb2b0f0d99ca7`
- Linear report/replay SHA-256: `6e50e7ede6c49d43d69a5400289ec6f4838a9bbb0229d51aac51ead789e4beb4`
- Runtime: Python 3.11.15, Windows AMD64; AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD.
- Native packages: cadquery 2.6.1, cadquery-ocp 7.8.1.1.post1, mujoco 3.3.6, numpy 2.2.6, pillow 11.3.0, scipy 1.15.3.

## Explicitly unverified

Docker Engine was unavailable on this machine. The two images and their dedicated CI/test workflow are provided,
but container execution and the Linux CI jobs were not run here. No paid or live model API was called; HTTP
protocols, response handling and deadlines were verified with mocked transports. Nonzero procedural seeds
are supported but are not part of this five-task certified calibration record.

## Reproduce

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run kcb benchmark --suite suites/calibration.json --provider configs/replay.json --label reference --unsafe-local --out runs/reference
uv run kcb replay runs/reference/linear-000000 --unsafe-local --out runs/replay
```

The delivered local evidence is under `artifacts/release-calibration/`; large generated artifacts are excluded
from source distributions. The local calibration ranking is `artifacts/leaderboard.json` and is explicitly
marked development-only. See the protocol for the limits of numerical rigid-body evidence.
