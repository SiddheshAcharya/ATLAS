"""Job B — claim extraction stamps identity and enforces the grounding gate."""

from __future__ import annotations

from atlas.contracts import Claim, ClaimScope, Depth, PaperMeta, ParsedDoc
from atlas.extract import claims as claims_mod
from atlas.ingest.grobid import _assemble

SECTION = (
    "The proposed wearable achieved a mean alert latency of 1.8 seconds across 40 field "
    "trials conducted in urban settings over a two-week period. Battery life exceeded 36 "
    "hours under continuous GPS polling, which is comparable to prior commercial devices. "
    "The gesture classifier reached 94 percent precision on a held-out set of triggers, and "
    "no false alerts were recorded during the daytime trials."
)


def _doc() -> ParsedDoc:
    full, secs = _assemble([("methods", "M", SECTION)])
    return ParsedDoc(
        paper_id="doi:10.1/x", depth=Depth.FULL_TEXT, structure="grobid",
        full_text=full, sections=secs,
    )


class FakeResult:
    def __init__(self, value: object) -> None:
        self.value = value


class FakeClient:
    """Returns one grounded claim + one paraphrased (should be dropped)."""

    def complete(self, job, *, messages, response_model, **kw):
        good = Claim(
            claim_id="tmp", paper_id="tmp", section="tmp",
            text="latency was 1.8s",
            quote="mean alert latency of 1.8 seconds across 40 field trials",
            scope=ClaimScope(what_was_tested="alert latency"),
        )
        bad = Claim(
            claim_id="tmp", paper_id="tmp", section="tmp",
            text="fast alerts",
            quote="the device alerted users in well under two seconds during the study",
            scope=ClaimScope(what_was_tested="alert latency"),
        )
        return FakeResult([good, bad])


def test_extract_stamps_ids_and_drops_ungrounded():
    harvest = claims_mod.extract_claims(_doc(), PaperMeta(paper_id="doi:10.1/x", title="T"),
                                        client=FakeClient())
    assert harvest.n_extracted == 2
    assert harvest.n_dropped == 1
    assert len(harvest.kept) == 1

    c = harvest.kept[0]
    assert c.paper_id == "doi:10.1/x"
    assert c.section == "methods"
    assert c.claim_id not in ("tmp", "")
    assert c.verified and c.verify_method == "exact"


def test_short_sections_are_skipped():
    full, secs = _assemble([("results", "R", "Too short.")])
    doc = ParsedDoc(paper_id="doi:1", depth=Depth.FULL_TEXT, structure="grobid",
                    full_text=full, sections=secs)
    harvest = claims_mod.extract_claims(doc, PaperMeta(paper_id="doi:1", title="T"),
                                        client=FakeClient())
    assert harvest.n_extracted == 0
