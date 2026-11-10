"""Run a system over a question split and save outputs + a summary.

    python -m evals.run --split dev --system refuse_all
    python -m evals.run --split test --system ... --allow-test   # gate only, Colin's approval
    python -m evals.run --rescore <run_id>                        # re-score saved outputs

Outputs: `evals/results/<run_id>.jsonl` (raw, gitignored) and
`evals/results/<run_id>.summary.json` (metrics + provenance, committed with experiments).
Only counts and metrics are printed, never question text, so running the test split does not
expose its contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals import score
from evals.corpus import load_corpus
from evals.schema import Question, RunRecord, SystemOutput, load_questions
from evals.synonyms import synonym_table
from evals.systems import System, load_system
from fabops.authz.policy import scope_of_user
from fabops.authz.scope import Scope
from fabops.config import get_settings
from fabops.data.seed import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
RESULTS = EVALS / "results"
USERS = ROOT / "data" / "generated" / "users.jsonl"
# calibration: judge-calibration pool only (evals/gen_calibration.py), never a system metric
SPLITS = ("dev", "test", "calibration")


class TestSplitLocked(RuntimeError):
    pass


def question_files(split: str, evals_dir: Path = EVALS) -> list[Path]:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    return sorted((evals_dir / split).glob("*.jsonl"))


def load_scopes(path: Path = USERS) -> dict[str, Scope]:
    return {u["user_id"]: scope_of_user(u) for u in read_jsonl(path)}


def files_sha256(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def git_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {"commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "-s"))}


def run_questions(
    system: System, questions: list[Question], scopes: dict[str, Scope]
) -> list[SystemOutput]:
    missing = sorted({q.user_id for q in questions} - scopes.keys())
    if missing:
        raise ValueError(f"unknown user_id(s): {missing}")
    outputs = []
    for q in questions:
        t0 = time.perf_counter()
        try:
            out = system.answer(q.question, scopes[q.user_id])
        except Exception as e:  # one failing question must not abort the run
            out = SystemOutput(answer="", error=f"{type(e).__name__}: {e}")
        if out.latency_ms is None:
            out = out.model_copy(update={"latency_ms": (time.perf_counter() - t0) * 1000})
        outputs.append(out)
    return outputs


def score_outputs(questions: list[Question], outputs: list[SystemOutput]) -> dict[str, Any]:
    """Metrics from score.py, or a note while score.py is still a stub."""
    try:
        table = synonym_table()
        superseded = {d for d, doc in load_corpus().items() if doc.get("superseded_by")}
        scores = [
            score.score_question(q, o, table, superseded)
            for q, o in zip(questions, outputs, strict=True)
        ]
        return {
            "metrics": score.aggregate(scores),
            "per_question": [s.model_dump() for s in scores],
        }
    except NotImplementedError:
        return {"metrics": None, "note": "evals/score.py not implemented yet; outputs saved"}


def summarize(
    run_id: str,
    split: str,
    system_name: str,
    files: list[Path],
    questions: list[Question],
    outputs: list[SystemOutput],
    git: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`git`: the state when the run *started* (the code that produced the outputs)."""
    settings = get_settings()
    latencies = [o.latency_ms for o in outputs if o.latency_ms is not None]
    return {
        "run_id": run_id,
        "split": split,
        "system": system_name,
        "n": len(questions),
        "n_by_qtype": dict(sorted(Counter(q.qtype.value for q in questions).items())),
        "questions_sha256": files_sha256(files),
        "question_files": [p.name for p in files],
        "git": git if git is not None else git_state(),
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model},
        "errors": sum(o.error is not None for o in outputs),
        "cost_usd": round(sum(o.cost_usd for o in outputs), 6),
        "tokens": {
            "input": sum(o.input_tokens for o in outputs),
            "output": sum(o.output_tokens for o in outputs),
        },
        "latency_ms_mean": round(sum(latencies) / len(latencies), 1) if latencies else None,
        **score_outputs(questions, outputs),
    }


def write_run(
    run_id: str,
    outputs: list[SystemOutput],
    questions: list[Question],
    summary: dict[str, Any],
    results_dir: Path,
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / f"{run_id}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for q, o in zip(questions, outputs, strict=True):
            f.write(RunRecord(run_id=run_id, qid=q.qid, output=o).model_dump_json() + "\n")
    path = results_dir / f"{run_id}.summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def check_split_allowed(split: str, allow_test: bool) -> None:
    if split == "test" and not allow_test:
        raise TestSplitLocked(
            "the test split runs only at a gate with Colin's approval: `make eval-test`"
        )


def run(
    split: str,
    system_spec: str,
    *,
    allow_test: bool = False,
    limit: int | None = None,
    evals_dir: Path = EVALS,
    results_dir: Path = RESULTS,
    users_path: Path = USERS,
) -> dict[str, Any]:
    check_split_allowed(split, allow_test)
    files = question_files(split, evals_dir)
    if not files:
        raise FileNotFoundError(f"no question files in {evals_dir / split}")
    questions = load_questions(files)[:limit]
    system = load_system(system_spec)
    git = git_state()  # before the run: files may change while a long run is in progress
    outputs = run_questions(system, questions, load_scopes(users_path))
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{split}-{system.name}"
    summary = summarize(run_id, split, system.name, files, questions, outputs, git)
    summary["limit"] = limit
    summary["summary_path"] = str(write_run(run_id, outputs, questions, summary, results_dir))
    return summary


def rescore(
    run_id: str, *, allow_test: bool = False, evals_dir: Path = EVALS, results_dir: Path = RESULTS
) -> dict[str, Any]:
    old = json.loads((results_dir / f"{run_id}.summary.json").read_text(encoding="utf-8"))
    check_split_allowed(old["split"], allow_test)
    files = question_files(old["split"], evals_dir)
    if files_sha256(files) != old["questions_sha256"]:
        raise ValueError("question files changed since this run; re-run instead of re-scoring")
    by_qid = {q.qid: q for q in load_questions(files)}
    with (results_dir / f"{run_id}.jsonl").open(encoding="utf-8") as f:
        records = [RunRecord.model_validate_json(line) for line in f if line.strip()]
    questions = [by_qid[r.qid] for r in records]
    outputs = [r.output for r in records]
    summary = {
        **old,
        **score_outputs(questions, outputs),
        "rescored_at": f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
    }
    write_run(run_id, outputs, questions, summary, results_dir)
    return summary


def _print(summary: dict[str, Any]) -> None:
    keys = (
        "run_id",
        "split",
        "system",
        "n",
        "n_by_qtype",
        "errors",
        "cost_usd",
        "latency_ms_mean",
        "metrics",
        "note",
        "summary_path",
    )
    for k in keys:
        if k in summary:
            print(f"{k:>16}: {json.dumps(summary[k], ensure_ascii=False)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--split", choices=SPLITS, default="dev")
    p.add_argument("--system", default="refuse_all")
    p.add_argument("--allow-test", action="store_true", help="required for --split test")
    p.add_argument("--limit", type=int, default=None, help="first N questions (smoke runs)")
    p.add_argument("--rescore", metavar="RUN_ID")
    a = p.parse_args(argv)
    try:
        if a.rescore:
            summary = rescore(a.rescore, allow_test=a.allow_test)
        else:
            summary = run(a.split, a.system, allow_test=a.allow_test, limit=a.limit)
    except (TestSplitLocked, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
