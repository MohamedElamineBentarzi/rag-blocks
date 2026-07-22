# The HotpotQA benchmark

A larger, real-world **retrieval + generation** benchmark built from
[HotpotQA](https://huggingface.co/datasets/hotpotqa/hotpot_qa). Where
`benchmarks/baseline/` is a tiny hermetic regression detector that runs in CI
forever, this one is a richer, human-labelled evaluation you run by hand with a
real embedder and (optionally) an LLM judge.

## The data is NOT in the repo — you generate it

This folder ships **only** this README and a `.gitignore`. The corpus and
questions are **not committed**. You produce them locally by running the prompt
in `tump_docs/hotpotqa-generation-prompt.md`, which downloads HotpotQA from
Hugging Face and writes it into this folder in the format documented below.

Two reasons it is gitignored, not committed:

1. **Licensing.** HotpotQA is **CC BY-SA 4.0**; this repo is Apache-2.0.
   Vendoring its Wikipedia text into the tree would pull share-alike and
   attribution obligations into an otherwise cleanly-licensed project. Keeping
   the data local avoids that entirely.
2. **Size and reproducibility.** It is large and fully regenerable from one
   prompt, so there is nothing to gain from committing it.

## What this benchmark is — and is not

- **It is** a real-world retrieval test: human-written multi-hop questions with
  human-annotated supporting documents, plus a short reference answer for the
  generation phase.
- **It is not** a public leaderboard, and it is not a substitute for the
  baseline. Keep the two separate — they use *different* labelling conventions
  (see below).
- **It does not touch ingestion.** HotpotQA is clean Wikipedia prose: no scans,
  no tables, no OCR. It exercises retrieval and generation only. To stress the
  parsing / OCR / provenance side (the streaming-ingestion differentiator), use
  a messy-document benchmark instead.

## The data contract (what the generator must produce)

The layout mirrors `benchmarks/baseline/` on purpose, so the same loader shape
works (`benchmarks/baseline/run.py::load_corpus` / `load_dataset`):

```
benchmarks/hotpotqa/
├── corpus/                 one markdown file per document
│   ├── scott-derrickson.md
│   ├── ed-wood.md
│   └── ...
├── qa.jsonl                one question per line (schema below)
├── config.json            the grid (copy baseline/config.json's shape)
└── ATTRIBUTION.md          CC BY-SA 4.0 notice (see "Licensing")
```

### `corpus/*.md`

One document per file. **The filename is the label key** — `qa.jsonl` refers to
documents by filename, and the runner resolves each filename to a real `doc_id`
(content hash) at load time. Never put content hashes in `qa.jsonl`; they rot
the first time the corpus is edited.

Each file is one HotpotQA context paragraph:

```markdown
# Scott Derrickson

Scott Derrickson (born July 16, 1966) is an American director... (the
paragraph's sentences, joined into prose).
```

Filenames are slugs of the Wikipedia title (lowercase, spaces → hyphens,
punctuation stripped), e.g. `Scott Derrickson` → `scott-derrickson.md`. On a
slug collision between two different titles, append a short disambiguating
suffix.

### `qa.jsonl`

One JSON object per line:

```json
{"question": "...", "relevant_docs": ["scott-derrickson.md", "ed-wood.md"], "reference_answer": "yes"}
```

| Field | Meaning |
|---|---|
| `question` | The HotpotQA question, verbatim. |
| `relevant_docs` | Filenames under `corpus/` of the **gold supporting documents** — HotpotQA's `supporting_facts` titles. Multi-hop questions have **two or more**. Every filename here MUST exist in `corpus/`. |
| `reference_answer` | HotpotQA's `answer` (may be a short span, or `"yes"` / `"no"`). |

### `config.json`

Copy the shape of `benchmarks/baseline/config.json`. Point `corpus` at
`"corpus"` and `dataset` at `"qa.jsonl"`. Because you will run this with a real
embedder rather than `hashing`, set the `embedder` axis accordingly.

## How it is labelled, and why (read before scoring)

Ground truth is **document-level** (`relevant_docs` → `relevant_doc_ids`), never
chunk-level — same reasoning as the baseline: a chunk id (`{doc_id}:{index}`)
denotes a *different passage* under a different chunker, so chunk-level labels
would make chunk size the one knob you cannot tune. HotpotQA's
`supporting_facts` give you the gold document titles directly, so document-level
labels come for free — no LLM, no synthesis, no manual cull.

**The multi-hop difference from baseline.** Baseline questions are answerable
from exactly one document; HotpotQA questions need **two or more**. That changes
what recall measures — the retriever must surface *all* the gold documents, not
just one. This is a legitimately richer test, but it is a **different
convention**. Do not merge these questions into `baseline/qa.jsonl`; keep the
two benchmarks apart.

## Generating it

Open `tump_docs/hotpotqa-generation-prompt.md` and follow it (paste it to a
coding agent, or use it as a spec to write the script yourself). It loads
`hotpotqa/hotpot_qa` (`distractor` config, `validation` split), samples a
subset, builds the shared corpus, and writes `corpus/`, `qa.jsonl`,
`config.json`, and `ATTRIBUTION.md` into this folder.

## Running it

Reuse the baseline runner's structure — its `load_corpus` / `load_dataset`
already expect this exact format. The generation prompt writes a `run.py` here
modelled on `benchmarks/baseline/run.py`, swapping in a real embedder (and,
for the generation phase, an injected RAGAS judge — see
`rag_blocks/evaluation/ragas_evaluator.py`). This benchmark is **not** hermetic
and does not run in CI.

## Licensing

The generated corpus is derived from **HotpotQA**, licensed **CC BY-SA 4.0**.
The generator writes an `ATTRIBUTION.md` next to the data recording the source,
license, and a link. If you ever redistribute the generated data (you normally
won't — it is gitignored), CC BY-SA's attribution **and share-alike** terms
apply to it. None of this affects the Apache-2.0 license of the `rag-blocks`
code itself.
