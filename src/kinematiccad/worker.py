"""Container entry point. Candidate and judge are invoked in separate containers."""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path
import sys

from .io import read_json
from .process import bounded_run
from .schema import Submission, Task
from .transport import pack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("candidate", "judge"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/work/output"))
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--timeout", type=float, default=280)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(sys.stderr):
        if args.mode == "candidate":
            command = [sys.executable, str((args.input / "design.py").resolve()), str(args.output.resolve())]
            bounded_run(command, timeout=args.timeout, output_limit=1_000_000, cwd=Path.cwd())
            manifest = Submission.model_validate(read_json(args.output / "submission.json"))
            expected = {"submission.json"} | {p.step for p in manifest.parts}
            if {p.name for p in args.output.iterdir()} != expected:
                raise ValueError("Unexpected candidate output files")
        else:
            from .evaluator import evaluate

            task = Task.model_validate(read_json(args.input / "task.json"))
            evaluate(task, args.input, args.output)
    if args.archive:
        sys.stdout.buffer.write(pack(args.output))


if __name__ == "__main__":
    main()
