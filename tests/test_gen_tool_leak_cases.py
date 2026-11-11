"""Agent-tool leak cases: rules hold and the committed file is reproducible."""

from collections import Counter

from evals import gen_tool_leak_cases as g
from evals.leak_tools import judge
from evals.schema import load_tool_leak_cases


def test_committed_cases_are_reproducible():
    assert [c.model_dump() for c in g.generate()] == [
        c.model_dump() for c in load_tool_leak_cases(g.OUT)
    ]


def test_every_case_passes_the_rules():
    assert g.check(g.generate()) == []


def test_every_cell_is_covered():
    from fabops.authz.policy import MES_CLEARANCE

    cells = Counter((c.boundary, c.tool) for c in g.generate())
    search = {(b, t) for b in g.BOUNDARIES for t in ("search_sop", "search_similar_incidents")}
    # public MES rows (MES_CLEARANCE = 0) leave no clearance boundary for the MES tools
    mes_boundaries = g.BOUNDARIES if MES_CLEARANCE > 0 else ("cross_fab", "cross_dept")
    assert {(b, t) for b in mes_boundaries for t in g.MES_TOOLS} | search == set(cells)
    assert all(cells[(b, t)] <= g.PER_CELL for b in g.BOUNDARIES for t in g.MES_TOOLS)


def test_judge_flags_ids_and_strings():
    case = load_tool_leak_cases(g.OUT)[0]
    assert judge(case, {"found": False, "message": "查無此資料"}) == []
    assert case.forbidden_strings[0] in judge(case, {"found": True, "x": case.forbidden_strings[0]})
