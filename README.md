# KinematicCAD-Bench

**Executable mechanical design contracts for AI-generated parametric CAD.**

KinematicCAD-Bench evaluates whether a generated mechanism is a valid solid assembly and actually
transmits motion under load. OpenCascade checks the B-Rep; MuJoCo integrates contact dynamics;
mathematical contracts decide the verdict. There is no language-model judge.

Version 0.1 is a working research baseline with five public calibration families. It does **not**
claim to be an established leaderboard, a contamination-free dataset, or a certification of
manufactured hardware. [Français](README.fr.md) · [Protocol](docs/PROTOCOL.md) ·
[Architecture](docs/ARCHITECTURE.md) · [Extending the benchmark](docs/EXTENDING.md)

The delivered verification record is in [VALIDATION.md](VALIDATION.md), including measured
reference results, test coverage and the checks that could not be run on the development machine.

## Acceptance gates

1. **Topology:** exactly one closed, correctly oriented positive-volume solid per body;
   OpenCascade validity and self-interference checks.
2. **Assembly:** boolean intersection volumes for every pair, plus specified minimum and maximum
   clearances. Connected bodies do not receive an interference exemption.
3. **Dynamics:** evaluator-owned actuators and loads, actual contact-mediated gear/cam transmission,
   measured displacement and velocity errors, travel, useful work, penetration and loop closure.
   Every trial is repeated at half the integration timestep and must converge.
4. **Evidence:** standalone HTML with interactive 3D replay, animated GIFs, a PNG, raw traces,
   compiled physics models, diagnostic JSON and SHA-256 hashes. Failures also produce evidence.

Collision geometry is not trusted: independently reconstructed convex CAD cells must cover the
STEP solid in **both** boolean directions. Mass, centre of mass and inertia come from that solid.
The evaluator never accepts a model-provided actuator, motion trajectory or gear-ratio constraint.

## Run a reference design

Python **3.11**, x86-64, and a recent `uv` are required. The lock contains exact dependencies and
artifact hashes. Linux containers are the ranking environment; native Windows/Linux runs are
development runs.

```bash
uv sync --frozen --extra dev
uv run kcb doctor
uv run kcb demo --family slider_crank --unsafe-local --out runs/crank
```

Open `runs/crank/evaluation/evidence.html`. It works offline and supports rotation, playback,
trial selection and frame scrubbing. No GPU, X server, OpenGL context or browser automation is
required to evaluate or render. `--unsafe-local` executes trusted Python on your machine;
it is deliberately excluded from official ranking.

For untrusted generated designs, build **both** container images:

```bash
docker build --target candidate -t kinematiccad-bench:0.1.0-candidate .
docker build --target judge -t kinematiccad-bench:0.1.0 .
uv run kcb demo --family spur --out runs/spur
uv run kcb replay runs/spur --out runs/spur-replay
```

Published evaluations should build from a pinned `BASE_IMAGE` digest and archive both resulting
image digests. The runner resolves image IDs before executing and never pulls during evaluation.

## Evaluate a model

```bash
uv run kcb suite --seeds 0,1,2 --out suites/calibration.json
uv run kcb benchmark --suite suites/calibration.json --provider configs/local-http.json \
  --label my-model --out runs/my-model
uv run kcb leaderboard --suite suites/calibration.json --batches runs/my-model \
  --out runs/leaderboard.json
```

Adapt the model ID, URL and explicit decoding parameters in the provider file. Supported adapters:

| Adapter | Purpose |
| --- | --- |
| `http`, `chat` | OpenAI-compatible Chat Completions, including compatible local servers |
| `http`, `responses` | Responses API; API keys are read from a named environment variable |
| `command` | Any trusted local inference program: JSON request on stdin, Python source on stdout |
| `replay` | Previously recorded Python answers, with no model or network dependency |

HTTP failures and truncated completions count as failed attempts; there are no silent retries or
model substitutions. The adapter interface supports additional vendors without changing the judge.
Requests and responses are saved. No API keys are copied into evaluation containers.

An individual answer can also be evaluated:

```bash
uv run kcb task --family cam --seed 7 --out task.json
uv run kcb evaluate --task task.json --design answer.py --out runs/answer
```

## Mechanical families

| Family | Measured relation | Transmission |
| --- | --- | --- |
| `linear` | `x(t) = F t² / (2m)` | Six-DOF carriage guided by floor/wall contacts under lateral load |
| `spur` | `theta_out = -N_in / N_out * theta_in` | Tooth contact, forward and reverse under load |
| `slider_crank` | `x = r cos(theta) + sqrt(l² - r² sin²(theta))` | Rigid links and supplied pin bearings |
| `cam` | `y = R + e cos(theta)` | Unilateral contact with a preloaded flat follower |
| `planetary` | `omega_carrier / omega_sun = N_s / (N_s + N_r)` | Sun/planet/fixed-ring tooth contacts |

The task defines the topology and supplied ideal bearings (except the free-body linear guide);
the model designs all named solids.
The initial release concerns planar mechanisms with fully 3D solids and inertia. It does not
evaluate arbitrary mechanism synthesis, flexible material failure or fatigue. The public seeds
are for calibration, not a defensible secret test split. See the protocol for release requirements.

## Determinism and interpretation

The **evaluation** is deterministic for frozen assets, the same image/native libraries, numerical
settings and hardware cohort. Each run records that cohort and the hashes of traces at both
timesteps. `replay` checks exact equality. A remote model's answer is not assumed deterministic;
the saved answer is the replay boundary. Cross-CPU bitwise identity is not promised.

The result is a bounded numerical experiment, with explicit tolerances and a finite horizon.
Passing is not a proof of continuous-time collision freedom or real-world durability.

## Tests and project map

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
# After building both images (POSIX shell):
KCB_TEST_DOCKER=1 uv run pytest tests/test_pipeline.py -m docker -q
```

Tests exercise real OpenCascade and MuJoCo, invalid B-Reps, forged collision proxies, static
interference, insufficient clearance, non-transmitting solids, exact trace replay, API protocols,
subprocess limits, hostile archive paths, missing-attempt scoring and the full pipeline.

```text
src/kinematiccad/
  tasks.py, schema.py       mathematical contracts and bounded interchange formats
  sdk.py, references.py     candidate CAD API and public calibration designs
  geometry.py, physics.py   independent geometric and physical validation
  inference.py              remote, local and replay inference adapters
  sandbox.py, worker.py     separate candidate/judge processes and containers
  evidence.py, viewer.html  software rendering and autonomous replay
  pipeline.py, cli.py       end-to-end execution
  leaderboard.py           manifest-based ranking and confidence intervals
tests/                     physical, protocol and adversarial tests
docs/                      methodology, security boundaries, extension guide
```

The primary ranking is pass@1 across the **entire frozen suite**. Missing attempts score zero.
Quality is a secondary diagnostic; it cannot compensate for a failed physical gate. Different
runtime cohorts or suite hashes are rejected. See [PROTOCOL.md](docs/PROTOCOL.md).

MIT licensed. Dependencies retain their own licenses. Citation metadata is in `CITATION.cff`.

