"""The invariant tests. If these fail, the project's central claims are false.

Everything else in the test suite is secondary to these.
"""

import pytest
from pydantic import ValidationError

from atlas.contracts import Claim, ClaimScope, GapCandidate, PaperRef
from atlas.extract.grounding import verify
from atlas.ids import canonical_id, is_fallback_id
from atlas.ingest.normalize import normalize_text, strip_page_numbers

SOURCE = (
    "The proposed wearable achieved a mean alert latency of 1.8 seconds across 40 field "
    "trials conducted in urban settings. Battery life exceeded 36 hours under continuous "
    "GPS polling, which is comparable to prior commercial devices."
)


def _claim(quote: str) -> Claim:
    return Claim(
        claim_id="c1",
        paper_id="doi:10.1/x",
        text="restated",
        quote=quote,
        section="results",
        scope=ClaimScope(what_was_tested="alert latency"),
    )


# ── normalization ─────────────────────────────────────────────────────────────

def test_normalize_is_idempotent():
    raw = "The pro-\nposed  de\ufb01nition of \u201csafety\u201d\nis robust.\n\nNext."
    once = normalize_text(raw)
    assert once == normalize_text(once)


def test_normalize_fixes_ligatures_and_hyphenation():
    out = normalize_text("The pro-\nposed de\ufb01nition")
    assert "proposed" in out and "definition" in out


def test_page_number_does_not_land_mid_sentence():
    """E4 claim #18's root cause: a page break mid-sentence left the page number in the
    parsed text ("the last few 5 layers"). Top/bottom page numbers are stripped; numbers
    in the body are not."""
    pages = [
        "Freeze Layers-based methods only fine-tune the last few\n4\n",
        "5\nlayers of FMs inspired by this work [118].\nTable 2\n7\n12 of 30",
    ]
    text = normalize_text("\n\n".join(strip_page_numbers(pages)))
    assert "last few layers" in text.replace("\n\n", " ")
    assert "Table 2 7" in text  # body numbers survive; only "12 of 30" (the last line) went
    assert "12 of 30" not in text

# ── canonical identity (ADR-006) ──────────────────────────────────────────────

def test_same_paper_from_four_sources_collapses_to_one_id():
    ids = {
        canonical_id(doi="https://doi.org/10.1109/ACCESS.2020.1234"),
        canonical_id(doi="10.1109/access.2020.1234", openalex_id="W99"),
        canonical_id(doi="10.1109/ACCESS.2020.1234", s2_corpus_id="55512"),
    }
    assert len(ids) == 1


def test_arxiv_versions_collapse():
    assert canonical_id(arxiv_id="arxiv.org/abs/2301.01234v3") == canonical_id(
        arxiv_id="2301.01234"
    )


def test_title_fallback_is_flagged():
    pid = canonical_id(title="A Smart IoT Safety Band", year=2021, first_author="R. Sharma")
    assert is_fallback_id(pid)


# ── the grounding gate (ADR-007) — the integrity test ─────────────────────────

def test_exact_quote_verifies_and_offsets_round_trip():
    quote = "mean alert latency of 1.8 seconds across 40 field trials"
    out = verify(_claim(quote), SOURCE)
    assert out.verified and out.verify_method == "exact"
    assert normalize_text(SOURCE)[out.quote_char_start : out.quote_char_end] == quote


def test_paraphrase_is_rejected():
    """The failure mode this whole project exists to prevent."""
    out = verify(_claim("the device alerted users in under two seconds during testing"), SOURCE)
    assert not out.verified and out.verify_method == "failed"


def test_fabricated_number_is_rejected():
    out = verify(_claim("mean alert latency of 0.8 seconds across 40 field trials"), SOURCE)
    assert not out.verified


def test_e4_claim_18_inserted_digit_is_rejected():
    """Regression: E4 claim #18 (arxiv:2501.13787). The stored quote carried a "5" that is
    not in the paper's sentence; it came from a PDF page number PyMuPDF left mid-sentence.
    Against the real sentence the quote must fail."""
    src = (
        "Commonly used methods include Freeze Layers [53], BitFit [71], and PASTA [72]. "
        "Freeze Layers-based methods only fine-tune the last few layers of FMs inspired by "
        "this work [118]."
    )
    quote = (
        "Freeze Layers-based methods only fine-tune the last few 5 layers of FMs inspired "
        "by this work [118]."
    )
    assert not verify(_claim(quote), src).verified


def test_fuzzy_path_rejects_two_letter_wording_change():
    """'increased' -> 'decreased' scores ~98 on partial_ratio; it must still fail."""
    src = (
        "Across all three deployments the false alarm rate increased once the accelerometer "
        "threshold was lowered below the manufacturer default setting."
    )
    quote = (
        "Across all three deployments the false alarm rate decreased once the accelerometer "
        "threshold was lowered below the manufacturer default setting."
    )
    assert not verify(_claim(quote), src).verified


def test_fuzzy_path_rejects_inserted_word_from_a_real_run():
    """Found by re-checking every stored fuzzy97 claim (doi:10.1109/jbhi.2025.3631706): the
    quote inserted "set" and the old gate passed it at ~99."""
    src = (
        "If μ is set too low, the regularization term has little effect; conversely, if μ is "
        "too high, local updates become very small, resulting in slow convergence."
    )
    quote = (
        "If μ is set too low, the regularization term has little effect; conversely, if μ is "
        "set too high, local updates become very small, resulting in slow convergence."
    )
    assert not verify(_claim(quote), src).verified


def test_fuzzy_path_forgives_capitalised_start_and_added_full_stop():
    """The harmless differences real quotes carry: a mid-sentence start capitalised, a full
    stop where the sentence continues, a Unicode hyphen (U+2010) for a PDF-dropped one."""
    src = (
        "In the second study we see that the wearable remains usable after six weeks of daily "
        "outdoor wear by every participant, although battery life suffered. The cutting "
        "edge sensors held up in all outdoor trials across the monsoon season."
    )
    capitalised = (
        "We see that the wearable remains usable after six weeks of daily outdoor wear by "
        "every participant."
    )
    hyphen = f"The cutting{chr(0x2010)}edge sensors held up in all outdoor trials across the"
    for quote in (capitalised, hyphen):
        out = verify(_claim(quote), src)
        assert out.verified and out.verify_method == "fuzzy97", quote


def test_fuzzy_path_forgives_omitted_citation_marker_but_not_invented_one():
    """Real sentence from the e2e fixture paper (doi:10.48550/arxiv.2503.01933): the quote
    omitted "[7]". Omitting a reference marker is formatting; inventing one is not."""
    src = (
        "Shakti-250M and Shakti-100M models employ Direct Preference Optimization[7] (DPO) as "
        "a computationally efficient alternative to RLHF[6]. DPO aligns these models with "
        "user preferences while minimizing computational resource demands."
    )
    omitted = (
        "Shakti-250M and Shakti-100M models employ Direct Preference Optimization (DPO) as a "
        "computationally efficient alternative to RLHF."
    )
    invented = omitted.replace("RLHF.", "RLHF[9].")
    assert verify(_claim(omitted), src).verified
    assert not verify(_claim(invented), src).verified


def test_fuzzy_path_rejects_flipped_comparison_and_dropped_sign():
    src = (
        "The association with symptom severity was not significant (p > 0.05) in the "
        "adjusted model, and the slope was -0.3 per decade of age at enrolment."
    )
    flipped = src.replace("p > 0.05", "p < 0.05")
    unsigned = src.replace("-0.3", "0.3")
    assert not verify(_claim(flipped[:150]), src).verified
    assert not verify(_claim(unsigned[60:210]), src).verified


def test_fuzzy_path_tolerates_pdf_spacing_and_hyphen_noise():
    """What the fuzzy path is for: a dropped space or an in-word hyphen from PDF text."""
    src = (
        "This study offers a comprehensive assessment of the literature showing IOT devices "
        "for women's safety, their keycharacteristics, wearable technology, and the fixed-rank "
        "adapters used."
    )
    quote = (
        "their key characteristics, wearable technology, and the fixedrank adapters used"
    )
    out = verify(_claim(quote), src)
    assert out.verified and out.verify_method == "fuzzy97"
    matched = normalize_text(src)[out.quote_char_start : out.quote_char_end]
    assert matched == (
        "their keycharacteristics, wearable technology, and the fixed-rank adapters used"
    )


def test_ligature_variant_still_verifies():
    src = "The proposed de\ufb01nition of latency is strict and applies to every field trial."
    out = verify(_claim("The proposed definition of latency is strict"), src)
    assert out.verified


def test_too_short_quote_rejected():
    assert not verify(_claim("Battery life"), SOURCE).verified


def test_overlong_quote_rejected():
    assert not verify(_claim("x" * 401), SOURCE).verified


# ── the citation rule ─────────────────────────────────────────────────────────

def test_gap_without_bounding_papers_cannot_be_constructed():
    """The rule is enforced in the type system, not only in fusion."""
    with pytest.raises(ValidationError):
        GapCandidate(
            gap_id="g1",
            type="unlinked_concepts",
            statement="X and Y are never connected",
            detector_score=0.9,
            bounding_papers=[],
        )


def test_gap_with_bounding_papers_is_valid():
    g = GapCandidate(
        gap_id="g1",
        type="unlinked_concepts",
        statement="X and Y are never connected",
        detector_score=0.9,
        bounding_papers=[PaperRef(paper_id="doi:10.1/x", title="A", year=2020, role="a_side")],
    )
    assert len(g.bounding_papers) == 1
