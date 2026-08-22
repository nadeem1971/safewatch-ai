"""Tests for section-aware chunking. No Azure required."""

from pathlib import Path

from src.rag.chunking import Chunk, chunk_corpus

CORPUS = Path(__file__).parent.parent / "data" / "regulations" / "sample_corpus.json"


def test_each_clause_becomes_a_citable_chunk() -> None:
    chunks = chunk_corpus(CORPUS)
    assert len(chunks) >= 2
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.regulation
        assert c.clause
        assert c.content
        assert c.violation_types


def test_chunk_carries_metadata_for_citation() -> None:
    # A retrieved chunk must know exactly where it came from.
    chunks = chunk_corpus(CORPUS)
    c = chunks[0]
    assert c.source_uri.startswith("http")
    assert c.id


def test_search_document_shape_matches_index() -> None:
    chunks = chunk_corpus(CORPUS)
    doc = chunks[0].to_search_document([0.0] * 3072)
    assert set(doc.keys()) == {
        "id",
        "regulation",
        "clause",
        "title",
        "content",
        "violation_types",
        "source_uri",
        "contentVector",
    }
    assert len(doc["contentVector"]) == 3072


def test_long_clause_subchunks_inherit_parent_metadata() -> None:
    from src.rag.chunking import _sub_chunk

    long_text = " ".join(f"Sentence number {i} about safety." for i in range(60))
    pieces = _sub_chunk(long_text, target=200, overlap=40)
    assert len(pieces) > 1
    assert all(p.strip() for p in pieces)
