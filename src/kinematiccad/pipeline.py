"""Host orchestration. Secrets stay here; candidate and judge only receive bounded files."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile

from .evidence import infrastructure_evidence
from .io import confined_file, digest, read_json, write_json
from .schema import Submission


def run_design(task, source: str, output: Path, sandbox) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Run output must be empty")
    write_json(output / "task.json", task)
    (output / "design.py").write_text(source, encoding="utf-8")
    stage = "candidate"
    try:
        with tempfile.TemporaryDirectory(prefix=".kcb-work-", dir=output) as temporary:
            root = Path(temporary)
            candidate_input = root / "candidate-input"
            candidate_input.mkdir()
            (candidate_input / "design.py").write_text(source, encoding="utf-8")
            assets = root / "assets"
            sandbox.run("candidate", candidate_input, assets)
            manifest = Submission.model_validate(read_json(assets / "submission.json"))
            # Build a new read-only judge input from only the explicitly allowed files.
            judge_input = root / "judge-input"
            judge_input.mkdir()
            write_json(judge_input / "task.json", task)
            write_json(judge_input / "submission.json", manifest)
            for part in manifest.parts:
                shutil.copyfile(confined_file(assets, part.step), judge_input / part.step)
            shutil.copytree(judge_input, output / "assets")
            stage = "judge"
            sandbox.run("judge", judge_input, output / "evaluation")
            report = read_json(output / "evaluation" / "result.json")
    except Exception as exc:
        report = infrastructure_evidence(
            output / "evaluation",
            task,
            stage + "_timeout" if isinstance(exc, TimeoutError) else stage + "_error",
            str(exc),
        )
    write_json(
        output / "run.json",
        {
            "format": "kcb-run-1",
            "task_id": task.id,
            "task_sha256": digest(task),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "sandbox": sandbox.provenance,
            "passed": report["passed"],
            "score": report["score"],
            "status": report["status"],
        },
    )
    return report
