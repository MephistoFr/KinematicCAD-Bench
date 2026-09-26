import numpy as np
import pytest
from pydantic import ValidationError

from kinematiccad.io import canonical, digest, read_json
from kinematiccad.physics import expected
from kinematiccad.schema import Cell, Submission, Task
from kinematiccad.tasks import FAMILIES, make_task


def test_frozen_task_generation():
    for family in FAMILIES:
        assert canonical(make_task(family, 12)) == canonical(make_task(family, 12))
        assert digest(make_task(family, 12)) != digest(make_task(family, 13))


def test_analytic_motion_contracts():
    task = make_task("slider_crank")
    trace = np.zeros((3, 5))
    trace[:, 1] = [0, np.pi, 2 * np.pi]
    assert np.allclose(
        expected(task, trace, 1, task.trials[0]), [0, -2 * task.parameters["radius"] * 0.001, 0]
    )
    task = make_task("planetary")
    assert task.parameters["ratio"] == task.parameters["teeth_sun"] / (
        task.parameters["teeth_sun"] + task.parameters["teeth_ring"]
    )


def test_reject_nonfinite_and_extraneous_actuation():
    with pytest.raises(ValidationError):
        Cell(vertices=[(float("nan"), 0, 0)] * 4)
    with pytest.raises(ValidationError):
        Submission(parts=[], actuator={"output": "teleport"})


def test_duplicate_and_nonfinite_json(tmp_path):
    path = tmp_path / "bad.json"
    for text in ['{"x":1,"x":2}', '{"x":NaN}']:
        path.write_text(text)
        with pytest.raises(ValueError):
            read_json(path)


def test_empty_and_duplicate_trials_cannot_vacuously_pass():
    data = make_task("linear").model_dump(mode="json")
    for trials in ([], [data["trials"][0], data["trials"][0]]):
        with pytest.raises(ValidationError):
            Task.model_validate({**data, "trials": trials})
