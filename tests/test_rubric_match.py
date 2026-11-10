from evals.rubric_match import match_points, point_needles, verdict

RUBRIC = (
    "要點：(1) 先確認該腔體是否在保養中，並暫停該腔體派貨；(2) 等待 5 分鐘後重新量測；"
    "(3) 連續 2 次超出上限就 hold 受影響批號並通知模組經理；"
    "(4) 執行月保養後以 3 片監控晶圓驗證才可復機；(5) 超過 4 小時未排除升級至模組經理。"
    "每漏一個要點扣分。"
)


def test_needles_per_template():
    assert point_needles("先確認該腔體是否在保養中，並暫停該腔體派貨") == ["保養中", "暫停"]
    assert point_needles("等待 5 分鐘後重新量測") == ["5 分鐘"]
    assert point_needles("連續 2 次超出上限就 hold 受影響批號並通知模組經理") == [
        "2 次",
        "模組經理",
    ]
    assert point_needles("執行腔體濕式清潔後以 1 片監控晶圓驗證才可復機") == [
        "腔體濕式清潔",
        "1 片",
    ]
    assert point_needles("超過 4 小時未排除升級至模組經理") == ["4 小時"]


def test_full_steps_pass_and_summary_sentence_fails():
    full = (
        "1. 確認腔體是否在保養中，暫停派貨。2. 等待5分鐘後重新量測。"
        "3. 連續2次超出上限，hold 批號並通知模組經理。4. 執行月保養後以3片監控晶圓驗證。"
        "5. 超過4小時未排除升級。"
    )
    assert match_points(full, RUBRIC, {}) == ["有"] * 5
    summary = "依 SOP 處置：確認異常後等待重測，再次確認仍超出上限，執行月PM後以監控晶圓驗證。"
    assert match_points(summary, RUBRIC, {}) == ["漏"] * 5


def test_numbers_need_boundaries_and_refusal_scores_nothing():
    assert match_points("等待15分鐘後重新量測", RUBRIC, {})[1] == "漏"
    assert match_points("等待5分鐘", RUBRIC, {}, refused=True) == ["漏"] * 5


def test_verdict():
    assert verdict(["有"] * 5) == "對"
    assert verdict(["漏"] * 5) == "錯"
    assert verdict(["有", "漏"]) == "部分"
