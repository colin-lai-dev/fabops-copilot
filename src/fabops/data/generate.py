"""Rule-based synthetic data generator (ADR-0004, skeleton + render stages).

Produces, deterministically from a fixed seed:
- MES tables (equipment, chambers, lots, dispatch_log, alarms, maintenance, users)
- documents (SOPs with old/new versions, incident reports) rendered from templates
- a facts file: the ground truth used later by evals (never shown to the model)

Run: `python -m fabops.data.generate`
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fabops.data import world

SEED = 20261108
TZ = timezone(timedelta(hours=8))
START = datetime(2026, 9, 1, tzinfo=TZ)
DAYS = 21
OUT_DIR = Path("data/generated")

ROOT_CAUSES = {
    "etch": ["O-ring 老化導致微漏", "RF 匹配器電容劣化", "壓力計校正偏移", "靜電吸盤表面污染"],
    "litho": ["鏡組冷卻水溫控不穩", "對準標記辨識失敗", "載台干涉儀讀值漂移"],
    "thinfilm": ["MFC 流量漂移", "噴淋頭局部堵塞", "腔壁沉積物剝落"],
    "diffusion": ["加熱器區段老化", "熱電偶接點鬆脫", "排氣壓力不穩"],
    "cmp": ["研磨墊磨耗不均", "研磨液管路結晶", "修整器鑽石盤磨損"],
}
NOTIFY_ROLES = ["設備工程師", "製程工程師", "值班主任", "模組經理"]


@dataclass
class Doc:
    doc_id: str
    doc_type: str
    title: str
    fab: str
    department: str
    clearance: int
    effective_date: str
    body_md: str
    sop_key: str | None = None
    version: int = 1
    superseded_by: str | None = None
    source: str = "template"
    facts: dict = field(default_factory=dict)
    dirty_tags: list[str] = field(default_factory=list)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------- MES tables


def gen_mes(rng: random.Random) -> dict[str, list[dict]]:
    users = [
        {"user_id": u, "display_name": n, "fabs": f, "departments": d, "clearance": c}
        for u, n, f, d, c in world.DEMO_USERS
    ]

    equipment, chambers = [], []
    for fab in world.FABS:
        for dept, (etype, models) in world.EQUIPMENT_TYPES.items():
            for n in range(1, 4):
                eq_id = f"{fab}-{etype}-{n:02d}"
                equipment.append(
                    {
                        "equipment_id": eq_id,
                        "fab": fab,
                        "department": dept,
                        "equipment_type": etype,
                        "vendor_model": rng.choice(models),
                        "status": "up",
                    }
                )
                for c in "ABCD"[: rng.randint(2, 4)]:
                    chambers.append(
                        {"chamber_id": f"{eq_id}-CH{c}", "equipment_id": eq_id, "status": "up"}
                    )

    eq_by_id = {e["equipment_id"]: e for e in equipment}
    end = START + timedelta(days=DAYS)

    maintenance, pm_windows = [], {}
    for ch in chambers:
        for _ in range(rng.randint(1, 2)):
            s = START + timedelta(hours=rng.randint(0, DAYS * 24 - 12))
            e = s + timedelta(hours=rng.randint(2, 8))
            maintenance.append(
                {
                    "maintenance_id": len(maintenance) + 1,
                    "fab": eq_by_id[ch["equipment_id"]]["fab"],
                    "equipment_id": ch["equipment_id"],
                    "chamber_id": ch["chamber_id"],
                    "pm_type": rng.choice(world.PM_TYPES),
                    "start_at": _iso(s),
                    "end_at": _iso(e),
                }
            )
            pm_windows.setdefault(ch["chamber_id"], []).append((s, e))

    # One chamber per fab is in PM at the end of the period, so "current status" questions
    # have an interesting answer.
    for fab in world.FABS:
        ch = rng.choice([c for c in chambers if c["equipment_id"].startswith(fab)])
        s, e = end - timedelta(hours=3), end + timedelta(hours=5)
        maintenance.append(
            {
                "maintenance_id": len(maintenance) + 1,
                "fab": fab,
                "equipment_id": ch["equipment_id"],
                "chamber_id": ch["chamber_id"],
                "pm_type": "腔體濕式清潔",
                "start_at": _iso(s),
                "end_at": _iso(e),
            }
        )
        pm_windows.setdefault(ch["chamber_id"], []).append((s, e))
        ch["status"] = "pm"

    lots = []
    for fab in world.FABS:
        for n in range(1, 76):
            lots.append(
                {
                    "lot_id": f"{fab}L{n:05d}",
                    "fab": fab,
                    "product": rng.choice(world.PRODUCTS),
                    "route_step": rng.choice(world.ROUTE_STEPS),
                    "priority": rng.choices([1, 2, 3], weights=[1, 3, 6])[0],
                    "status": rng.choices(["wait", "run", "hold", "done"], [4, 3, 1, 2])[0],
                }
            )
    lots_by_fab = {f: [lot for lot in lots if lot["fab"] == f] for f in world.FABS}

    def in_pm(chamber_id: str, t: datetime) -> bool:
        return any(s <= t < e for s, e in pm_windows.get(chamber_id, []))

    # Business rule: a chamber under PM must not receive lots -> dispatch is rejected.
    dispatch, last_lot = [], {}
    for ch in chambers:
        fab = eq_by_id[ch["equipment_id"]]["fab"]
        t = START
        while t < end:
            t += timedelta(minutes=rng.randint(180, 420))
            if t >= end:
                break
            lot = rng.choice(lots_by_fab[fab])
            if in_pm(ch["chamber_id"], t):
                result = "rejected"
            else:
                result = "aborted" if rng.random() < 0.02 else "ok"
            dispatch.append(
                {
                    "dispatch_id": len(dispatch) + 1,
                    "fab": fab,
                    "lot_id": lot["lot_id"],
                    "equipment_id": ch["equipment_id"],
                    "chamber_id": ch["chamber_id"],
                    "dispatched_at": _iso(t),
                    "result": result,
                }
            )
            if result == "ok":
                last_lot[(ch["chamber_id"], t)] = lot["lot_id"]

    alarms = []
    alarm_types_by_dept = {}
    for a in world.ALARM_TYPES:
        alarm_types_by_dept.setdefault(a.department, []).append(a)
    for _ in range(400):
        ch = rng.choice(chambers)
        eq = eq_by_id[ch["equipment_id"]]
        at = rng.choice(alarm_types_by_dept[eq["department"]])
        t = START + timedelta(minutes=rng.randint(0, DAYS * 24 * 60 - 1))
        value = round(at.limit_high * rng.uniform(1.05, 1.6), 1)
        recent = [
            lot
            for (cid, dt), lot in last_lot.items()
            if cid == ch["chamber_id"] and t - timedelta(hours=8) <= dt <= t
        ]
        alarms.append(
            {
                "alarm_id": len(alarms) + 1,
                "fab": eq["fab"],
                "equipment_id": eq["equipment_id"],
                "chamber_id": ch["chamber_id"],
                "alarm_code": at.code,
                "severity": at.severity,
                "message": f"{at.name}: {at.parameter} = {value} {at.unit} (limit {at.limit_high})",
                "occurred_at": _iso(t),
                "lot_id": recent[-1] if recent else None,
                "_value": value,
            }
        )
    alarms.sort(key=lambda a: a["occurred_at"])
    for i, a in enumerate(alarms, 1):
        a["alarm_id"] = i

    for eq in equipment:
        if any(c["status"] == "pm" for c in chambers if c["equipment_id"] == eq["equipment_id"]):
            eq["status"] = "pm"

    return {
        "users": users,
        "equipment": equipment,
        "chambers": chambers,
        "lots": lots,
        "dispatch_log": dispatch,
        "alarms": alarms,
        "maintenance": maintenance,
    }


# ---------------------------------------------------------------- SOPs


def _sop_params(rng: random.Random, at: world.AlarmType) -> dict:
    return {
        "limit_low": at.limit_low,
        "limit_high": at.limit_high,
        "wait_min": rng.choice([5, 10, 15, 20, 30]),
        "consecutive": rng.choice([2, 3]),
        "notify_role": rng.choice(NOTIFY_ROLES),
        "pm_type": rng.choice(world.PM_TYPES),
        "escalate_hours": rng.choice([2, 4, 8]),
        "monitor_wafers": rng.choice([1, 2, 3]),
    }


def _render_sop(
    at: world.AlarmType, fab: str, version: int, eff: str, p: dict, clearance: int, html_rev: bool
) -> str:
    dept_zh = world.DEPARTMENTS[at.department]
    etype = world.EQUIPMENT_TYPES[at.department][0]
    lines = [
        f"# SOP {at.code}：{at.name}處置程序（{fab}，第 {version} 版）",
        "",
        "## 1. 目的",
        f"規範 {fab} {dept_zh}區 {etype} 機台發生「{at.name}」（{at.code}）時的處置方式，"
        "降低產品風險並縮短停機時間。",
        "",
        "## 2. 適用範圍",
        f"適用於 {fab} 所有 {etype} 機台與其腔體。",
        "",
        "## 3. 判定標準",
        "",
        "| 監控參數 | 下限 | 上限 | 單位 |",
        "| --- | --- | --- | --- |",
        f"| {at.parameter} | {p['limit_low']} | {p['limit_high']} | {at.unit} |",
        "",
        f"量測值高於上限 {p['limit_high']} {at.unit} 即判定為異常。",
        "",
        "## 4. 處置步驟",
        "1. 確認 alarm 內容與發生的腔體，並查詢該腔體目前是否在保養中。",
        "2. 暫停該腔體派貨。保養中的腔體一律不得派貨。",
        f"3. 等待 {p['wait_min']} 分鐘後重新量測。",
        f"4. 若連續 {p['consecutive']} 次量測超出上限，hold 受影響批號並通知{p['notify_role']}。",
        f"5. 執行{p['pm_type']}後，以 {p['monitor_wafers']} 片監控晶圓驗證，通過才可復機。",
        "",
        "## 5. 升級條件",
        f"異常持續超過 {p['escalate_hours']} 小時仍未排除，升級至模組經理。",
    ]
    if clearance >= 2:
        lines += [
            "",
            "## 6. 製程補償參數（限授權人員）",
            f"復機首批可套用補償值 {p['comp_value']}（{at.parameter}），"
            f"僅限 {p['comp_lots']} 批內使用。",
        ]
    lines += ["", "## 修訂紀錄", ""]
    if html_rev:
        lines.append(
            "<table><tr><th>版次</th><th>生效日</th></tr>"
            f"<tr><td>{version}</td><td>{eff}</td></tr></table>"
        )
    else:
        lines += ["| 版次 | 生效日 |", "| --- | --- |", f"| {version} | {eff} |"]
    return "\n".join(lines) + "\n"


def gen_sops(rng: random.Random) -> list[Doc]:
    docs: list[Doc] = []
    keys = [(at, fab) for at in world.ALARM_TYPES for fab in world.FABS]
    versioned = set(rng.sample(range(len(keys)), 8))
    for i, (at, fab) in enumerate(keys):
        sop_key = f"SOP-{fab}-{at.code}"
        clearance = rng.choices([0, 1, 2, 3], weights=[1, 6, 3, 1])[0]
        p = _sop_params(rng, at)
        p["comp_value"] = f"{rng.choice(['+', '-'])}{rng.randint(2, 9)}%"
        p["comp_lots"] = rng.randint(2, 5)
        html_rev = rng.random() < 0.2
        if i in versioned:
            old_p = dict(p)
            old_p["wait_min"] = rng.choice([w for w in (5, 10, 15, 20, 30) if w != p["wait_min"]])
            old_id, new_id = f"{sop_key}-v1", f"{sop_key}-v2"
            docs.append(
                Doc(
                    doc_id=old_id,
                    doc_type="sop",
                    title=f"{at.name}處置程序（{fab}）",
                    fab=fab,
                    department=at.department,
                    clearance=clearance,
                    effective_date="2026-03-01",
                    body_md=_render_sop(at, fab, 1, "2026-03-01", old_p, clearance, html_rev),
                    sop_key=sop_key,
                    version=1,
                    superseded_by=new_id,
                    facts={**old_p, "alarm_code": at.code, "parameter": at.parameter},
                    dirty_tags=["old_version"],
                )
            )
            version, eff, doc_id = 2, "2026-08-15", new_id
        else:
            version, eff, doc_id = 1, "2026-06-01", f"{sop_key}-v1"
        docs.append(
            Doc(
                doc_id=doc_id,
                doc_type="sop",
                title=f"{at.name}處置程序（{fab}）",
                fab=fab,
                department=at.department,
                clearance=clearance,
                effective_date=eff,
                body_md=_render_sop(at, fab, version, eff, p, clearance, html_rev),
                sop_key=sop_key,
                version=version,
                facts={**p, "alarm_code": at.code, "parameter": at.parameter},
                dirty_tags=(["html_table"] if html_rev else []),
            )
        )
    return docs


# ---------------------------------------------------------------- incident reports


def _dirty(rng: random.Random, text: str, tags: list[str]) -> str:
    if rng.random() < 0.4:
        for canon, variants in world.ABBREVIATIONS.items():
            if canon in text:
                text = text.replace(canon, rng.choice(variants))
        tags.append("abbreviation")
    if rng.random() < 0.25:
        for right, wrong in world.TYPOS.items():
            if right in text and rng.random() < 0.6:
                text = text.replace(right, wrong, 1)
        tags.append("typo")
    if rng.random() < 0.3:
        text = rng.choice(world.COLLOQUIAL_OPENERS) + " " + text
        tags.append("colloquial")
    return text


def gen_incidents(rng: random.Random, mes: dict, sops: list[Doc]) -> list[Doc]:
    at_by_code = {a.code: a for a in world.ALARM_TYPES}
    current_sop = {d.sop_key: d for d in sops if d.superseded_by is None}
    candidates = [a for a in mes["alarms"] if a["severity"] in ("warning", "critical")]
    chosen = sorted(rng.sample(candidates, 150), key=lambda a: a["occurred_at"])
    lots = {lot["lot_id"]: lot for lot in mes["lots"]}
    docs = []
    for n, al in enumerate(chosen, 1):
        at = at_by_code[al["alarm_code"]]
        sop = current_sop[f"SOP-{al['fab']}-{at.code}"]
        cause = rng.choice(ROOT_CAUSES[at.department])
        downtime = rng.randint(30, 600)
        lot_id = al["lot_id"]
        hot = lot_id is not None and lots[lot_id]["priority"] == 1
        clearance = 2 if hot else rng.choices([1, 2, 3], weights=[8, 2, 1])[0]
        when = al["occurred_at"][:16].replace("T", " ")
        tags: list[str] = []
        symptom = _dirty(
            rng,
            f"{when} 機台 {al['equipment_id']} 的 {al['chamber_id']} 發生{at.name}，"
            f"量測值 {al['_value']} {at.unit}，已經超出管制上限，腔體暫停派貨。",
            tags,
        )
        handling = _dirty(
            rng,
            f"依 {sop.sop_key} 處置：確認異常後等待重測，再次確認仍超出上限，"
            f"執行{sop.facts['pm_type']}後以監控晶圓驗證復機，停機共 {downtime} 分鐘。",
            tags,
        )
        lot_line = lot_id or "無"
        if hot:
            handling += f"受影響批號 {lot_id} 為急件，已 hold 並通知客戶窗口。"
        body = "\n".join(
            [
                f"# 異常報告 INC-2026-{n:04d}：{al['equipment_id']} {at.name}",
                "",
                "## 基本資料",
                "",
                "| 項目 | 內容 |",
                "| --- | --- |",
                f"| 發生時間 | {when} |",
                f"| 機台 | {al['equipment_id']} |",
                f"| 腔體 | {al['chamber_id']} |",
                f"| Alarm code | {at.code} |",
                f"| 批號 | {lot_line} |",
                "",
                "## 現象描述",
                symptom,
                "",
                "## 處理經過",
                handling,
                "",
                "## 根本原因",
                cause,
                "",
                "## 後續對策",
                f"將「{cause.split('導致')[0]}」納入{sop.facts['pm_type']}檢查項目。",
                "",
            ]
        )
        docs.append(
            Doc(
                doc_id=f"INC-2026-{n:04d}",
                doc_type="incident",
                title=f"{al['equipment_id']} {at.name}",
                fab=al["fab"],
                department=at.department,
                clearance=clearance,
                effective_date=al["occurred_at"][:10],
                body_md=body,
                facts={
                    "alarm_id": al["alarm_id"],
                    "alarm_code": at.code,
                    "equipment_id": al["equipment_id"],
                    "chamber_id": al["chamber_id"],
                    "lot_id": lot_id,
                    "root_cause": cause,
                    "downtime_min": downtime,
                    "sop_key": sop.sop_key,
                    "hot_lot": hot,
                },
                dirty_tags=sorted(set(tags)),
            )
        )
    return docs


def shared_docs() -> list[Doc]:
    body_public = (
        "# 緊急應變總則（全廠適用）\n\n"
        "## 1. 原則\n人員安全優先於產品與設備。\n\n"
        "## 2. 通報\n發生化學品洩漏、火警或人員受傷時，立即撥打廠內緊急分機 119 並通知值班主任。\n"
    )
    body_internal = (
        "# 異常升級通報辦法\n\n"
        "## 1. 適用範圍\n所有模組的設備與製程異常。\n\n"
        "## 2. 升級層級\n\n"
        "| 層級 | 條件 | 通知對象 |\n| --- | --- | --- |\n"
        "| L1 | 單一腔體異常 | 設備工程師 |\n"
        "| L2 | 影響急件或超過 4 小時 | 值班主任 |\n"
        "| L3 | 多機台同時異常 | 模組經理 |\n"
    )
    docs = []
    for fab in world.FABS:
        docs.append(
            Doc(
                f"GEN-{fab}-EMERGENCY-v1",
                "sop",
                "緊急應變總則",
                fab,
                world.SHARED_DEPARTMENT,
                0,
                "2026-01-01",
                body_public,
                sop_key=f"GEN-{fab}-EMERGENCY",
                facts={"emergency_ext": "119"},
            )
        )
        docs.append(
            Doc(
                f"GEN-{fab}-ESCALATION-v1",
                "sop",
                "異常升級通報辦法",
                fab,
                world.SHARED_DEPARTMENT,
                1,
                "2026-01-01",
                body_internal,
                sop_key=f"GEN-{fab}-ESCALATION",
                facts={"l2_hours": 4},
            )
        )
    return docs


# ---------------------------------------------------------------- main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate(out_dir: Path = OUT_DIR) -> dict:
    rng = random.Random(SEED)
    mes = gen_mes(rng)
    sops = gen_sops(rng) + shared_docs()
    incidents = gen_incidents(rng, mes, sops)
    docs = sops + incidents

    out_dir.mkdir(parents=True, exist_ok=True)
    for a in mes["alarms"]:
        a.pop("_value", None)
    for name, rows in mes.items():
        _write_jsonl(out_dir / f"{name}.jsonl", rows)
    rows = []
    for d in docs:
        row = asdict(d)
        row.pop("facts")
        row.pop("dirty_tags")
        rows.append(row)
    _write_jsonl(out_dir / "documents.jsonl", rows)
    # Ground truth for evals. Never fed to the model.
    facts = {d.doc_id: {"facts": d.facts, "dirty_tags": d.dirty_tags} for d in docs}
    (out_dir / "facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    summary = {name: len(rows) for name, rows in mes.items()}
    summary["sops"] = len(sops)
    summary["incidents"] = len(incidents)
    return summary


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=1))
