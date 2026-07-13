"""RagPipeline: the whole loop end to end, zero dependencies."""
from rag_toolkit.chunking.markdown import MarkdownChunker
from rag_toolkit.core.contracts import Answer, Query, Source
from rag_toolkit.generation.extractive import ExtractiveGenerator
from rag_toolkit.pipeline import RagPipeline

_CORPUS = "# France\nParis is the capital of France.\n\n# Fruit\nBananas are yellow.\n"


def source():
    return Source.from_bytes(_CORPUS.encode(), name="facts.md")


def test_index_then_ask_returns_a_grounded_answer():
    rag = RagPipeline(chunker=MarkdownChunker())
    rag.index(source())

    answer = rag.ask("What is the capital of France?", k=1)
    assert isinstance(answer, Answer)
    assert "Paris" in answer.text
    # The citation resolves back to a real chunk with page provenance.
    assert answer.citations
    assert answer.citations[0].page_start is not None


def test_accepts_a_string_or_query():
    rag = RagPipeline(chunker=MarkdownChunker())
    rag.index(source())
    from_str = rag.ask("capital of France", k=1)
    from_obj = rag.ask(Query(text="capital of France"), k=1)
    assert from_str.text == from_obj.text


def test_ask_before_indexing_is_graceful():
    answer = RagPipeline().ask("anything at all")
    assert isinstance(answer, Answer)
    assert answer.citations == []  # nothing indexed ⇒ no sources


def test_index_populates_the_store():
    rag = RagPipeline(chunker=MarkdownChunker())
    rag.index(source())
    # Two headings ⇒ two chunks upserted into the (default memory) store.
    hits = rag.store.search(rag.embedder.embed_query("fruit"), k=10)
    assert len(hits) == 2


def test_components_are_swappable():
    # A custom generator is used verbatim by the facade.
    class _Fixed(ExtractiveGenerator):
        name = "fixed-gen"

        def _complete(self, query, packed):
            return ("stub answer", {})

    rag = RagPipeline(chunker=MarkdownChunker(), generator=_Fixed())
    rag.index(source())
    assert rag.ask("anything", k=1).text == "stub answer"
