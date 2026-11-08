"""Split a question pool into dev/test, stratified by qtype (ADR-0005: dev/test = 40/60).

    python -m evals.split evals/handwritten.jsonl     # -> evals/dev/handwritten.jsonl
                                                      #    evals/test/handwritten.jsonl

Each pool is split on its own, so adding a new pool never moves questions that were already
assigned. The split is deterministic (fixed seed, qids sorted first). An existing test file
is never overwritten unless `--force` is given: once frozen, the test set stays put.
Only counts are printed.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

from evals.schema import Question, dump_questions, load_questions

EVALS = Path(__file__).resolve().parent
DEV_RATIO = 0.4
SEED = 20261108


def stratified_split(
    questions: list[Question], dev_ratio: float = DEV_RATIO, seed: int = SEED
) -> tuple[list[Question], list[Question]]:
    by_type: dict[str, list[Question]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.qid):
        by_type[q.qtype.value].append(q)
    rng = random.Random(seed)
    dev, test = [], []
    for qtype in sorted(by_type):
        group = by_type[qtype]
        rng.shuffle(group)
        n_dev = round(len(group) * dev_ratio)
        dev += group[:n_dev]
        test += group[n_dev:]
    return sorted(dev, key=lambda q: q.qid), sorted(test, key=lambda q: q.qid)


def split_pool(pool: Path, *, evals_dir: Path = EVALS, force: bool = False) -> dict[str, int]:
    name = pool.name
    dev_path, test_path = evals_dir / "dev" / name, evals_dir / "test" / name
    if test_path.exists() and not force:
        raise FileExistsError(f"{test_path} exists (frozen test set); pass --force to replace")
    dev, test = stratified_split(load_questions([pool]))
    dump_questions(dev, dev_path)
    dump_questions(test, test_path)
    return {"dev": len(dev), "test": len(test)}


def counts_by_type(questions: list[Question]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for q in questions:
        out[q.qtype.value] += 1
    return dict(sorted(out.items()))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("pool", type=Path)
    p.add_argument("--force", action="store_true", help="overwrite an existing test file")
    a = p.parse_args(argv)
    try:
        counts = split_pool(a.pool, force=a.force)
    except (FileExistsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{a.pool.name}: dev {counts['dev']}, test {counts['test']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
