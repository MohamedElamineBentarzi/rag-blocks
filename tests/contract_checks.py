"""Reusable invariants every stage implementation must satisfy.

ABCs enforce "the method exists"; mypy enforces "the signature matches";
THIS enforces "the behavior holds". Any new implementation (yours or a
plugin's) calls the matching `assert_<stage>_contract` in its tests and
inherits every guarantee the rest of the pipeline relies on.
"""
from __future__ import annotations

import uuid

import pytest

from rag_toolkit.core.contracts import Source
from rag_toolkit.core.errors import StorageError
from rag_toolkit.ingestion.parsers.base import Parser
from rag_toolkit.storage.base import BlobStore


def assert_parser_contract(parser: Parser, source: Source) -> None:
    # 1. Streaming API yields ordered, 1-based, markdown pages.
    pages = list(parser.iter_pages(source))
    assert pages, "parser yielded no pages for a non-empty source"
    numbers = [p.number for p in pages]
    assert numbers == sorted(numbers), "pages must arrive in reading order"
    assert numbers[0] >= 1, "page numbers are 1-based"
    assert all(isinstance(p.markdown, str) for p in pages)

    # 2. parse() assembles a Document whose provenance spans are sane:
    #    ordered, non-overlapping, within bounds, and counted correctly.
    doc = parser.parse(source)
    assert doc.metadata["page_count"] == len(doc.pages)
    cursor = 0
    for span in doc.pages:
        assert span.start >= cursor, "spans must not overlap"
        assert span.end >= span.start
        cursor = span.end
    assert cursor <= len(doc.markdown)

    # 3. Identity is deterministic — the eval cache depends on it.
    assert parser.fingerprint() == parser.fingerprint()


def assert_blob_store_contract(store: BlobStore) -> None:
    """Every BlobStore (disk, S3, your own) must behave like this.

    Uses a fresh random key so the check is safe to run repeatedly against a
    real, shared backend (the contract has no delete, by design)."""
    key = f"contract-checks/{uuid.uuid4().hex}/original.bin"
    # Binary-safe payloads: full byte range incl. NUL, plus nested-path key.
    payload = bytes(range(256)) + b"\n rag-toolkit blob \x00 body"
    payload2 = b"overwritten \xff\x00 value"

    # 1. Absent key: exists() is a quiet False; get() raises with the key.
    assert store.exists(key) is False
    with pytest.raises(StorageError):
        store.get(key)

    # 2. Round-trip is byte-exact, and exists() flips to True.
    store.put(key, payload)
    assert store.exists(key) is True
    assert store.get(key) == payload

    # 3. put() overwrites in place (idempotent for content-addressed keys).
    store.put(key, payload2)
    assert store.get(key) == payload2

    # 4. Distinct keys are independent.
    other = f"contract-checks/{uuid.uuid4().hex}.bin"
    assert store.exists(other) is False

    # 5. Identity is deterministic.
    assert store.fingerprint() == store.fingerprint()
