# The Open-RAG-Bench benchmark

A real-world **retrieval + generation** benchmark built from
[vectara/open_ragbench](https://huggingface.co/datasets/vectara/open_ragbench):
expert queries over a corpus of **full arXiv papers**, with built-in hard
negatives. It is the sibling of `benchmarks/hotpotqa/` — same layout, same
loader, same "generate it locally, never commit it" rule — but a different kind
of retrieval test (see below).

## The data is NOT in the repo — you generate it

This folder ships **only** this README and a `.gitignore`. The corpus and
questions are **not committed**; you produce them locally with `generate.py`,
which downloads Open-RAG-Bench from Hugging Face and writes it into this folder.

Two reasons it is gitignored, not committed:

1. **Licensing.** Open-RAG-Bench is **CC BY-NC 4.0** (non-commercial); this repo
   is Apache-2.0. Vendoring its text into the tree would pull a *non-commercial*
   restriction into an otherwise permissively-licensed project. Keeping the data
   local avoids that entirely.
2. **Size and reproducibility.** It is ≈1000 full papers and fully regenerable
   from one script, so there is nothing to gain from committing it.

## What this benchmark is — and how it differs from HotpotQA

- **It is** a real-world retrieval test over **long, full-document** sources
  (arXiv papers, tens of KB each), with **600 curated hard-negative documents**
  that make retrieval able to be genuinely wrong, plus a reference answer for the
  generation phase.
- **Single gold document per query** (single-hop), unlike HotpotQA's multi-hop
  two-or-more. Recall therefore measures whether the retriever surfaces *the*
  gold paper among ~1000, not a set.
- **Two query axes that actually vary**: `type` (abstractive / extractive) and
  `source` (text / text-image / text-table / text-table-image). `generate.py`
  balances the sample across them.
- **Still clean-ish text.** The source is PDF-extracted arXiv markdown (with
  LaTeX and image/table markers left in place). It exercises retrieval and
  generation over long documents — not scanning/OCR ingestion.

## The data contract (what the generator produces)

Identical to `benchmarks/baseline/` and `benchmarks/hotpotqa/`, so the same
loader shape works (`benchmarks/baseline/run.py::load_corpus` / `load_dataset`):

```
benchmarks/open_ragbench/
├── corpus/                 one markdown file per arXiv paper (slug of its id)
│   ├── 2401-01872v2.md
│   └── ...
├── qa.jsonl                one question per line (schema below)
├── config.json            the grid (baseline/config.json's shape, real embedder)
└── ATTRIBUTION.md          CC BY-NC 4.0 notice
```

### `corpus/*.md`

One paper per file. **The filename is the label key** — `qa.jsonl` refers to
documents by filename, and the runner resolves each to a real `doc_id` (content
hash) at load time. Body is `# {title}` then the paper's extracted sections
joined into prose. Filenames are slugs of the arXiv id (`2401.01872v2` →
`2401-01872v2.md`).

### `qa.jsonl`

```json
{"question": "...", "relevant_docs": ["2401-01872v2.md"], "reference_answer": "..."}
```

| Field | Meaning |
|---|---|
| `question` | The Open-RAG-Bench query, verbatim. |
| `relevant_docs` | The **one** gold document's filename (from `qrels`). Every filename here MUST exist in `corpus/`. |
| `reference_answer` | Open-RAG-Bench's answer for the query. |

Ground truth is **document-level** (never chunk-level) — same reasoning as the
baseline: a chunk id denotes a different passage under a different chunker, so
chunk-level labels would make chunk size the one knob you cannot tune. The
`qrels` also carry a `section_id`, which is deliberately **dropped**: the label
is the document.

## Generating it

```
pip install datasets huggingface_hub
python benchmarks/open_ragbench/generate.py
```

It loads `vectara/open_ragbench` (the `pdf/arxiv` subset), samples a subset of
queries (balanced across `type` × `source`, seeded), downloads the full curated
corpus, and writes `corpus/`, `qa.jsonl`, `config.json`, and `ATTRIBUTION.md`.
Deterministic given the seed.

## Running it

Reuse the runner's structure — `load_corpus` / `load_dataset` already expect this
format. `run.py` here is modelled on `benchmarks/baseline/run.py`, swapping in a
real embedder (and, for the generation phase, an injected RAGAS judge). This
benchmark is **not** hermetic and does not run in CI.

## Licensing

The generated corpus is derived from **Open-RAG-Bench**, licensed **CC BY-NC
4.0**. `generate.py` writes an `ATTRIBUTION.md` next to the data recording the
source, license, and a link. The **non-commercial** term travels with the data;
none of it affects the Apache-2.0 license of the `rag-blocks` code itself.
