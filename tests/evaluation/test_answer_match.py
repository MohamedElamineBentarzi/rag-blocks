"""AnswerMatchEvaluator: generation scoring with no judge. Hermetic."""
from __future__ import annotations

import pytest

from rag_blocks.core.contracts import Answer, Citation
from rag_blocks.evaluation import (
    AnswerMatchEvaluator,
    EvalOutcome,
    EvalSample,
    exact_match,
    token_f1,
)
from tests.contract_checks import assert_evaluator_contract


def outcome(answer_text, reference, question="q") -> EvalOutcome:
    return EvalOutcome(
        sample=EvalSample(question=question, reference_answer=reference),
        answer=Answer(text=answer_text) if answer_text is not None else None,
    )


# -- exact match ---------------------------------------------------------


@pytest.mark.parametrize(
    "answer, reference, expected",
    [
        ("Paris", "Paris", 1.0),
        ("paris", "PARIS", 1.0),              # case-insensitive
        ("  Paris  ", "Paris", 1.0),          # whitespace-normalized
        ("Paris.", "Paris", 1.0),             # punctuation is not a word
        ("Lyon", "Paris", 0.0),
        ("Paris France", "Paris", 0.0),       # brutal by design
    ],
)
def test_exact_match_normalizes_case_and_punctuation(answer, reference, expected):
    assert exact_match(answer, reference) == expected


# -- token F1 ------------------------------------------------------------


def test_token_f1_is_1_for_identical_answers():
    assert token_f1("the cat sat", "the cat sat") == pytest.approx(1.0)


def test_token_f1_is_0_when_nothing_overlaps():
    assert token_f1("alpha beta", "gamma delta") == 0.0


def test_token_f1_matches_the_arithmetic_by_hand():
    # answer "the cat" (2 tokens) vs reference "the cat sat" (3 tokens):
    #   overlap = 2 ⇒ precision = 2/2 = 1.0, recall = 2/3
    #   F1 = 2 * 1.0 * (2/3) / (1.0 + 2/3) = 0.8
    assert token_f1("the cat", "the cat sat") == pytest.approx(0.8)


def test_token_f1_credits_partial_overlap():
    partial = token_f1("the cat sat", "the cat sat on the mat")
    assert 0.0 < partial < 1.0


def test_token_f1_ignores_word_order():
    # Bag of words: the point is overlap, not sequence.
    assert token_f1("cat the sat", "the cat sat") == pytest.approx(1.0)


def test_repeating_a_keyword_cannot_inflate_the_score():
    # Multiset overlap: "cat cat cat" earns credit for ONE "cat", and the
    # padding costs precision. Set-based overlap would score this 1.0.
    padded = token_f1("cat cat cat", "cat")
    assert padded < token_f1("cat", "cat")


@pytest.mark.parametrize(
    "answer, reference, expected",
    [
        ("", "", 1.0),          # vacuously equal
        ("", "something", 0.0),  # said nothing
        ("something", "", 0.0),  # nothing to match
        ("...", "!!!", 1.0),     # no word tokens either side
    ],
)
def test_token_f1_edge_cases(answer, reference, expected):
    assert token_f1(answer, reference) == pytest.approx(expected)


def test_accented_text_tokenizes_as_words():
    # French corpora are the motivating case; naive [a-z]+ would shred these.
    assert token_f1("les objectifs du parcours", "les objectifs du parcours") == 1.0
    assert exact_match("PARCOURS SIIA", "parcours siia") == 1.0


# -- the evaluator -------------------------------------------------------


def test_satisfies_the_evaluator_contract():
    assert_evaluator_contract(
        AnswerMatchEvaluator(),
        [outcome("Paris", "Paris"), outcome("Lyon", "Paris")],
    )


def test_citation_markers_do_not_penalize_an_answer():
    # Markers are OUR bookkeeping injected into the text; scoring an answer
    # down for carrying provenance would be perverse.
    report = AnswerMatchEvaluator().evaluate([outcome("Paris [1]", "Paris")])
    assert report.metrics["exact_match"] == 1.0
    assert report.metrics["token_f1"] == pytest.approx(1.0)


def test_citation_stripping_can_be_turned_off():
    report = AnswerMatchEvaluator(strip_citations=False).evaluate(
        [outcome("Paris [1]", "Paris")]
    )
    assert report.metrics["exact_match"] == 0.0


def test_answer_carrying_citations_object_is_scored_on_its_text():
    cited = EvalOutcome(
        sample=EvalSample(question="q", reference_answer="Paris"),
        answer=Answer(
            text="Paris [1]",
            citations=[Citation(marker=1, chunk_id="d:0", doc_id="d", page_start=1)],
        ),
    )
    assert AnswerMatchEvaluator().evaluate([cited]).metrics["exact_match"] == 1.0


def test_aggregate_is_the_mean_over_samples():
    report = AnswerMatchEvaluator().evaluate(
        [outcome("Paris", "Paris"), outcome("Lyon", "Paris")]
    )
    assert report.metrics["exact_match"] == pytest.approx(0.5)


def test_samples_without_a_reference_answer_are_skipped():
    unreferenced = EvalOutcome(
        sample=EvalSample(question="q"), answer=Answer(text="anything")
    )
    report = AnswerMatchEvaluator().evaluate([outcome("Paris", "Paris"), unreferenced])
    assert report.metrics["exact_match"] == pytest.approx(1.0)  # not 0.5
    assert report.per_sample[1] == {}


def test_a_phase_1_outcome_with_no_answer_is_skipped_not_failed():
    # Phase 1 of a tuning run scores retrieval only, so `answer is None` is a
    # normal state — not a generator that produced nothing.
    report = AnswerMatchEvaluator().evaluate(
        [outcome("Paris", "Paris"), outcome(None, "Paris")]
    )
    assert report.metrics["exact_match"] == pytest.approx(1.0)
    assert report.per_sample[1] == {}


def test_config_changes_the_fingerprint():
    assert AnswerMatchEvaluator(strip_citations=True).fingerprint() != (
        AnswerMatchEvaluator(strip_citations=False).fingerprint()
    )


def test_the_two_generation_evaluators_share_a_stage():
    # Interchangeability is the point: the tuner selects by `stage`, so
    # answer-match and (later) ragas must be substitutable at the same slot.
    assert AnswerMatchEvaluator.stage == "generation"
