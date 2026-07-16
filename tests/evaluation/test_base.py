"""The Evaluator seam: value objects and the ABC's shared plumbing. Hermetic."""
from __future__ import annotations

import dataclasses

import pytest

from rag_blocks.evaluation import (
    EvalOutcome,
    EvalSample,
    Evaluator,
    MetricReport,
    RetrievalEvaluator,
)


class _CountingEvaluator(Evaluator):
    """Records how often it is asked to score — the tuner's two-phase
    screening is asserted with this in PR 3."""

    kind = "evaluator"
    name = "counting"
    stage = "retrieval"

    def __init__(self, config=None, **overrides):
        super().__init__(config, **overrides)
        self.calls: list[int] = []

    def evaluate(self, outcomes):
        self.calls.append(len(outcomes))
        return MetricReport(metrics={"seen": float(len(outcomes))})


# -- the value objects are immutable inputs ------------------------------


@pytest.mark.parametrize(
    "value",
    [
        EvalSample(question="q"),
        EvalOutcome(sample=EvalSample(question="q")),
        MetricReport(metrics={}),
    ],
)
def test_eval_value_objects_are_frozen(value):
    # A dataset row mutated halfway through a tuning run would silently
    # invalidate every trial that already scored against it.
    first_field = dataclasses.fields(value)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, first_field, "mutated")


def test_a_sample_needs_only_a_question():
    # Both label kinds are optional and independent: retrieval-only and
    # generation-only datasets are both legitimate.
    sample = EvalSample(question="what is the objective?")
    assert sample.relevant_chunk_ids is None
    assert sample.reference_answer is None


def test_an_outcome_defaults_to_the_phase_1_shape():
    # Retrieval ran, generation did not — not an error, just phase 1.
    out = EvalOutcome(sample=EvalSample(question="q"))
    assert out.retrieved == ()
    assert out.answer is None


def test_a_report_may_omit_per_sample_detail():
    assert MetricReport(metrics={"recall@1": 1.0}).per_sample == ()


# -- the ABC enforces its contract ---------------------------------------


def test_evaluator_cannot_be_instantiated_without_evaluate():
    class _Incomplete(Evaluator):
        kind = "evaluator"
        name = "incomplete"
        stage = "retrieval"

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_kind_is_declared_once_on_the_abc():
    # The house rule: `kind` on the stage ABC, `name`/`version` on the
    # concrete class — so the registry slot can never drift per implementation.
    assert Evaluator.kind == "evaluator"
    assert RetrievalEvaluator.kind == "evaluator"


def test_stage_is_class_level_not_config():
    # `stage` is a fact about what an evaluator measures, so it must not be
    # tunable per instance — the tuner reads it to decide phase 1 vs. phase 2.
    assert "stage" not in RetrievalEvaluator().describe()["config"]


# -- shared aggregation plumbing -----------------------------------------


def test_aggregate_averages_only_the_samples_that_scored_a_metric():
    # The honesty invariant, tested on the base directly: a metric absent
    # from a sample must not be averaged in as a zero.
    evaluator = _CountingEvaluator()
    aggregate = evaluator._aggregate([{"a": 1.0}, {}, {"a": 0.0, "b": 1.0}])
    assert aggregate == {"a": 0.5, "b": 1.0}


def test_aggregate_of_nothing_is_nothing():
    assert _CountingEvaluator()._aggregate([]) == {}
    assert _CountingEvaluator()._aggregate([{}, {}]) == {}


def test_aggregate_orders_metrics_stably():
    # Trial records are diffed and hashed; key order must not wobble.
    aggregate = _CountingEvaluator()._aggregate([{"z": 1.0, "a": 1.0, "m": 1.0}])
    assert list(aggregate) == ["a", "m", "z"]


# -- identity ------------------------------------------------------------


def test_describe_and_fingerprint_come_free_from_component():
    described = RetrievalEvaluator().describe()
    assert described["kind"] == "evaluator"
    assert described["name"] == "ir"
    assert len(RetrievalEvaluator().fingerprint()) == 16


def test_an_evaluator_with_no_config_declares_none():
    assert _CountingEvaluator().config is None
