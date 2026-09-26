"""Freeze the public seed-zero suite and standalone reference answers."""

from pathlib import Path

from kinematiccad.io import digest, write_json
from kinematiccad.references import reference_script
from kinematiccad.schema import Submission, Task
from kinematiccad.tasks import FAMILIES, make_task


def main():
    root = Path(__file__).resolve().parents[1]
    tasks = [make_task(family) for family in FAMILIES]
    suite = {
        "format": "kcb-suite-1",
        "split": "public-calibration",
        "tasks": [t.model_dump(mode="json") for t in tasks],
    }
    write_json(root / "suites" / "calibration.json", suite)
    write_json(root / "schemas" / "task.schema.json", Task.model_json_schema())
    write_json(root / "schemas" / "submission.schema.json", Submission.model_json_schema())
    for task in tasks:
        target = root / "examples" / "references" / (task.id + ".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(reference_script(task), encoding="utf-8")
    print(f"Frozen {len(tasks)} tasks; suite SHA-256: {digest(suite)}")


if __name__ == "__main__":
    main()
