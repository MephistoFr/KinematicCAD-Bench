"""Re-evaluate a recorded batch after a judge revision, without generating new answers."""

import argparse
import hashlib
from pathlib import Path
import shutil

from kinematiccad.io import confined_file, digest, read_json, write_json
from kinematiccad.schema import Submission, Task
from kinematiccad.sandbox import Sandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unsafe-local", action="store_true")
    args = parser.parse_args()
    suite = read_json(args.suite)
    batch = read_json(args.batch / "batch.json")
    if batch["suite_sha256"] != digest(suite):
        raise ValueError("The recorded answers belong to another suite")
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        raise ValueError("Output must be empty")
    sandbox = Sandbox(unsafe_local=args.unsafe_local)
    write_json(args.out / "batch.json", {**batch, "rejudged_from_batch_sha256": digest(batch)})
    failures = 0
    for record in suite["tasks"]:
        task = Task.model_validate(record)
        original = args.batch / task.id
        target = args.out / task.id
        target.mkdir()
        original_run = read_json(original / "run.json")
        if original_run["task_sha256"] != digest(task):
            raise ValueError("Recorded task hash mismatch")
        source = confined_file(original, "design.py", 1_000_000).read_bytes()
        # run_design hashes the source as UTF-8; preserve it exactly.
        if hashlib.sha256(source).hexdigest() != original_run["source_sha256"]:
            # Windows text files can use CRLF even when the original source was LF.
            normalized = source.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
            if hashlib.sha256(normalized).hexdigest() != original_run["source_sha256"]:
                raise ValueError("Recorded source hash mismatch")
        (target / "design.py").write_bytes(source)
        write_json(target / "task.json", task)
        assets = target / "assets"
        assets.mkdir()
        manifest = Submission.model_validate(read_json(original / "assets" / "submission.json"))
        write_json(assets / "submission.json", manifest)
        write_json(assets / "task.json", task)
        for part in manifest.parts:
            shutil.copyfile(confined_file(original / "assets", part.step), assets / part.step)
        print(f"Re-evaluating {task.id}", flush=True)
        sandbox.run("judge", assets, target / "evaluation")
        report = read_json(target / "evaluation" / "result.json")
        write_json(
            target / "run.json",
            {
                **original_run,
                "sandbox": sandbox.provenance,
                "passed": report["passed"],
                "score": report["score"],
                "status": report["status"],
            },
        )
        failures += not report["passed"]
        print(report["status"], flush=True)
    if (args.batch / "inference").is_dir():
        shutil.copytree(args.batch / "inference", args.out / "inference")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
