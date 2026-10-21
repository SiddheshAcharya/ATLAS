"""Concept/method/dataset/limitation/future-work extraction + normalization (R4)."""

from __future__ import annotations

from atlas.extract.concepts import extract_from_sections, extract_phrases, normalize_phrases

GROBID_SECTIONS = {
    "abstract": "A wearable IoT device for women safety using GPS tracking and a panic button.",
    "methods": (
        "The system uses a NodeMCU microcontroller connected to a GPS module. "
        "We evaluate the prototype on a field trial with 40 participants over two weeks. "
        "The benchmark dataset used for gesture classification is the WISDM activity dataset."
    ),
    "results": "The device achieved a mean alert latency of 1.8 seconds across the field trial.",
    "limitations": (
        "However, the small sample size of 40 participants is a limitation of this study. "
        "Further validation across rural settings is required."
    ),
    "future_work": (
        "In future work, we plan to integrate fall detection as a secondary trigger. "
        "We also intend to evaluate the device on a larger deployment."
    ),
}

FLAT_TEXT = (
    "The proposed wearable device integrates GPS tracking and a panic button. "
    "However, the small sample size is a limitation of this work. "
    "In future work, we plan to extend the evaluation to a larger cohort."
)


def test_extract_phrases_finds_multi_word_candidates():
    phrases = extract_phrases(GROBID_SECTIONS["methods"], top_n=10)
    assert phrases
    assert any("gps" in p or "nodemcu" in p or "participants" in p for p in phrases)
    # every candidate is a clean 1-5 word phrase, no leading article
    for p in phrases:
        assert not p.startswith(("a ", "an ", "the "))
        assert 1 <= len(p.split()) <= 5


def test_grobid_structure_scopes_methods_datasets_limitations_future():
    ep = extract_from_sections("doi:1", GROBID_SECTIONS, structure="grobid")
    assert ep.concepts
    assert ep.methods  # from the methods section only
    assert ep.limitation_sentences and "small sample size" in ep.limitation_sentences[0]
    assert ep.future_work_sentences and "future work" in ep.future_work_sentences[0].lower()


def test_flat_structure_skips_methods_but_still_finds_cue_sentences():
    ep = extract_from_sections("doi:2", {"other": FLAT_TEXT}, structure="flat")
    assert ep.concepts
    assert ep.methods == []  # no section boundary to scope it to — not guessed
    assert ep.datasets == []
    assert ep.limitation_sentences
    assert ep.future_work_sentences


def test_extract_from_sections_skips_empty_text():
    ep = extract_from_sections("doi:3", {"abstract": ""}, structure="none")
    assert ep.concepts == []
    assert ep.limitation_sentences == []


# ── normalization ────────────────────────────────────────────────────────────


def test_alias_file_maps_known_variants_to_the_same_canonical_label():
    occ = ["iot devices", "iot device", "internet-of-things device", "IoT-based device"]
    mapping = normalize_phrases(occ)
    assert len({mapping[o] for o in occ}) == 1
    assert next(iter(mapping.values())) == "iot device"


def test_clustering_groups_near_duplicates_not_in_the_alias_file():
    # not in config/concept_aliases.yaml, but near-identical in meaning/embedding
    occ = ["fall detection sensor", "fall detection sensor", "fall-detection sensors"]
    mapping = normalize_phrases(occ)
    assert len(set(mapping.values())) == 1
    # canonical = most frequent surface form
    assert mapping["fall detection sensor"] == "fall detection sensor"


def test_distinct_concepts_stay_distinct():
    occ = ["gps tracker", "panic button"]
    mapping = normalize_phrases(occ)
    assert mapping["gps tracker"] != mapping["panic button"]


def test_normalize_empty_input():
    assert normalize_phrases([]) == {}
