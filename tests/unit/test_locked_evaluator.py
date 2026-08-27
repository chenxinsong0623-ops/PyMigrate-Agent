from __future__ import annotations

import json

import pytest

from app.evaluation import locked


def test_locked_selftest_exercises_scorers_without_locked_inputs() -> None:
    locked.run_selftest()


def test_locked_binary_line_and_one_hop_scorers_are_deterministic() -> None:
    gold = {
        ("fx-a", "pkg/model.py", 10, "rule_a"),
        ("fx-b", "pkg/model.py", 10, "rule_a"),
        ("fx-b", "pkg/settings.py", 20, "rule_b"),
    }
    predictions = {
        ("fx-a", "pkg/model.py", 10, "rule_a"),
        ("fx-a", "pkg/model.py", 11, "rule_a"),
        ("fx-b", "pkg/model.py", 10, "rule_a"),
        ("fx-b", "pkg/extra.py", 99, "rule_z"),
    }

    binary = locked._score_binary(gold, predictions)  # noqa: SLF001
    assert binary["tp"] == 2
    assert binary["fp"] == 2
    assert binary["fn"] == 1
    assert binary["precision"] == 0.5
    assert binary["recall"] == 2 / 3
    assert binary["f1"] == pytest.approx(4 / 7)

    line_formula = (
        "exact-line / predictions whose (file, rule_id) matches positive gold"
    )
    one_hop_formula = (
        "(positive_correct + negative_correct) / "
        "(positive_gold + negative_gold + unexpected_predictions)"
    )
    assert locked._line_accuracy(gold, predictions) == {  # noqa: SLF001
        "formula": line_formula,
        "numerator": 2,
        "denominator": 3,
        "accuracy": 2 / 3,
    }

    assert locked._one_hop_accuracy(  # noqa: SLF001
        positives={("importer.py", "imported.py"), ("root.py", "leaf.py")},
        negatives={("root.py", "unrelated.py")},
        predictions={
            ("importer.py", "imported.py"),
            ("root.py", "unrelated.py"),
            ("x.py", "y.py"),
        },
    ) == {
        "formula": one_hop_formula,
        "positive_relation_correct": 1,
        "positive_relation_missed": 1,
        "forbidden_negative_relation_incorrectly_emitted": 1,
        "unexpected_relation_emitted": 1,
        "negative_relation_correct": 0,
        "denominator": 4,
        "accuracy": 0.25,
    }


def test_locked_rerun_guard_allows_empty_report_directory(tmp_path) -> None:
    (tmp_path / "reports").mkdir()

    locked._guard_no_prior_consumption(tmp_path)  # noqa: SLF001


def test_locked_rerun_guard_rejects_consumed_json_artifact(tmp_path) -> None:
    report = tmp_path / "reports" / "eval.json"
    report.parent.mkdir()
    report.write_text(
        json.dumps({"locked_run_consumed": True, "run_attempt": locked.RUN_ATTEMPT}),
        encoding="utf-8",
    )

    with pytest.raises(
        locked.LockedEvaluationAlreadyRunError, match="already consumed"
    ):
        locked._guard_no_prior_consumption(tmp_path)  # noqa: SLF001


def test_locked_rerun_guard_rejects_existing_csv_artifact(tmp_path) -> None:
    report = tmp_path / "reports" / "retrieval_metrics.csv"
    report.parent.mkdir()
    report.write_text("system,Recall@3\nhybrid,0.9\n", encoding="utf-8")

    with pytest.raises(locked.LockedEvaluationAlreadyRunError, match="blocks rerun"):
        locked._guard_no_prior_consumption(tmp_path)  # noqa: SLF001
