# Extending KinematicCAD-Bench

## Add a model provider

Implement the `Provider.generate(messages, task_id) -> Response` protocol, then register its
factory in `provider_from_config`. Keep inference outside workers. Save the original answer,
parameters, model identifier and usage metadata. Do not add automatic repair or retry without
making it a separately named evaluation track.

Any vendor can already be bridged through a trusted command provider:

```json
{
  "kind": "command",
  "model": "my-exact-local-model",
  "argv": ["python", "my_inference_adapter.py"],
  "timeout": 300
}
```

The program receives `{"messages":[...],"task_id":"..."}` on stdin and returns Python source
on stdout. Send model logs to stderr. Arguments are executed directly, without a shell.

## Create a design script

```python
import sys
from kinematiccad.sdk import Part, box, export

# Example of the CAD interface, not a complete answer to a multi-part task.
part = Part.from_cells("carriage", [box(12, 8, 6)])
export([part], sys.argv[1])
```

Body coordinates are local to the task's parent hierarchy. Do not bake the task's world offsets
into a part and then apply them again. `prism` creates the **convex hull** of its points: split a
concave cross-section into actual convex construction cells. `cylinder` is a regular polygonal
prism, explicitly matching its collision hull. `Part(name, shape, cells)` supports direct
CadQuery solids with a decomposition that the judge checks independently.

Every reference can be exported as standalone candidate code:

```bash
uv run kcb reference --family planetary --out planetary.py
uv run kcb evaluate --family planetary --design planetary.py --out runs/planetary
```

## Add a mechanical family

1. Define the allowed solids, coordinate frames, fixture topology, material, envelopes and attachment
   locations. Decide which joints are supplied ideal fixtures and which relationships must emerge
   from physical contact.
2. Derive an analytical relation from mechanics and add it to `physics.expected`. Include position,
   velocity/ratio, sufficient travel, load transfer and failure thresholds.
3. Add deterministic task generation and validate schema limits. Do not embed an analytical output
   trajectory in the physics compiler or actuator configuration.
4. Add a CAD reference that passes the B-Rep checks, all load directions and both timesteps.
5. Add negative controls that preserve plausible appearance while removing actual transmission,
   removing supports, changing the ratio or causing interference.
6. Record calibration across more than one parameter value and update the protocol version and
   task hashes when any physical acceptance setting changes.

Tests should challenge a physical assumption or trust boundary. A test that merely restates a
constant is not evidence of mechanical correctness. Start with a simple complete mechanism and
inspect both its numerical traces and visual replay.

## Artifact layout

```text
case/
  task.json, design.py, run.json
  assets/                    frozen judge input (STEP, cells and task)
  evaluation/
    result.json              verdict, geometry, metrics, versions and hashes
    task.json                frozen task
    model-<trial>.xml         evaluator-owned physics scene
    trace-<trial>.json        [time, input q, output q, input v, output v]
    trace-<trial>-halfstep.json
    evidence.json            geometry and measured world transforms
    evidence.html            standalone interactive replay
    preview.png
    <trial>.gif
```

If source execution or the judge process fails before geometry can be recovered, the supervisor
still writes diagnostic JSON, offline HTML and a PNG explaining the failure. It does not invent
a mechanical animation when no simulation exists.

When only the refined simulation fails, the evidence includes an additional `_halfstep` replay
of that failure. The displayed motion therefore comes from the simulation that actually failed.

After a judge revision, `scripts/rejudge.py` can evaluate a recorded batch against the same frozen
suite without regenerating model answers. It writes a new batch and checks task/source hashes.
This is distinct from `kcb replay`, which requires the same runtime cohort and checks exact identity.

