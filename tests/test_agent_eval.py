"""Agent scenarios: reproducible generation, and the scoring rules of evals/agent_eval.py."""

from evals import gen_agent_scenarios as g
from evals.agent_eval import Observed, score_scenario
from evals.schema import AgentScenario, ExpectedProposal, load_agent_scenarios


def test_committed_scenarios_are_reproducible():
    dev, test = g.generate()
    assert [s.model_dump() for s in dev] == [
        s.model_dump() for s in load_agent_scenarios([g.DIR / "dev" / "scenarios.jsonl"])
    ]
    assert len(test) == len(load_agent_scenarios([g.DIR / "test" / "scenarios.jsonl"]))
    assert g.check(dev + test) == []
    assert 20 <= len(dev) + len(test) <= 30
    assert not {s.sid for s in dev} & {s.sid for s in test}


S = AgentScenario(
    sid="A-9999",
    category="multi_step",
    question="FX1-ETCHER-02-CHA 發生 ETC-PRS-0412，請處理。",
    user_id="eng_fx1_etch",
    expected_tools=["get_equipment_status", "search_sop"],
    expected_facts=[["暫停", "停止派貨"]],
    expected_proposal=ExpectedProposal(action="inhibit_chamber", target_id="FX1-ETCHER-02-CHA"),
)


def obs(answer, proposal=None, tools=("get_equipment_status", "search_sop"), seen=""):
    calls = [{"tool": t, "ok": True} for t in tools]
    return Observed(answer, [], False, proposal, calls, seen, len(calls), {}, "done")


def test_success_needs_facts_proposal_and_tools():
    good = {"action": "inhibit_chamber", "target_id": "FX1-ETCHER-02-CHA"}
    r = score_scenario(S, obs("建議暫停該腔體派貨。", good), "agent", 1.0)
    assert r.success and r.tools_ok and r.ungrounded_ids == []
    wrong = {"action": "hold_lot", "target_id": "FX1L00001"}
    assert not score_scenario(S, obs("建議暫停", wrong), "agent", 1.0).success
    assert not score_scenario(S, obs("建議暫停"), "agent", 1.0).success  # no proposal
    assert (
        score_scenario(S, obs("建議暫停", good, tools=["search_sop"]), "agent", 1).tools_ok is False
    )


def test_ungrounded_ids_are_counted():
    good = {"action": "inhibit_chamber", "target_id": "FX1-ETCHER-02-CHA"}
    r = score_scenario(S, obs("暫停，並 hold FX1L00042。", good), "agent", 1.0)
    assert r.ungrounded_ids == ["FX1L00042"]
    r = score_scenario(S, obs("暫停，並 hold FX1L00042。", good, seen='"FX1L00042"'), "agent", 1)
    assert r.ungrounded_ids == []


def test_refusal_expectation():
    s = S.model_copy(
        update={"expected_proposal": None, "expected_facts": [], "expect_refusal": True}
    )
    assert score_scenario(s, obs("查無資料，無法回答。"), "agent", 1.0).success
    assert not score_scenario(s, obs("可以派貨。"), "agent", 1.0).success
