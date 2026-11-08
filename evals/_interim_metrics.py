"""TEMPORARY retrieval metrics — delete once evals/score.py is done (handoff 002, item 3).

This is NOT the implementation of score.py and must not be used as one: it exists only so
retrieval can be developed on dev before Colin's scorer lands. It follows the ADR-0005
default rules for retrieval only (Recall@5 = fraction of expected docs in the top 5; Hit@5;
MRR on the first expected doc), over answerable questions.

    python -m evals._interim_metrics <run_id> [<run_id> ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from evals.run import RESULTS, check_split_allowed, question_files
from evals.schema import RunRecord, load_questions


def _metrics(rows: list[tuple[list[str], list[str]]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    rec = hit = rr = 0.0
    for retrieved, expected in rows:
        top = retrieved[:5]
        rec += sum(e in top for e in expected) / len(expected)
        hit += any(e in top for e in expected)
        ranks = [retrieved.index(e) + 1 for e in expected if e in retrieved]
        rr += 1 / min(ranks) if ranks else 0.0
    return {
        "n": n,
        "recall@5": round(rec / n, 3),
        "hit@5": round(hit / n, 3),
        "mrr": round(rr / n, 3),
    }


def interim(run_id: str, *, results_dir: Path = RESULTS, allow_test: bool = False) -> dict:
    summary = json.loads((results_dir / f"{run_id}.summary.json").read_text(encoding="utf-8"))
    check_split_allowed(summary["split"], allow_test)
    qs = {q.qid: q for q in load_questions(question_files(summary["split"]))}
    with (results_dir / f"{run_id}.jsonl").open(encoding="utf-8") as f:
        records = [RunRecord.model_validate_json(line) for line in f if line.strip()]
    by_type: dict[str, list] = defaultdict(list)
    for r in records:
        q = qs[r.qid]
        if q.should_refuse or not q.expected_doc_ids:
            continue
        by_type[q.qtype.value].append((r.output.retrieved, q.expected_doc_ids))
    lat = [r.output.latency_ms for r in records if r.output.latency_ms is not None]
    return {
        "run_id": run_id,
        "system": summary["system"],
        "split": summary["split"],
        "overall": _metrics([x for rows in by_type.values() for x in rows]),
        "by_qtype": {t: _metrics(rows) for t, rows in sorted(by_type.items())},
        "latency_ms": {
            "mean": round(sum(lat) / len(lat), 1),
            "p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1),
        }
        if lat
        else None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("run_ids", nargs="+")
    a = p.parse_args(argv)
    for rid in a.run_ids:
        print(json.dumps(interim(rid), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
