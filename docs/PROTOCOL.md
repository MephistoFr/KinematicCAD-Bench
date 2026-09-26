# Evaluation protocol, version 0.1

## Scope and scientific claim

KCB measures whether a model can create parametric solids that satisfy a **specified mechanical
architecture** and transmit motion in a deterministic rigid-body experiment. It combines:

- exact boundary-representation predicates within declared numerical tolerances;
- all-pairs static boolean interference checks and specified surface clearances;
- simulated force-driven or torque-limited dynamics, compared to analytical laws;
- replayable visual and numerical evidence.

The first release contains planar mechanical layouts represented as 3D solids. Models design
parts and their convex decomposition. They do not choose the mechanism topology, ideal bearing
locations, material model or measurement law. A free-body linear guide task separately tests
whether CAD contacts actually provide guidance. This scope must appear with reported scores.

“Deterministic” refers to evaluation of **frozen assets within one runtime/hardware cohort**.
Remote generation is outside that claim. MuJoCo describes deterministic state evolution when
the state, model and inputs are identical. KCB initializes fresh states, uses fixed-step loops,
disables noise and compares actual replay hashes.
[MuJoCo simulation documentation](https://mujoco.readthedocs.io/en/3.4.0/programming/simulation.html)

## Frozen experiment

Before inference, publish or privately commit the suite JSON and its SHA-256 hash. Fix:

1. Task IDs, full task contracts and protocol/code revision.
2. Candidate and judge image digests, architecture, Python/native library versions and CPU cohort.
3. Provider/model identifier, prompt, decoding parameters, token limit and timeout.
4. One generation attempt per task for pass@1. Retry policies require a separate protocol.

Keep requests, raw responses, generated source, STEP files, convex cells, task JSON, compiled
physics XML, trajectories, results and evidence. The API response identity and usage are recorded
when available. Authentication credentials are never research artifacts.

The current suite generator has a deliberately small calibration parameter space. Different seeds
may produce the same geometry. Changing only a seed or task ID is not evidence of novelty.

## Geometric acceptance

Every part must contain exactly one closed solid. `BRepCheck_Analyzer` runs with geometric checks;
shell closure, signed volume and the OpenCascade self-interference analyzer are checked separately.
Declared envelope and volume bounds constrain unrelated or degenerate designs. Bearing and
closure attachment locations must be within 1 mm of actual material.

For a submitted solid S and reconstructed convex-cell union C, require separately:

`volume(S \ C) <= eps` and `volume(C \ S) <= eps`,

where `eps = max(1e-5 mm³, 1e-7 * volume(S))`. A signed difference would allow missing and extra
material to cancel, so it is not used. Polyhedral CAD cells are the supported exact construction
path. Arbitrary curved CAD is accepted only if its decomposition meets the same tight bound;
there is no unchecked approximate decomposition fallback.

Every distinct pair of parts is intersected at the declared rest pose. More than `1e-5 mm³` of
overlap rejects the assembly, including linked or parent/child parts. Prescribed surface-to-surface
clearances have both lower and upper bounds. Contact is permitted when its contract permits zero
gap; material overlap remains disallowed. The tolerance is part of the claim, not mathematical
zero in infinite precision.

## Equations and coordinates

All angles are unwrapped joint positions in radians. All dynamic translations are in metres.
Outputs are displacements from the initial pose unless stated otherwise.

| Family | Analytical output |
| --- | --- |
| External gears | `q_o = -(N_i/N_o) q_i` |
| Fixed-ring planetary | `q_c = N_s/(N_s+N_r) q_s`, with `N_r=N_s+2N_p` |
| Slider-crank | `x = r cos(q_i) + sqrt(l²-r² sin²(q_i)) - (r+l)` |
| Eccentric cam, flat follower | `y = e(cos(q_i)-1) - g_initial` |
| Linear calibration | `x(t)=F t²/(2m)` using the B-Rep-derived mass |

The independent variable for kinematic laws is the **measured** input position, not commanded
speed. This avoids treating motor acceleration as a transmission error. A separate minimum
input-travel requirement prevents a stationary mechanism from passing trivially. Gear trials
require enough travel for a complete output revolution. Slider-crank and cam trials exceed one
input revolution. Linear trials move in both directions while applying a lateral load and gravity.

The velocity actuator has finite gain and torque limit. Its target follows a smooth 0.2 s ramp.
Cam preload ramps over 0.05 s to avoid an artificial initial impact. No body pose is assigned
after initialization. At every integration step, the judge checks finite state, excessive motion,
solver warnings, contact penetration, pin closure and, for the free guide, transverse displacement
and orientation. Parent/child contact filtering is disabled.

## Numerical acceptance and score

Every task freezes its thresholds. Typical defaults are:

| Diagnostic | Threshold |
| --- | --- |
| Static intersection | `1e-5 mm³` |
| Dynamic penetration | `0.08 mm` at every step, including startup |
| Pin closure | `0.12 mm` |
| Gear transmission ratio | `0.5%` relative fitted slope error |
| Free guide transverse motion | `0.5 mm` maximum |
| Free guide rotation | `0.03 rad` maximum |
| Refined trajectory difference | RMS no greater than half the position tolerance |

Post-warmup position RMS and maximum absolute error are measured against the analytical target,
without fitting away phase, amplitude or ratio error. Maximum position error must be at most
three times the RMS tolerance. Velocity error uses non-overlapping approximately 30 ms secants
of the recorded positions to avoid making individual contact impulses the entire score.
Gear ratios also receive an independent least-squares slope check.

Gear outputs must perform positive useful work against an opposing load. Motor and load work are
reported as signed time integrals; they are not presented as a general efficiency certificate.
A cam preload is conservative over a full cycle and can return energy, so negative signed load
work there is not automatically a failure.

Each trial runs from rest at `dt` and `dt/2`. **Both** must satisfy every gate. The fine output is
interpolated onto the coarse time grid for a convergence RMS check. Failing convergence fails
the task; the evaluator never silently chooses the more favorable resolution.

Pass@1 is binary. If any gate fails, the secondary quality score is zero. For passing trials,

`quality = max(0,1 - position_RMS / position_tol) * max(0,1 - velocity_rel_RMS / velocity_tol)`.

Task quality is the minimum over both resolutions and all trials. It is a tie-breaker and a
diagnostic, not a replacement for the hard pass rate. It is sensitive to solver discretization,
so scores must not be compared across different cohorts.

## Ranking

The frozen suite defines the denominator. Missing outputs, inference errors, parser failures and
timeouts count as zero. One batch represents one labeled model/configuration and one attempt
per task. Duplicate model labels and mixed suite/runtime hashes are rejected. The leaderboard
sorts by full-suite pass@1, then mean physical quality, then label for deterministic ties.

Wilson 95% intervals are provided descriptively. Calibration tasks from a small family are not
independent samples of all mechanical intelligence; the intervals do not capture task-selection
uncertainty. Publications should also provide per-family results and cluster-aware uncertainty
for a larger privately authored evaluation set.

Saved result hashes detect accidental edits. They do not authenticate externally supplied reports:
anyone can recompute a hash. A public leaderboard operator must rerun submissions on controlled
workers. Never treat arbitrary uploaded result JSON as an official score.

## Contamination and generalization

The public reference solutions are intentionally available for debugging. They cannot simultaneously
serve as a defensibly unseen test set. For a research release:

- Keep holdout task contracts private until evaluation closes; commit their hashes beforehand.
- Author new compositions and parameter ranges, rather than renaming known examples.
- Freeze prompts, images and model versions before collecting results.
- Separate public-reference performance, private-task performance and any interactive repair track.
- Audit source similarity and benchmark-specific imports as analysis, without making a second LLM
  responsible for the physical verdict.

The runner supports private frozen task files, but this repository does not invent a secret,
validated holdout or claim that contamination is solved. The default candidate image contains no
reference modules and has no network access. A model can still reproduce memorized designs;
the publication protocol must account for that.

## Limits of the physical claim

These are rigid-body numerical experiments. They do not certify elastic deformation, stress,
yielding, fatigue, wear, lubrication, temperature, fabrication tolerances or human safety.
Bearings outside the free-guide task are ideal supplied fixtures. The current tasks evaluate
fixed architectures, not arbitrary topology invention or general spatial assembly planning.

Static geometry is checked with B-Rep predicates, while dynamic contact is checked on verified
convex cells at discrete times. Half-step convergence and bounded penetration improve rigor;
they are not a proof of collision freedom between samples or an infinite-horizon guarantee.
Cross-platform floating-point identity is not assumed. Those limits should accompany all claims.

