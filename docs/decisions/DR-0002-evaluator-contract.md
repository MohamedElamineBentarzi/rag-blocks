# DR-0002 — Evaluators score data; they do not run pipelines

**Status:** accepted · **Milestone:** v0.8 (PR 1 of 4) · **Resolves:** a
conflict between AGENTS.md §7.3 and ARCHITECTURE.md §3.9 · **Breaking:** no
(new surface) · **Audience:** maintainer + coding agents

---

## 0. TL;DR

> An `Evaluator` takes **outcomes the pipeline already produced** and returns
> scores:
>
> ```python
> evaluate(self, outcomes: Sequence[EvalOutcome]) -> MetricReport
> ```
>
> It does **not** take a `RagPipeline` and does not run anything. The run loop
> lives once, in the tuner (v0.8 PR 3).

## 1. The conflict

Two committed documents specified different signatures:

| Source | Says |
|---|---|
| ARCHITECTURE.md §3.9 | `def evaluate(self, dataset: EvalDataset, pipeline: RagPipeline) -> MetricReport` |
| AGENTS.md §7.3 | *"`RagasEvaluator`, an Adapter **translating our trial data** (question, retrieved contexts, answer, ground truth) into a RAGAS `EvaluationDataset`"* |

§7.3 describes an evaluator that consumes *data*. §3.9 describes one that
consumes a *pipeline* and drives it. AGENTS.md §7 instructs agents to
implement §7.3 "to the letter" and to flag — not silently fix — code/spec
conflicts, so this was raised with the owner before any code was written.
**Resolution: §7.3 wins; §3.9 is amended.**

## 2. Why data, not a pipeline

Four independent arguments, any one of which would be sufficient:

1. **The run loop would be reimplemented per evaluator.** Every `Evaluator`
   taking a pipeline must iterate the dataset, call `ask()`, and collect
   results. Written once per implementation ⇒ written wrong at least once.
   With outcomes, the loop lives in the tuner, which *already* has to own it
   (it is the thing enumerating combinations).
2. **It inverts the dependency the wrong way.** A late-stage component
   (evaluation) would import and drive an orchestrator (`RagPipeline`), which
   composes every earlier stage. AGENTS.md §2.1 is "contracts, not coupling",
   and the pipeline is a composition root — nothing downstream should depend
   on it. `EvalOutcome` is a contract; `RagPipeline` is a wiring decision.
3. **Testability is the first consumer.** With outcomes, `recall@k` is a pure
   function of two lists, verifiable against arithmetic done by hand in a
   test (`test_ndcg_matches_the_arithmetic_by_hand`). With a pipeline, testing
   the *metric* requires constructing a *pipeline* — the classic sign the seam
   is in the wrong place. The house corollary: "if a change is hard to test,
   the design is wrong."
4. **Two-phase evaluation needs the split anyway.** §7.3 requires screening
   all candidates on IR metrics and running the judge only on the top-N. That
   is only expressible if retrieval outcomes exist as data *before* an
   evaluator is asked to score them — a pipeline-driving evaluator would
   re-run retrieval for every metric family.

The cost: one more contract (`EvalOutcome`) and the tuner grows the loop.
Both are things we wanted regardless.

## 3. What the contract is

```python
@dataclass(frozen=True)
class EvalSample:      # one labeled row of the user's dataset
    question: str
    relevant_chunk_ids: Optional[tuple[str, ...]] = None
    reference_answer: Optional[str] = None
    filters: Optional[dict] = None
    metadata: dict = field(default_factory=dict)

@dataclass(frozen=True)
class EvalOutcome:     # what one pipeline produced for one sample
    sample: EvalSample
    retrieved: tuple[ScoredChunk, ...] = ()
    answer: Optional[Answer] = None

@dataclass(frozen=True)
class MetricReport:
    metrics: dict[str, float]
    per_sample: tuple[dict[str, float], ...] = ()

class Evaluator(Component):
    kind = "evaluator"
    stage: ClassVar[Literal["retrieval", "generation"]]
    def evaluate(self, outcomes: Sequence[EvalOutcome]) -> MetricReport: ...
```

Decisions inside the decision:

- **Frozen value objects.** A dataset row is an input fact read by every trial
  in a run; a mutation halfway through would silently invalidate every
  comparison already made (`Source`/`PageSpan` precedent).
- **`answer=None` is a normal state**, not an error: it is exactly what phase 1
  of a two-phase run produces.
- **`stage` is a `ClassVar`, not a config field.** It states what an evaluator
  *measures*, so it cannot vary per instance; the tuner reads it to decide
  what runs in phase 1 vs. phase 2. It is deliberately absent from
  `describe()["config"]`.
- **`stage` splits by cost, not by taxonomy.** "retrieval" = free, "generation"
  = may cost cents per sample. That is the only distinction the tuner needs.
- **`EvalSample`/`EvalOutcome` live in `evaluation/`, not `core/contracts.py`**
  (AGENTS.md §12: core only if *every* stage needs it — ingestion has no
  business knowing what a label is).

## 4. Honest absence: unlabeled samples are skipped, never zeroed

The rule, implemented once in `Evaluator._aggregate` so it cannot drift per
metric: **a sample an evaluator could not score contributes to no average**,
and its `per_sample` entry is `{}`.

Zeroing would be a lie with a specific shape: `0.0` reads as *"the pipeline
failed this question"* when the truth is *"we never asked"* — and it would
drag every aggregate toward zero in proportion to how incompletely a dataset
is labeled. Same family as `Page.ocr_applied` (never claim OCR we can't
prove) and `Chunk.page_start=None` (means "not applicable", not "page 0").

The consequence is documented rather than hidden: aggregates are means over
the **labeled subset**, so two labeled rows out of thirty produce a
confident-looking number computed from two rows. `per_sample` is what makes
that visible, and it is why the field exists.

Preconditions are enforced as errors, not scores: `recall_at_k(retrieved, [],
k)` raises `ValueError` rather than returning `0.0`, because recall over an
empty ground truth is `0/0`. Callers filter first.

## 5. Binary relevance for nDCG

`EvalSample.relevant_chunk_ids` is a **set**, not a grade map, so nDCG uses
gain 1 for a hit and 0 otherwise. Graded relevance (the classic 0–3 TREC
scale) would need a contract change and a dataset format that carries grades.
Synthesizing grades from a set — e.g. "the first listed id is more relevant" —
would be inventing labels the user never provided. If graded relevance is ever
wanted, it arrives as a new optional field, and the metric branches on its
presence.

## 6. Two implementations per stage, and one of them must be free

AGENTS.md §11 requires ≥ 2 interchangeable implementations per seam. For
`stage="generation"` they are `AnswerMatchEvaluator` (token-F1 + exact match,
pure string math) and `RagasEvaluator` (LLM judge, v0.8 PR 4).

`AnswerMatchEvaluator` is not filler. It is the reason the hermetic suite and
the tuner can score generation with **no key, no network, no vendor** — the
same argument that justifies `MemoryVectorStore` and `HashingEmbedder`. It is
also a deterministic floor to sanity-check a judge against. Its limits are
stated in its own docstring rather than implied: token overlap cannot see
faithfulness and punishes correct paraphrases. Two implementations, genuinely
different trade-offs, and `fingerprint()` records which one produced a number.

## 7. Rejected alternatives

- **`evaluate(dataset, pipeline)`** (ARCHITECTURE.md §3.9 as written) — §2.
- **An `EvalDataset` component/kind.** A list of `EvalSample` is a list. A
  kind would need a registry slot, a fingerprint, and a loader, to wrap
  `list`. Loading a dataset from JSONL is a function; it does not need a
  taxonomy entry. (`SearchSpace` is likewise plain data — PR 3.)
- **Metrics as `Evaluator` subclasses** (`RecallEvaluator`, `NdcgEvaluator`,
  …). Inheritance-for-configuration, explicitly forbidden (§5). Cut-offs are
  config (`k_values`); one `RetrievalEvaluator` reports the family.
- **A `metrics=[...]` config selecting which to compute.** They cost
  microseconds and share the same scan; making it configurable would add a
  fingerprint dimension that changes nothing but the output keys.
- **Asserting metrics land in [0, 1]** in the contract check. Metrics are free
  to use any scale; the leaderboard needs only "higher is better" and a finite
  number. Finiteness *is* asserted — a NaN poisons every average and sort
  downstream of it.

## 8. Consequences

- ARCHITECTURE.md §3.9 is amended to the new signature, with a pointer here.
- The tuner (PR 3) owns the run loop, the pipeline, the cache, and cost
  attribution. Its `run()` is a Template Method; `iter_candidates()` is the
  only strategy decision. That is specified in DR-0003.
- `RagasEvaluator` (PR 4) is a pure translator: `EvalOutcome` → RAGAS
  `EvaluationDataset` → `MetricReport`. No pipeline-driving code.
- The evaluator contract check asserts scoring is **pure** (same outcomes,
  same report). A judged evaluator satisfies this through its verdict cache —
  which §7.3 requires anyway, keyed by (question, answer, judge-model).
