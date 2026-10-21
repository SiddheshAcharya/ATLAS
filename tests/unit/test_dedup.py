"""ids.dedup_papers — one record per canonical id, deterministic merge."""

from __future__ import annotations

from atlas.contracts import Author, PaperMeta, SourceName
from atlas.ids import dedup_papers


def _p(**kw) -> PaperMeta:
    base = dict(paper_id="doi:10.1/x", title="A Paper")
    base.update(kw)
    return PaperMeta(**base)


def test_same_doi_from_two_sources_merges_to_one():
    a = _p(found_via=[SourceName.OPENALEX], abstract="short", citation_count=5)
    b = _p(found_via=[SourceName.PUBMED], abstract="a much longer abstract text", pmid="42")
    (merged,) = dedup_papers([a, b])
    assert merged.found_via == [SourceName.OPENALEX, SourceName.PUBMED]
    assert merged.abstract == "a much longer abstract text"  # longer wins
    assert merged.pmid == "42"  # blank filled from b
    assert merged.citation_count == 5


def test_max_citation_count_wins():
    a = _p(citation_count=3)
    b = _p(citation_count=99)
    assert dedup_papers([a, b])[0].citation_count == 99


def test_more_complete_author_list_wins():
    a = _p(authors=[Author(name="Solo")])
    b = _p(authors=[Author(name="First"), Author(name="Second")])
    assert [x.name for x in dedup_papers([a, b])[0].authors] == ["First", "Second"]


def test_distinct_ids_are_kept_in_first_seen_order():
    out = dedup_papers(
        [_p(paper_id="doi:10.1/c"), _p(paper_id="doi:10.1/a"), _p(paper_id="doi:10.1/c")]
    )
    assert [p.paper_id for p in out] == ["doi:10.1/c", "doi:10.1/a"]
