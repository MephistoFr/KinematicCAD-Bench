from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from .io import digest, read_json, write_json
from .schema import Task
from .tasks import FAMILIES, make_task


def task_from_args(args):
    return (
        Task.model_validate(read_json(args.task))
        if getattr(args, "task", None)
        else make_task(args.family, args.seed)
    )


def runtime_args(parser):
    parser.add_argument(
        "--unsafe-local", action="store_true", help="Trusted development scripts only; unranked"
    )
    parser.add_argument("--image", default="kinematiccad-bench:0.1.0")
    parser.add_argument("--timeout", type=float, default=600)


def task_args(parser):
    parser.add_argument("--task", type=Path, help="A frozen task JSON")
    parser.add_argument("--family", choices=FAMILIES, default="linear")
    parser.add_argument("--seed", type=int, default=0)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kcb", description="KinematicCAD-Bench: deterministic mechanical contracts"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local native libraries and Docker availability")
    suite = sub.add_parser("suite", help="Freeze procedural tasks into a versioned suite")
    suite.add_argument("--out", type=Path, required=True)
    suite.add_argument("--seeds", default="0")
    suite.add_argument("--families", default=",".join(FAMILIES))
    task = sub.add_parser("task", help="Write one mathematical contract")
    task_args(task)
    task.add_argument("--out", type=Path, required=True)
    reference = sub.add_parser("reference", help="Export a public reference as standalone Python source")
    task_args(reference)
    reference.add_argument("--out", type=Path, required=True)
    for command in ("evaluate", "demo"):
        p = sub.add_parser(
            command, help="Evaluate a design" if command == "evaluate" else "Evaluate a public reference"
        )
        task_args(p)
        runtime_args(p)
        p.add_argument("--out", type=Path, required=True)
        if command == "evaluate":
            p.add_argument("--design", type=Path, required=True)
    bench = sub.add_parser("benchmark", help="Infer and evaluate exactly one attempt per task")
    bench.add_argument("--suite", type=Path, required=True)
    bench.add_argument("--provider", type=Path, required=True)
    bench.add_argument("--label", required=True)
    bench.add_argument("--out", type=Path, required=True)
    runtime_args(bench)
    replay = sub.add_parser(
        "replay", help="Re-evaluate frozen assets and compare both-resolution trace hashes"
    )
    replay.add_argument("run", type=Path)
    replay.add_argument("--out", type=Path, required=True)
    runtime_args(replay)
    board = sub.add_parser("leaderboard", help="Rank complete manifests; missing tasks count as failures")
    board.add_argument("--suite", type=Path, required=True)
    board.add_argument("--batches", type=Path, nargs="+", required=True)
    board.add_argument("--out", type=Path, required=True)
    board.add_argument("--allow-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            from .evaluator import environment

            print(
                json.dumps(
                    {"environment": environment(), "docker_cli": bool(shutil.which("docker"))}, indent=2
                )
            )
            return 0
        if args.command == "suite":
            tasks = [
                make_task(f, int(s)).model_dump(mode="json")
                for f in args.families.split(",")
                for s in args.seeds.split(",")
            ]
            if len({t["id"] for t in tasks}) != len(tasks):
                raise ValueError("Duplicate suite task")
            write_json(args.out, {"format": "kcb-suite-1", "split": "public-calibration", "tasks": tasks})
            print(f"Wrote {len(tasks)} contracts: {args.out.resolve()}")
            return 0
        if args.command in ("task", "reference"):
            task = task_from_args(args)
            if args.command == "task":
                write_json(args.out, task)
            else:
                from .references import reference_script

                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(reference_script(task), encoding="utf-8")
            print(args.out.resolve())
            return 0
        if args.command == "leaderboard":
            from .leaderboard import rank

            result = rank(read_json(args.suite), args.batches, allow_local=args.allow_local)
            write_json(args.out, result)
            print(json.dumps(result, indent=2))
            return 0
        from .sandbox import Sandbox

        sandbox = Sandbox(unsafe_local=args.unsafe_local, image=args.image, timeout=args.timeout)
        if args.command in ("evaluate", "demo"):
            from .pipeline import run_design

            task = task_from_args(args)
            if args.command == "demo":
                from .references import reference_script

                source = reference_script(task)
            else:
                source = args.design.read_text(encoding="utf-8")
            report = run_design(task, source, args.out, sandbox)
            print(
                json.dumps(
                    {
                        "status": report["status"],
                        "failure": report.get("failure"),
                        "score": report["score"],
                        "evidence": str((args.out / "evaluation" / "evidence.html").resolve()),
                    },
                    indent=2,
                )
            )
            return 0 if report["passed"] else 1
        if args.command == "replay":
            original = read_json(args.run / "evaluation" / "result.json")
            sandbox.run("judge", args.run / "assets", args.out)
            replayed = read_json(args.out / "result.json")

            def hashes(report):
                return [(t["name"], t["trace_sha256"], t["fine_trace_sha256"]) for t in report["trials"]]

            same = bool(original.get("trials")) and hashes(original) == hashes(replayed)
            same = (
                same
                and original["environment"] == replayed["environment"]
                and original["passed"] == replayed["passed"]
            )
            print(
                json.dumps(
                    {
                        "identical": same,
                        "original": original.get("result_sha256"),
                        "replay": replayed.get("result_sha256"),
                    },
                    indent=2,
                )
            )
            return 0 if same else 1
        if args.command == "benchmark":
            from .evidence import infrastructure_evidence
            from .inference import infer, provider_from_config
            from .pipeline import run_design

            suite = read_json(args.suite)
            tasks = [Task.model_validate(t) for t in suite["tasks"]]
            if not tasks or len({t.id for t in tasks}) != len(tasks):
                raise ValueError("Empty or duplicate suite tasks")
            config = read_json(args.provider)
            provider = provider_from_config(config)
            args.out.mkdir(parents=True, exist_ok=True)
            if any(args.out.iterdir()):
                raise ValueError("Batch output must be empty")
            write_json(
                args.out / "batch.json",
                dict(
                    format="kcb-batch-1",
                    model_label=args.label,
                    suite_sha256=digest(suite),
                    task_ids=[t.id for t in tasks],
                    provider_config_sha256=digest(config),
                ),
            )
            failures = 0
            for task in tasks:
                print(f"Evaluating {task.id}", flush=True)
                case = args.out / task.id
                inference = args.out / "inference" / task.id
                try:
                    source = infer(provider, task, inference)
                    report = run_design(task, source, case, sandbox)
                except Exception as exc:
                    report = infrastructure_evidence(case / "evaluation", task, "inference_error", str(exc))
                    write_json(
                        case / "run.json",
                        dict(
                            format="kcb-run-1",
                            task_id=task.id,
                            task_sha256=digest(task),
                            sandbox=sandbox.provenance,
                            passed=False,
                            score=0.0,
                            status="error",
                        ),
                    )
                failures += not report["passed"]
                print(f"  {report['status']}: {report.get('failure') or 'all gates passed'}", flush=True)
            print(f"Completed {len(tasks)} attempts, {failures} failures. Artifacts: {args.out.resolve()}")
            return 0 if not failures else 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"kcb: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
