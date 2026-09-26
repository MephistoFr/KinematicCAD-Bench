"""Trusted evaluator entry point. Receives assets, never a Python design script."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
from pathlib import Path

from . import __version__
from .evidence import write_evidence
from .geometry import Rejected, inspect_geometry
from .io import digest, write_json
from .physics import evaluate_dynamics
from .schema import Task


def environment():
    source = Path(__file__).parent
    implementation = digest(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(source.iterdir())
            if p.suffix in (".py", ".html")
        }
    )
    return dict(
        benchmark=__version__,
        python=platform.python_version(),
        os=platform.system(),
        implementation_sha256=implementation,
        machine=platform.machine(),
        processor=platform.processor(),
        libraries={
            p: importlib.metadata.version(p)
            for p in ("cadquery", "cadquery-ocp", "mujoco", "numpy", "scipy", "pillow")
        },
    )


def evaluate(task: Task, assets: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    meshes, runs = {}, []
    report = dict(
        format="kcb-result-1",
        task_id=task.id,
        family=task.family,
        task_sha256=digest(task),
        environment=environment(),
        status="error",
        passed=False,
        score=0.0,
        geometry=None,
        trials=[],
        failure=None,
    )

    def progress(current):
        meshes.update(current)

    try:
        geometry = inspect_geometry(task, assets, progress)
        report["geometry"] = geometry.report
        report["submission_sha256"] = digest(
            {
                p.name: hashlib.sha256((assets / p.step).read_bytes()).hexdigest()
                for p in geometry.manifest.parts
            }
            | {"manifest": digest(geometry.manifest)}
        )
        results, runs = evaluate_dynamics(task, geometry, output)
        report["trials"] = results
        report["passed"] = all(r["passed"] for r in results)
        report["status"] = "passed" if report["passed"] else "failed"
        report["score"] = (
            min(min(r["coarse"]["score"], r["fine"]["score"]) for r in results) if report["passed"] else 0.0
        )
        if not report["passed"]:
            report["failure"] = "dynamic_contract"
    except Rejected as exc:
        report.update(status="failed", passed=False, score=0.0, failure=exc.code, detail=exc.detail)
    except Exception as exc:
        # CAD import/compiler exceptions must never yield a pass. Details remain reviewable.
        report.update(
            status="error",
            passed=False,
            score=0.0,
            failure="evaluation_error",
            detail=f"{type(exc).__name__}: {str(exc)[:3000]}",
        )
    write_json(output / "task.json", task)
    write_evidence(output, task, meshes, runs, report)
    # Evidence is an acceptance gate too, not an optional decoration.
    report["evidence_sha256"] = hashlib.sha256((output / "evidence.json").read_bytes()).hexdigest()
    report["result_sha256"] = digest(report)
    write_json(output / "result.json", report)
    return report
