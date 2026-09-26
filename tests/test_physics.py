import numpy as np
import pytest
from types import SimpleNamespace

from kinematiccad.evaluator import evaluate
from kinematiccad.geometry import inspect_geometry
from kinematiccad.io import digest, read_json
from kinematiccad.physics import compile_model, metrics, simulate
from kinematiccad.references import reference_parts
from kinematiccad.sdk import Part, box, cylinder, export
from kinematiccad.tasks import FAMILIES, make_task


@pytest.mark.integration
@pytest.mark.parametrize("family", FAMILIES)
def test_reference_passes_all_gates_at_both_timesteps(tmp_path, family):
    task = make_task(family)
    assets = tmp_path / "assets"
    export(reference_parts(task), assets)
    result = evaluate(task, assets, tmp_path / "result")
    assert result["passed"], result
    assert all(t["converged"] for t in result["trials"])
    assert (tmp_path / "result" / "preview.png").is_file()
    assert (tmp_path / "result" / "evidence.html").is_file()
    assert len(list((tmp_path / "result").glob("*.gif"))) == 2


@pytest.mark.integration
def test_smooth_noncontact_gears_fail_even_with_valid_geometry(tmp_path):
    task = make_task("spur")
    p = task.parameters
    parts = [
        Part.from_cells(name, [cylinder(p[key] * p["module"] / 2 - 0.06, 6, segments=120)])
        for name, key in [("input", "teeth_in"), ("output", "teeth_out")]
    ]
    export(parts, tmp_path)
    geometry = inspect_geometry(task, tmp_path)
    run = simulate(task, geometry, task.trials[0])
    verdict = metrics(task, geometry, task.trials[0], run)
    assert not verdict["passed"]
    assert "motion_law" in verdict["reasons"]


@pytest.mark.integration
def test_exact_trace_replay_and_no_output_actuator(tmp_path):
    task = make_task("slider_crank")
    export(reference_parts(task), tmp_path)
    geometry = inspect_geometry(task, tmp_path)
    model, xml = compile_model(task, geometry)
    assert model.nu == 1
    assert 'joint="crank"' in xml
    assert "<joint polycoef=" not in xml
    a = simulate(task, geometry, task.trials[0])
    b = simulate(task, geometry, task.trials[0])
    assert digest(a["trace"]) == digest(b["trace"])
    assert np.array_equal(np.array(a["trace"]), np.array(b["trace"]))


@pytest.mark.integration
def test_linear_guide_must_physically_resist_lateral_load(tmp_path):
    task = make_task("linear")
    parts = reference_parts(task)
    parts[1] = Part.from_cells("guide", [box(100, 12.4, 2, (0, 0, -4.2))])
    export(parts, tmp_path)
    geometry = inspect_geometry(task, tmp_path)  # Rest clearance and B-Rep still pass.
    model, _ = compile_model(task, geometry)
    assert model.nv == 6  # No hidden ideal slider constraint to conceal absent walls.
    run = simulate(task, geometry, task.trials[0])
    assert "guide_escape_or_tilt" in metrics(task, geometry, task.trials[0], run)["reasons"]


def test_ratio_gate_catches_small_systematic_error():
    task = make_task("spur")
    trial = task.trials[0]
    time = np.linspace(0, task.duration, 2000)
    theta = 3 * time
    ratio = task.parameters["ratio"] * 1.01
    trace = np.column_stack(
        [time, theta, ratio * theta, np.full_like(time, 3), np.full_like(time, 3 * ratio)]
    )
    run = {
        "trace": trace.tolist(),
        "failure": None,
        "max_penetration_mm": 0,
        "max_closure_mm": 0,
        "max_guidance_error_mm": 0,
        "max_tilt_rad": 0,
        "motor_work_j": 1,
        "load_work_j": 1,
        "worst_contact": None,
    }
    geometry = SimpleNamespace(properties={task.output: {"mass": 1}})
    verdict = metrics(task, geometry, trial, run)
    assert verdict["relative_ratio_error"] == pytest.approx(0.01)
    assert "transmission_ratio" in verdict["reasons"]


@pytest.mark.integration
def test_refined_failure_has_its_own_visual_replay(tmp_path):
    task = make_task("linear").model_copy(update={"max_penetration_mm": 0.045})
    export(reference_parts(task), tmp_path / "assets")
    report = evaluate(task, tmp_path / "assets", tmp_path / "result")
    assert not report["passed"]
    assert report["trials"][0]["coarse"]["passed"]
    assert not report["trials"][0]["fine"]["passed"]
    evidence = read_json(tmp_path / "result" / "evidence.json")
    assert any(r["name"] == "forward_halfstep" for r in evidence["runs"])
