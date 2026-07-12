# rag-toolkit

Composable building blocks for production RAG pipelines — every stage is a
swappable component, every pipeline is a serializable config, and an
auto-tuning evaluation suite finds the best combination for *your* dataset
with full trial logs.

**Status: v0.1 — ingestion subsystem.** Any file in → clean markdown out,
with per-page OCR routing (Mistral, Google Document AI, or your own engine)
and streaming that keeps memory flat on 2 000-page PDFs.

## Install

```bash
pip install "rag-toolkit[docling]"           # local parsing (default route)
pip install "rag-toolkit[docling,mistral]"   # + Mistral OCR
```

The core has **zero dependencies**; vendor SDKs are optional extras.

## Quick start

```python
import rag_toolkit as rk

# One call: any file → markdown Document with page provenance
doc = rk.ingest("report.pdf")
print(doc.markdown[:500])
print(doc.pages_for_span(1200, 1800))   # -> which pages a char range came from

# Scanned document through cloud OCR (needs MISTRAL_API_KEY)
doc = rk.ingest("scan.pdf", ocr_engine="mistral", ocr_policy=rk.OcrPolicy.FORCE)

# Streaming — memory stays O(page batch) on huge files
parser = rk.AutoParser()
for page in parser.iter_pages(rk.Source.from_path("huge.pdf")):
    process(page.markdown)
```

## Bring your own OCR

```python
from dataclasses import dataclass
from rag_toolkit import registry
from rag_toolkit.ingestion.ocr.base import OcrEngine, OcrResult, PageImage

@registry.register
class MyOcrEngine(OcrEngine):
    name = "my-ocr"

    @dataclass
    class Config:
        endpoint: str = "http://localhost:9000"

    def recognize(self, image: PageImage) -> OcrResult:
        markdown = my_model(image.data)          # your logic here
        return OcrResult(markdown=markdown)

doc = rk.ingest("scan.pdf", ocr_engine="my-ocr")   # that's it
```

## Design

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline map, the data
contracts, the pattern-by-pattern rationale, and the design of the evaluation
and auto-tuning suite.

## Development

```bash
pip install -e ".[dev]"
pytest                      # fast, hermetic suite — no vendor deps needed
pytest -m integration       # opt-in: real docling/OCR runs
ruff check . && mypy rag_toolkit
```

Tests mirror the package layout. `tests/contract_checks.py` holds the
behavioral contract every new `Parser` must pass — call
`assert_parser_contract(...)` from your parser's tests and you inherit the
guarantees the rest of the pipeline relies on.
