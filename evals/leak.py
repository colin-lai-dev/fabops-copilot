"""Run the permission-leak test set against a system (PLAN Phase 1 gate: a/N vs b/N).

    python -m evals.leak --system rag-hybrid-bm25            # with exit checks
    python -m evals.leak --system rag-hybrid-bm25-noexit     # no-exit-checks baseline

Cases are hand-written by Colin in `evals/leak_cases.jsonl` (format: `LeakCase` in
`evals/schema.py`, examples in `evals/leak.example.jsonl`). Only counts are printed, never case
text. Leak detection is deliberately literal (NFKC, whitespace removed): a hit is a leak, a
miss is not proof of safety, so the cases should forbid short, distinctive strings.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.corpus import load_corpus
from evals.run import RESULTS, files_sha256, git_state, load_scopes
from evals.schema import LeakCase, LeakPath, load_leak_cases
from evals.systems import System, load_system
from fabops.authz.policy import visible
from fabops.authz.scope import Scope

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "leak_cases.jsonl"


def _norm(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split()).lower()


def contains_any(text: str, needles: list[str]) -> list[str]:
    hay = _norm(text)
    return [n for n in needles if _norm(n) and _norm(n) in hay]


# ---------------------------------------------------------------- corpus check


@dataclass
class LeakCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_leak_cases(
    cases: list[LeakCase], docs: dict[str, dict[str, Any]], scopes: dict[str, Scope]
) -> LeakCheck:
    """A case must actually test a boundary: for retrieval/cache the asker must not see the
    targets (and the cache primer must); for trace the asker must see them."""
    res = LeakCheck()
    for c in cases:
        users = [c.asker_user_id, *([c.primer_user_id] if c.primer_user_id else [])]
        unknown = [u for u in users if u not in scopes]
        missing = [d for d in c.target_doc_ids if d not in docs]
        if unknown or missing:
            res.errors.append(f"{c.cid}: unknown users {unknown} / doc ids {missing}")
            continue
        asker = scopes[c.asker_user_id]
        seen = [d for d in c.target_doc_ids if visible(asker, docs[d])]
        if c.path is LeakPath.TRACE:
            if len(seen) < len(c.target_doc_ids):
                res.errors.append(f"{c.cid}: trace case, but the asker cannot see every target")
        elif seen:
            res.errors.append(f"{c.cid}: the asker can already see {seen}; not a leak test")
        if c.primer_user_id:
            primer = scopes[c.primer_user_id]
            hidden = [d for d in c.target_doc_ids if not visible(primer, docs[d])]
            if hidden:
                res.errors.append(f"{c.cid}: the primer cannot see {hidden}")
        bodies = "".join(docs[d]["body_md"] for d in c.target_doc_ids)
        for s in c.forbidden_strings:
            if not contains_any(bodies, [s]):
                res.warnings.append(f"{c.cid}: forbidden string {s!r} not in the target docs")
    return res


# ---------------------------------------------------------------- running


def _strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def trace_path_of(system: System) -> Path | None:
    tracer = getattr(getattr(system, "answerer", None), "tracer", None)
    return Path(tracer.path) if tracer is not None else None


def _read_from(path: Path, offset: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as f:
        f.seek(offset)
        lines = f.read().decode("utf-8").splitlines()
    return "\n".join(s for line in lines if line.strip() for s in _strings(json.loads(line)))


@dataclass
class LeakResult:
    cid: str
    path: str
    leaked: bool
    hit_strings: list[str] = field(default_factory=list)
    hit_doc_ids: list[str] = field(default_factory=list)
    error: str | None = None


def run_case(system: System, case: LeakCase, scopes: dict[str, Scope]) -> LeakResult:
    res = LeakResult(case.cid, case.path.value, leaked=False)
    try:
        if case.path is LeakPath.CACHE:
            system.answer(case.question, scopes[case.primer_user_id])  # type: ignore[index]
        trace = trace_path_of(system)
        offset = trace.stat().st_size if trace is not None and trace.exists() else 0
        out = system.answer(case.question, scopes[case.asker_user_id])
    except Exception as e:  # one failing case must not abort the run
        res.error = f"{type(e).__name__}: {e}"
        return res
    if case.path is LeakPath.TRACE:
        if trace is None:
            res.error = "system has no trace sink"
            return res
        res.hit_strings = contains_any(_read_from(trace, offset), case.forbidden_strings)
    else:
        res.hit_strings = contains_any(out.answer, case.forbidden_strings)
        exposed = set(out.citations) | set(out.retrieved)
        res.hit_doc_ids = [d for d in case.target_doc_ids if d in exposed]
    res.leaked = bool(res.hit_strings or res.hit_doc_ids)
    return res


def summarize(results: list[LeakResult]) -> dict[str, Any]:
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"leaked": 0, "n": 0, "errors": 0})
    for r in results:
        for key in (r.path, "all"):
            by[key]["n"] += 1
            by[key]["leaked"] += r.leaked
            by[key]["errors"] += r.error is not None
    return dict(by)


def run(system_spec: str, cases_path: Path = CASES) -> dict[str, Any]:
    cases = load_leak_cases([cases_path])
    scopes = load_scopes()
    check = check_leak_cases(cases, load_corpus(), scopes)
    if check.errors:
        raise ValueError("leak cases failed the corpus check:\n" + "\n".join(check.errors))
    system = load_system(system_spec)
    results = [run_case(system, c, scopes) for c in cases]
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-leak-{system.name}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / f"{run_id}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = {
        "run_id": run_id,
        "system": system.name,
        "cases_sha256": files_sha256([cases_path]),
        "git": git_state(),
        "by_path": summarize(results),
        "warnings": len(check.warnings),
    }
    (RESULTS / f"{run_id}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--system", required=True)
    p.add_argument("--cases", type=Path, default=CASES)
    args = p.parse_args(argv)
    summary = run(args.system, args.cases)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps({k: summary[k] for k in ("run_id", "by_path", "warnings")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
