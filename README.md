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
pip install "rag-toolkit[minio]"             # + MinIO / S3-compatible storage
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

## Persist raw files

A `BlobStore` is the durable *truth store* for ingested bytes (raw files today,
the parse cache next). Same tiny interface on disk or on any S3-compatible
backend — swap by config, no other code changes:

```python
from rag_toolkit import LocalBlobStore, MinioBlobStore, Source

# On disk (zero-dep default, atomic writes)
store = LocalBlobStore(root="./.rag_cache/blobs")

# ...or any S3-compatible backend (MinIO, AWS S3, R2, B2) — needs [minio].
# Credentials: config wins, else MINIO_ACCESS_KEY / MINIO_SECRET_KEY.
store = MinioBlobStore(endpoint="localhost:9000", bucket="rag-toolkit")

src = Source.from_path("report.pdf")
key = f"raw/{src.content_hash()}/original.pdf"   # content-addressed ⇒ dedup free
if not store.exists(key):                         # cheap pre-check
    store.put(key, src.open().read())
assert store.get(key)[:5] == b"%PDF-"
```

The store treats keys as opaque strings — the content-addressed layout lives in
your pipeline, so the two implementations stay perfectly interchangeable.

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
