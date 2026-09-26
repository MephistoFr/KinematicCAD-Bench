"""Fast development probe after check_reference has independently accepted the geometry."""

import argparse
from pathlib import Path
from kinematiccad.geometry import Geometry
from kinematiccad.io import read_json
from kinematiccad.schema import Submission
from kinematiccad.tasks import make_task
from kinematiccad.physics import simulate, metrics

parser = argparse.ArgumentParser()
parser.add_argument("family")
parser.add_argument("--halfstep", action="store_true")
args = parser.parse_args()
task = make_task(args.family)
root = Path("runs") / f"check-{task.id}"
geometry = Geometry(
    Submission.model_validate(read_json(root / "submission.json")),
    {},
    read_json(root / "properties.json"),
    {},
    {},
)
for trial in task.trials:
    run = simulate(task, geometry, trial, task.timestep / (2 if args.halfstep else 1))
    print(trial.name, metrics(task, geometry, trial, run), flush=True)
    if run["failure"]:
        print(run["trace"][-3:], flush=True)
