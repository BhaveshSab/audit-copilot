from audit_copilot.evaluate import classification, evaluate, percentile


def test_metrics_not_manufactured():
    result = classification(
        ["clean", "missing", "missing"], ["missing", "missing", "insufficient_evidence"]
    )
    assert result["false_findings_on_clean"] == 1
    assert result["per_class"]["missing"]["precision"] == 0.5
    assert result["per_class"]["missing"]["recall"] == 0.5
    assert percentile([1, 2, 3], 0.95) == 3


async def test_full_fixture_eval_is_labelled_and_retains_errors():
    result = await evaluate()
    assert (
        result["cases"] == 30
        and result["queries"] == 40
        and result["refusal_questions"] == 10
    )
    assert result["mode"] == "fixture"
    assert "NOT MODEL QUALITY" in result["claim_scope"]
    assert set(result["variants"]) == {"single", "multi", "multi_no_retrieval"}
    assert len(result["traces"]) == 90
    for v in result["variants"].values():
        assert v["total_cost_usd"] is None
        assert 0 <= v["accuracy"] <= 1
        assert "confusion_matrix" in v
