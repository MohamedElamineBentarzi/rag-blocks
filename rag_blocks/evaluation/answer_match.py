"""AnswerMatchEvaluator: generation scoring without a judge.

The generation stage's other implementation is `RagasEvaluator`, which calls an
LLM and costs money per sample. This one is pure string math against
`reference_answer`, which buys three things the judge cannot:

- the hermetic suite and the tuner can score generation with no key, no
  network, and no vendor — the same reason `MemoryVectorStore` exists;
- a deterministic floor to compare a judge against (if an expensive judge
  disagrees with exact-match on questions with one-word answers, suspect the
  judge);
- an honest default for datasets that have reference answers but no budget.

What it cannot do is the reason RAGAS exists: token overlap has no idea
whether an answer is *faithful* to its context, and it punishes correct
paraphrases. Two implementations of one seam with genuinely different
trade-offs — pick per dataset, and the fingerprint records which you used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from ..core.registry import registry
from .base import EvalOutcome, Evaluator, MetricReport

__all__ = ["token_f1", "exact_match", "AnswerMatchEvaluator"]

# Unicode-aware: `\w` keeps accented letters, so French corpora (the
# motivating case for this library) don't tokenize into confetti.
_WORD = re.compile(r"\w+", re.UNICODE)

# Mirrors the marker form `pack_context` emits (generation/packing.py::_MARKER).
_CITATION = re.compile(r"\[\d+\]")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def exact_match(answer: str, reference: str) -> float:
    """1.0 if the answers agree after case/whitespace normalization, else 0.0.

    Brutal and useful: meaningful for short factoid answers, near-useless for
    prose. Reported alongside token-F1 so the pair reveals which kind of
    dataset you have.
    """
    return float(" ".join(_tokens(answer)) == " ".join(_tokens(reference)))


def token_f1(answer: str, reference: str) -> float:
    """Harmonic mean of token precision and recall (bag-of-words overlap).

    Multiset overlap, not set overlap: an answer that repeats a word three
    times gets credit for it once per occurrence in the reference, so padding
    the answer with a keyword can't inflate the score.
    """
    answer_tokens = _tokens(answer)
    reference_tokens = _tokens(reference)
    if not answer_tokens or not reference_tokens:
        # Both empty is vacuously perfect; one empty is a total miss.
        return float(not answer_tokens and not reference_tokens)

    remaining = list(reference_tokens)
    overlap = 0
    for token in answer_tokens:
        if token in remaining:
            remaining.remove(token)
            overlap += 1
    if overlap == 0:
        return 0.0

    precision = overlap / len(answer_tokens)
    recall = overlap / len(reference_tokens)
    return 2 * precision * recall / (precision + recall)


@registry.register
class AnswerMatchEvaluator(Evaluator):
    """Vendor-free generation metrics: token-F1 and exact-match.

    Scores only samples carrying a `reference_answer` whose outcome has an
    `answer`; anything else gets an empty per-sample dict and joins no
    average (a phase-1 outcome has no answer yet, and that is not a zero).
    """

    name = "answer-match"
    version = "0.1.0"
    stage = "generation"

    @dataclass
    class Config:
        #: Strip citation markers ("[1]") before comparing. On by default:
        #: markers are our own bookkeeping injected into the text, and
        #: penalizing an answer for carrying provenance would be perverse.
        strip_citations: bool = True

    def evaluate(self, outcomes: Sequence[EvalOutcome]) -> MetricReport:
        per_sample: list[dict[str, float]] = []
        for outcome in outcomes:
            reference = outcome.sample.reference_answer
            if not reference or outcome.answer is None:
                per_sample.append({})
                continue
            text = outcome.answer.text
            if self.config.strip_citations:
                text = _CITATION.sub(" ", text)
            per_sample.append(
                {
                    "token_f1": token_f1(text, reference),
                    "exact_match": exact_match(text, reference),
                }
            )

        return MetricReport(
            metrics=self._aggregate(per_sample), per_sample=tuple(per_sample)
        )
