"""Eval harness untuk weight tuning hybrid search.

Run:
    python -m eval.evaluate                 # default weights
    python -m eval.evaluate --sweep         # grid search atas weight space
    python -m eval.evaluate --top-k 5       # ubah K
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Make parent package importable when run as `python -m eval.evaluate`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from psycopg.rows import dict_row

from embeddings import embed_single
from db import search_hybrid


def load_queries(path: Path) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        q, expected = [s.strip() for s in line.split("|", 1)]
        pairs.append((q, expected))
    return pairs


def connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "pricedb"),
        user=os.getenv("POSTGRES_USER", "price_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        row_factory=dict_row,
    )


def evaluate(queries: List[Tuple[str, str]], w_cos: float, w_tri: float, w_ts: float,
             top_k: int = 10, verbose: bool = False,
             emb_cache: dict | None = None) -> Tuple[float, float]:
    hits = 0
    mrr_total = 0.0
    with connect() as conn:
        for q, expected in queries:
            if emb_cache is not None:
                if q not in emb_cache:
                    emb_cache[q] = embed_single(q)
                emb = emb_cache[q]
            else:
                emb = embed_single(q)
            results = search_hybrid(conn, q, emb, top_k, w_cos, w_tri, w_ts)
            found_rank = None
            for i, r in enumerate(results, 1):
                if expected.lower() in r["nama"].lower():
                    found_rank = i
                    break
            if found_rank:
                hits += 1
                mrr_total += 1.0 / found_rank
                status = f"@{found_rank}"
            else:
                status = "MISS"
            if verbose:
                top1 = results[0]["nama"] if results else "(no results)"
                print(f"  {status:6} | {q:40s} | want '{expected}' | top1='{top1}'")
    n = len(queries)
    recall = hits / n if n else 0.0
    mrr = mrr_total / n if n else 0.0
    return recall, mrr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(Path(__file__).parent / "queries.txt"))
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--sweep", action="store_true", help="Grid search atas (cos, tri, ts) weights")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    queries = load_queries(Path(args.queries))
    print(f"Loaded {len(queries)} eval queries from {args.queries}")
    print(f"Top-K = {args.top_k}\n")

    if not args.sweep:
        recall, mrr = evaluate(queries, 0.5, 0.3, 0.2, args.top_k, verbose=True)
        print(f"\nDefault weights (0.5/0.3/0.2): Recall@{args.top_k}={recall:.3f}  MRR={mrr:.3f}")
        return

    # Grid search atas simplex weight space
    print("Pre-computing embeddings for all queries (cached)...")
    emb_cache: dict = {}
    # Warm cache with one pass
    evaluate(queries, 0.5, 0.3, 0.2, args.top_k, emb_cache=emb_cache)
    print(f"Cached {len(emb_cache)} embeddings\n")
    print("Grid search (weights sum to 1.0, step 0.1):\n")
    best = (0.0, 0.0, (0.5, 0.3, 0.2))
    rows = []
    step = 0.1
    candidates = [round(i * step, 1) for i in range(11)]
    for w_cos in candidates:
        for w_tri in candidates:
            w_ts = round(1.0 - w_cos - w_tri, 2)
            if w_ts < 0 or w_ts > 1:
                continue
            recall, mrr = evaluate(queries, w_cos, w_tri, w_ts, args.top_k, emb_cache=emb_cache)
            rows.append((recall, mrr, w_cos, w_tri, w_ts))
            if (recall, mrr) > (best[0], best[1]):
                best = (recall, mrr, (w_cos, w_tri, w_ts))

    rows.sort(reverse=True)
    print(f"{'Recall':>7} {'MRR':>6}  cos  tri  ts")
    for r, m, c, t, s in rows[:15]:
        print(f"  {r:.3f}  {m:.3f}  {c}  {t}  {s}")
    print(f"\nBest: Recall={best[0]:.3f} MRR={best[1]:.3f} weights={best[2]}")


if __name__ == "__main__":
    main()
