import pytest
from kinematiccad.io import digest, write_json
from kinematiccad.leaderboard import rank
from kinematiccad.tasks import make_task


def test_missing_and_failed_attempts_remain_in_denominator(tmp_path):
    tasks = [make_task("linear", i).model_dump(mode="json") for i in range(3)]
    suite = {"tasks": tasks}
    batch = tmp_path / "batch"
    write_json(batch / "batch.json", {"suite_sha256": digest(suite), "model_label": "test"})
    task = tasks[0]
    root = batch / task["id"]
    write_json(root / "run.json", {"task_sha256": digest(task), "sandbox": {"rankable": False}})
    write_json(
        root / "evaluation" / "result.json",
        {
            "task_sha256": digest(task),
            "passed": True,
            "status": "passed",
            "score": 0.8,
            "trials": [{"passed": True}],
        },
    )
    row = rank(suite, [batch], allow_local=True)["rows"][0]
    assert row["total"] == 3 and row["pass_at_1"] == pytest.approx(1 / 3)
    assert row["failures"] == {"missing": 2}
    with pytest.raises(ValueError, match="Unsafe local"):
        rank(suite, [batch])


def test_cannot_mix_suites(tmp_path):
    write_json(tmp_path / "batch.json", {"suite_sha256": "wrong", "model_label": "x"})
    with pytest.raises(ValueError, match="different suites"):
        rank({"tasks": [make_task("linear").model_dump(mode="json")]}, [tmp_path])
