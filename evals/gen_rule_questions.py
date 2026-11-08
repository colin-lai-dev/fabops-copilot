"""Rule-generated QA questions from the data skeleton (ADR-0004/0005).

    python -m evals.gen_rule_questions   # -> evals/dev/rule.jsonl, evals/test/rule.jsonl

Facts come from `data/generated/facts.json` (the ground truth), never from model output.
Design choices:

- Each (document, fact field) pair is asked at most once across all question types, so a
  fact seen in dev is never re-asked with different wording in test.
- The asker is the least-privileged demo user who can see every expected document; the
  QA set measures answering, while permission leaks are tested by Colin's leakage set.
- Restricted content (SOP section 6, compensation parameters) is never asked here.
- Refusal questions ask about things absent from the corpus, as admin_all, so a correct
  refusal cannot be explained by missing permissions.
- Only counts are printed; the generator also writes the test split.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.corpus import check_questions, load_corpus
from evals.run import load_scopes
from evals.schema import QType, Question
from evals.split import write_split
from fabops.authz.policy import visible
from fabops.authz.scope import Scope
from fabops.data import world

FACTS = Path(__file__).resolve().parents[1] / "data" / "generated" / "facts.json"
SEED = 20261108
POOL_NAME = "rule.jsonl"
ADMIN = "admin_all"

ALARMS = {a.code: a for a in world.ALARM_TYPES}

# Per qtype: target count of SOP / incident questions.
N_FACT_SOP, N_FACT_INC = 30, 15
N_PARA_SOP, N_PARA_INC = 20, 10
N_DIRTY = 25
N_CROSS = 20

# SOP fact fields -> (key fact formatter, templates per qtype).
# Template fields: fab, eq (equipment type), name (alarm name), code, param, dept (Chinese).
SOP_FIELDS: dict[str, dict[str, Any]] = {
    "limit_high": {
        "key_fact": lambda f, a: f"{_num(f['limit_high'])} {a.unit}",
        QType.FACT: "{fab} {eq} 發生「{name}」時，{param} 的上限是多少？",
        QType.PARAPHRASE: "{fab} 的{dept}機台，{param} 量到多少以上就算異常？",
        QType.DIRTY: "{fab} {eq} 的 {param} OOC 上限多少？",
    },
    "wait_min": {
        "key_fact": lambda f, a: f"{f['wait_min']} 分鐘",
        QType.FACT: "{fab} {eq} 發生「{name}」時，要等待幾分鐘後重新量測？",
        QType.PARAPHRASE: "{fab} 跳 {code} 以後，要隔多久才能再量一次？",
        QType.DIRTY: "{fab} EQP 跳 {code}，確任意常後要等幾分鐘在次量測？",
    },
    "consecutive": {
        "key_fact": lambda f, a: f"{f['consecutive']} 次",
        QType.FACT: "{fab} 的「{name}」處置程序中，連續幾次量測超出上限要 hold 批號？",
        QType.PARAPHRASE: "{fab}{dept}區遇到{name}，要量到第幾次都超標才需要把貨扣住？",
        QType.DIRTY: "{fab} chamber {name}，連續幾次 OOC 要 hold lot？",
    },
    "notify_role": {
        "key_fact": lambda f, a: f["notify_role"],
        QType.FACT: "{fab} {eq} 發生「{name}」並 hold 批號後，要通知誰？",
        QType.PARAPHRASE: "{fab} {eq} 的 {param} 一直超標、貨也扣了，接下來該找哪個角色？",
        QType.DIRTY: "{fab} EQP {name}，部驟裡 hold lot 之後要通知誰？",
    },
    "pm_type": {
        "key_fact": lambda f, a: f["pm_type"],
        QType.FACT: "{fab} {eq} 發生「{name}」時，要執行哪一種保養才能復機？",
        QType.PARAPHRASE: "{fab} 的 {code} 處理完，要做什麼維護才能讓機台回到生產？",
        QType.DIRTY: "{fab} tool {name}要做哪種 PM 才能 back to line？",
    },
    "escalate_hours": {
        "key_fact": lambda f, a: f"{f['escalate_hours']} 小時",
        QType.FACT: "{fab} 的「{name}」異常持續多久仍未排除，要升級至模組經理？",
        QType.PARAPHRASE: "{fab} {name}如果一直排除不了，拖多久要往上報？",
        QType.DIRTY: "{fab} {code} 意常多久沒排除要升級？",
    },
    "monitor_wafers": {
        "key_fact": lambda f, a: f"{f['monitor_wafers']} 片",
        QType.FACT: "{fab} {eq} 發生「{name}」後，要用幾片監控晶圓驗證才能復機？",
        QType.PARAPHRASE: "{fab} 的{name}修好後，驗證要跑多少片監控片？",
        QType.DIRTY: "{fab} {code} recover 前要跑幾片監控晶圓？",
    },
}

OLD_VERSION_TEMPLATES = [
    "{fab} {eq} 發生「{name}」時，等多久要重新量測？",
    "{fab} 的 {code} 處置程序目前規定，重新量測前要等待多久？",
]

INC_FACT = {
    "root_cause": ("{inc} 的根本原因是什麼？", lambda f: f["root_cause"]),
    "downtime_min": ("{inc} 這次異常總共停機多久？", lambda f: f"{f['downtime_min']} 分鐘"),
}
INC_PARAPHRASE = "{equipment} 在 {date} 發生的{name}，是什麼原因造成的？"
CROSS_TEMPLATES = {
    "wait_min": ("{inc} 處置時依照的 SOP，規定重新量測前要等幾分鐘？", "{wait_min} 分鐘"),
    "escalate_hours": (
        "{inc} 那類異常若一直排除不了，依 SOP 多久要升級？",
        "{escalate_hours} 小時",
    ),
    "notify_role": ("{inc} 依照的 SOP 中，hold 批號後要通知誰？", "{notify_role}"),
}

# Refusals: things that do not exist in the corpus. Codes follow the real format but are
# unused; FX3 is not a fab; INC numbers beyond the generated range.
REFUSE_QUESTIONS = [
    "FX1 發生 ETC-VAC-0999 時要怎麼處置？",
    "FX2 的 LIT-RET-0377 alarm 上限是多少？",
    "TFM-UNI-0688 的處置程序要通知誰？",
    "FX1 CMP-TMP-0855 異常要等幾分鐘重測？",
    "DIF-PRE-0731 持續多久要升級？",
    "FX3 的 ETCHER 腔體壓力上限是多少？",
    "FX3 廠的研磨液流量不足處置程序是哪一份？",
    "INC-2026-0999 的根本原因是什麼？",
    "INC-2026-0451 停機了多久？",
    "FX1 腔體壓力異常處置程序規定的零件保固期限是多久？",
    "FX2 對焦偏移處置程序中，負責的廠商聯絡電話是多少？",
    "FX1 ETCHER 的設備採購價格是多少？",
    "員工餐廳週末有營業嗎？",
    "今年的年終獎金怎麼計算？",
    "FX2 爐管溫度偏差處置程序第 3 版改了什麼？",
]


@dataclass
class Ctx:
    docs: dict[str, dict[str, Any]]
    facts: dict[str, dict[str, Any]]
    scopes: dict[str, Scope]
    users_by_privilege: list[str]


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _sop_vars(doc: dict[str, Any], f: dict[str, Any]) -> dict[str, str]:
    a = ALARMS[f["alarm_code"]]
    return {
        "fab": doc["fab"],
        "eq": world.EQUIPMENT_TYPES[a.department][0],
        "name": a.name,
        "code": a.code,
        "param": a.parameter,
        "dept": world.DEPARTMENTS[a.department],
    }


def asker(ctx: Ctx, doc_ids: list[str]) -> str:
    for uid in ctx.users_by_privilege:
        if all(visible(ctx.scopes[uid], ctx.docs[d]) for d in doc_ids):
            return uid
    raise ValueError(f"no demo user can see {doc_ids}")


def _privilege_order(scopes: dict[str, Scope]) -> list[str]:
    return sorted(
        scopes,
        key=lambda u: (scopes[u].clearance, len(scopes[u].departments), len(scopes[u].fabs), u),
    )


def _incident_date(doc: dict[str, Any]) -> str:
    m = re.search(r"\| 發生時間 \| (\d{4}-\d{2}-\d{2})", doc["body_md"])
    if not m:
        raise ValueError(f"{doc['doc_id']}: no date in body")
    return m.group(1)


def generate(ctx: Ctx, seed: int = SEED) -> list[Question]:
    rng = random.Random(seed)
    out: list[Question] = []
    counters: Counter[str] = Counter()
    used: set[tuple[str, str]] = set()  # (doc_id, field)

    def add(
        qtype: QType,
        text: str,
        facts: list[str],
        docs: list[str],
        *,
        user: str | None = None,
        refuse: bool = False,
        notes: str = "",
    ) -> None:
        counters[qtype.value] += 1
        out.append(
            Question(
                qid=f"R-{qtype.value.upper()}-{counters[qtype.value]:04d}",
                qtype=qtype,
                source="rule",
                question=text,
                user_id=user or asker(ctx, docs),
                key_facts=facts,
                expected_doc_ids=docs,
                should_refuse=refuse,
                notes=notes,
            )
        )

    # Alarm SOPs only: the general GEN-* SOPs carry the same facts in both fabs.
    current_sops = sorted(
        (
            d
            for d in ctx.docs.values()
            if d["doc_type"] == "sop"
            and not d["superseded_by"]
            and "alarm_code" in ctx.facts[d["doc_id"]]["facts"]
        ),
        key=lambda d: d["doc_id"],
    )
    current_by_key = {d["sop_key"]: d for d in current_sops}
    versioned = [d for d in current_sops if d["version"] > 1]

    # Old version: wait_min is the field that differs between v1 and v2.
    for d in versioned:
        f = ctx.facts[d["doc_id"]]["facts"]
        old_id = next(o["doc_id"] for o in ctx.docs.values() if o["superseded_by"] == d["doc_id"])
        old_wait = ctx.facts[old_id]["facts"]["wait_min"]
        for t in OLD_VERSION_TEMPLATES:
            add(
                QType.OLD_VERSION,
                t.format(**_sop_vars(d, f)),
                [f"{f['wait_min']} 分鐘"],
                [d["doc_id"]],
                notes=f"舊版 {old_id} 為 {old_wait} 分鐘",
            )
        used.add((d["doc_id"], "wait_min"))

    # SOP questions for fact / paraphrase / dirty, each (doc, field) at most once.
    pairs = [(d, fld) for d in current_sops for fld in SOP_FIELDS if (d["doc_id"], fld) not in used]
    rng.shuffle(pairs)
    for qtype, n in (
        (QType.FACT, N_FACT_SOP),
        (QType.PARAPHRASE, N_PARA_SOP),
        (QType.DIRTY, N_DIRTY),
    ):
        taken = 0
        for d, fld in pairs:
            if taken == n:
                break
            if (d["doc_id"], fld) in used:
                continue
            f = ctx.facts[d["doc_id"]]["facts"]
            spec = SOP_FIELDS[fld]
            add(
                qtype,
                spec[qtype].format(**_sop_vars(d, f)),
                [spec["key_fact"](f, ALARMS[f["alarm_code"]])],
                [d["doc_id"]],
                notes=f"field={fld}",
            )
            used.add((d["doc_id"], fld))
            taken += 1

    # Incidents: fact (by id), paraphrase (by equipment + date, no id), cross-doc (+ SOP).
    incidents = sorted(
        (d for d in ctx.docs.values() if d["doc_type"] == "incident"), key=lambda d: d["doc_id"]
    )
    rng.shuffle(incidents)
    signature = Counter(
        (
            ctx.facts[d["doc_id"]]["facts"]["equipment_id"],
            _incident_date(d),
            ctx.facts[d["doc_id"]]["facts"]["alarm_code"],
        )
        for d in incidents
    )
    pool = iter(incidents)

    for i in range(N_FACT_INC):
        d = next(pool)
        f = ctx.facts[d["doc_id"]]["facts"]
        fld = list(INC_FACT)[i % len(INC_FACT)]
        tmpl, fact = INC_FACT[fld]
        add(
            QType.FACT, tmpl.format(inc=d["doc_id"]), [fact(f)], [d["doc_id"]], notes=f"field={fld}"
        )

    taken = 0
    for d in pool:
        if taken == N_PARA_INC:
            break
        f = ctx.facts[d["doc_id"]]["facts"]
        sig = (f["equipment_id"], _incident_date(d), f["alarm_code"])
        if signature[sig] != 1:
            continue  # ambiguous without the incident id
        text = INC_PARAPHRASE.format(
            equipment=f["equipment_id"], date=sig[1], name=ALARMS[f["alarm_code"]].name
        )
        add(QType.PARAPHRASE, text, [f["root_cause"]], [d["doc_id"]], notes="field=root_cause")
        taken += 1

    taken = 0
    for d in pool:
        if taken == N_CROSS:
            break
        f = ctx.facts[d["doc_id"]]["facts"]
        sop = current_by_key.get(f.get("sop_key"))
        if sop is None:
            continue
        # Rotate fields, but skip SOP facts that another question already asks.
        rot = list(CROSS_TEMPLATES)
        rot = rot[taken % len(rot) :] + rot[: taken % len(rot)]
        fld = next((x for x in rot if (sop["doc_id"], x) not in used), None)
        if fld is None:
            continue
        used.add((sop["doc_id"], fld))
        tmpl, fact = CROSS_TEMPLATES[fld]
        sop_f = ctx.facts[sop["doc_id"]]["facts"]
        add(
            QType.CROSS_DOC,
            tmpl.format(inc=d["doc_id"]),
            [fact.format(**sop_f)],
            [d["doc_id"], sop["doc_id"]],
            notes=f"field={fld}",
        )
        taken += 1

    for text in REFUSE_QUESTIONS:
        add(QType.REFUSE, text, [], [], user=ADMIN, refuse=True)

    return out


def load_ctx() -> Ctx:
    import json

    scopes = load_scopes()
    return Ctx(
        docs=load_corpus(),
        facts=json.loads(FACTS.read_text(encoding="utf-8")),
        scopes=scopes,
        users_by_privilege=_privilege_order(scopes),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--force", action="store_true", help="overwrite an existing (frozen) test file")
    a = p.parse_args(argv)
    ctx = load_ctx()
    questions = generate(ctx)
    res = check_questions(questions, ctx.docs, ctx.scopes)
    if res.errors or res.warnings:  # rule questions must be exact
        for m in res.errors + res.warnings:
            print(f"error: {m}", file=sys.stderr)
        return 2
    try:
        counts = write_split(questions, POOL_NAME, force=a.force)
    except FileExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    by_type = Counter(q.qtype.value for q in questions)
    by_user = Counter(q.user_id for q in questions)
    print(f"rule questions: {len(questions)} -> dev {counts['dev']}, test {counts['test']}")
    print(f"  by qtype: {dict(sorted(by_type.items()))}")
    print(f"  by asker: {dict(sorted(by_user.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
