import os
import pytest

from kinematiccad.io import read_json
from kinematiccad.pipeline import run_design
from kinematiccad.references import reference_script
from kinematiccad.sandbox import Sandbox
from kinematiccad.tasks import make_task


@pytest.mark.integration
def test_end_to_end_in_separate_processes(tmp_path):
    task = make_task("linear")
    report = run_design(
        task, reference_script(task), tmp_path / "case", Sandbox(unsafe_local=True, timeout=60)
    )
    assert report["passed"], report
    run = read_json(tmp_path / "case" / "run.json")
    assert run["sandbox"]["rankable"] is False


def test_script_failure_still_has_visual_evidence(tmp_path):
    task = make_task("linear")
    report = run_design(
        task, "raise RuntimeError('deliberate failure')", tmp_path / "case", Sandbox(unsafe_local=True)
    )
    assert not report["passed"]
    assert report["failure"] == "candidate_error"
    assert (tmp_path / "case" / "evaluation" / "preview.png").exists()


@pytest.mark.docker
@pytest.mark.skipif(
    not os.environ.get("KCB_TEST_DOCKER"), reason="Set KCB_TEST_DOCKER=1 after building both images"
)
def test_docker_isolation_pipeline(tmp_path):
    task = make_task("linear")
    report = run_design(task, reference_script(task), tmp_path / "case", Sandbox(timeout=120))
    assert report["passed"], report
