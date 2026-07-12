"""Reusable invariants every Parser implementation must satisfy.

ABCs enforce "the method exists"; mypy enforces "the signature matches";
THIS enforces "the behavior holds". Any new parser (yours or a plugin's)
calls `assert_parser_contract` in its tests and inherits every guarantee
the rest of the pipeline relies on.
"""
from __future__ import annotations

from rag_toolkit.core.contracts import Source
from rag_toolkit.ingestion.parsers.base import Parser


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
