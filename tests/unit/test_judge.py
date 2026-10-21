"""Job C — relation judging: verdict -> Relation, budgets, resilience."""

from __future__ import annotations

from atlas.contracts import Claim, ClaimScope, PaperMeta
from atlas.judge.pairing import Pair
from atlas.judge.relations import RelationVerdict, _scope_str, contradiction_count, judge_pairs


def _claim(cid: str, pid: str) -> Claim:
    return Claim(claim_id=cid, paper_id=pid, section="results", text=f"claim {cid}",
                 quote=f"verbatim {cid}", scope=ClaimScope(what_was_tested="latency"))


def _pair(a_id: str, b_id: str) -> Pair:
    return Pair(
        a=_claim(a_id, "doi:A"),
        b={"claim_id": b_id, "paper_id": "doi:B", "text": "claim B", "quote": "q B",
           "scope": {"what_was_tested": "latency"}, "year": 2020},
        similarity=0.7,
    )


class _Res:
    def __init__(self, value: object, model: str = "test/model") -> None:
        self.value = value

        class M:
            pass

        self.meta = M()
        self.meta.model = model  # type: ignore[attr-defined]


class FakeClient:
    def __init__(self, verdicts: list[RelationVerdict]) -> None:
        from atlas.llm.client import ModelRouting

        self._v = list(verdicts)
        self.calls = 0
        self.routing = ModelRouting(profile="groq")  # judge_pairs reads the prompt file name

    def complete(self, job, *, messages, response_model, **kw):
        self.calls += 1
        return _Res(self._v.pop(0))


def _v(t: str, c: float = 0.9) -> RelationVerdict:
    return RelationVerdict(type=t, confidence=c, rationale="because")


def test_judge_pairs_builds_relations_with_pair_ids():
    client = FakeClient([_v("CONTRADICTS"), _v("DIFF_SCOPE")])
    rels = judge_pairs([_pair("a1", "b1"), _pair("a2", "b2")], client, "run-1",
                       papers={"doi:A": PaperMeta(paper_id="doi:A", title="A", year=2021)})
    assert [r.type for r in rels] == ["CONTRADICTS", "DIFF_SCOPE"]
    assert rels[0].source_claim_id == "a1" and rels[0].target_claim_id == "b1"
    assert rels[0].run_id == "run-1" and rels[0].judged_by == "test/model"
    assert client.calls == 2


def test_max_calls_caps_the_llm_spend():
    client = FakeClient([_v("SUPPORTS")] * 5)
    rels = judge_pairs([_pair(f"a{i}", f"b{i}") for i in range(5)], client, "r", max_calls=2)
    assert client.calls == 2 and len(rels) == 2


def test_a_failed_call_is_skipped_not_fatal():
    class Boom(FakeClient):
        def complete(self, *a, **k):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("429")
            return _Res(_v("UNRELATED"))

    client = Boom([])
    rels = judge_pairs([_pair(f"a{i}", f"b{i}") for i in range(3)], client, "r")
    assert client.calls == 3
    assert len(rels) == 2  # the middle one failed and was skipped


def test_contradiction_count_respects_confidence_floor():
    rels = judge_pairs([_pair("a1", "b1"), _pair("a2", "b2")],
                       FakeClient([_v("CONTRADICTS", 0.9), _v("CONTRADICTS", 0.4)]), "r")
    assert contradiction_count(rels, min_confidence=0.7) == 1


def test_scope_str_handles_model_and_dict():
    assert "latency" in _scope_str(ClaimScope(what_was_tested="latency"))
    assert "latency" in _scope_str({"what_was_tested": "latency", "method": None})
    assert _scope_str({}) == "(not specified)"


def test_rejudge_matches_old_sheet_rows_to_stored_claims(fresh_db: None):
    """E5 re-measurement: a labelled row from an older export (text + quote, no claim ids)
    is matched back to its stored claims and re-judged; `gold` survives, the old verdict
    moves to `prev_type`, and an unmatchable row is reported, not silently dropped."""
    from atlas.judge.eval import rejudge
    from atlas.store.db import ClaimRow, Paper, session_scope

    with session_scope() as s:
        s.add(Paper(paper_id="doi:10.1/a", title="Paper A", year=2021))
        s.add(Paper(paper_id="doi:10.1/b", title="Paper B", year=2023))
        s.add(ClaimRow(claim_id="ca", paper_id="doi:10.1/a", text="A uses a NodeMCU.",
                       quote="The system uses a NodeMCU", section="methods",
                       scope={"what_was_tested": "hardware"}, verified=True))
        s.add(ClaimRow(claim_id="cb", paper_id="doi:10.1/b", text="B uses an ESP32.",
                       quote="The device is built on an ESP32", section="methods",
                       scope={"what_was_tested": "hardware"}, verified=True))
    row = {"type": "CONTRADICTS", "gold": "DIFF_SCOPE",
           "a_text": "A uses a NodeMCU.", "a_quote": "The system uses a NodeMCU",
           "b_text": "B uses an ESP32.", "b_quote": "The device is built on an ESP32"}
    lost = {**row, "a_quote": "a quote that was never stored"}
    client = FakeClient([_v("DIFF_SCOPE")])

    out, missing = rejudge([row, lost], client)

    assert missing == 1 and client.calls == 1
    assert out[0]["type"] == "DIFF_SCOPE" and out[0]["prev_type"] == "CONTRADICTS"
    assert out[0]["gold"] == "DIFF_SCOPE" and out[0]["a_claim_id"] == "ca"
    assert out[1]["rejudge_error"] == "claim not found"
