"""Developer smoke runner; full CLI evaluation also renders evidence and refines dt."""

import argparse
from pathlib import Path
import numpy as np
from kinematiccad.tasks import make_task
from kinematiccad.references import reference_parts
from kinematiccad.sdk import export
from kinematiccad.geometry import inspect_geometry
from kinematiccad.physics import simulate, metrics
from kinematiccad.io import write_json

parser = argparse.ArgumentParser()
parser.add_argument("family")
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--reuse", action="store_true")
args = parser.parse_args()
task = make_task(args.family, args.seed)
directory = Path("runs") / f"check-{task.id}"
print(task.parameters, flush=True)
if not args.reuse:
    export(reference_parts(task), directory)
print("CAD exported", flush=True)
geometry = inspect_geometry(task, directory)
print("Geometry accepted", geometry.report, flush=True)
write_json(directory / "properties.json", geometry.properties)
for trial in task.trials:
    run = simulate(task, geometry, trial)
    print(trial.name, metrics(task, geometry, trial, run), flush=True)
    if run["failure"]:
        print("Last states", run["trace"][-10:], "penetration", run["max_penetration_mm"], flush=True)
    if task.connections:
        link = task.connections[0]
        errors = []
        for f in run["frames"]:
            a, b = f["poses"][link.a], f["poses"][link.b]
            ap = np.array(a["pos"]) + np.array(a["rot"]).reshape(3, 3) @ link.anchor_a
            bp = np.array(b["pos"]) + np.array(b["rot"]).reshape(3, 3) @ link.anchor_b
            errors.append((np.linalg.norm(ap - bp), f["time"], ap, bp))
        print("Worst closure", sorted(errors, key=lambda x: x[0], reverse=True)[:2], flush=True)
