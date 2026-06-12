"""Backfill embeddings for all price_records rows missing them."""

import os
import sys
import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from embeddings import embed_texts, EMBEDDING_MODEL

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "pricedb")
DB_USER = os.getenv("POSTGRES_USER", "price_admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "")


def connect():
    return psycopg.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        row_factory=dict_row,
    )


def main():
    conn = connect()
    cur = conn.cursor()

    # Get rows missing embeddings
    cur.execute(
        "SELECT id, search_text FROM price_records "
        "WHERE embedding IS NULL AND search_text IS NOT NULL "
        "ORDER BY id"
    )
    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        print("All rows already have embeddings. Nothing to do.")
        return

    print(f"Backfilling {total} rows...")

    batch_size = 32
    done = 0

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        texts = [r["search_text"] for r in batch]
        ids = [r["id"] for r in batch]

        embeddings = embed_texts(texts)

        for row_id, emb in zip(ids, embeddings):
            # pgvector expects string format: '[0.1, 0.2, ...]'
            vec_str = "[" + ",".join(str(v) for v in emb) + "]"
            cur.execute(
                "UPDATE price_records SET "
                "embedding = %s::vector, "
                "embedding_model = %s, "
                "embedding_version = %s, "
                "embedded_at = %s "
                "WHERE id = %s",
                (vec_str, EMBEDDING_MODEL, "v1", datetime.now(timezone.utc), row_id),
            )

        conn.commit()
        done += len(batch)
        print(f"  [{done}/{total}] embedded {len(batch)} rows")

    # Final check
    cur.execute(
        "SELECT count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded, "
        "count(*) AS total FROM price_records"
    )
    result = cur.fetchone()
    print(f"\nDone! {result['embedded']}/{result['total']} rows have embeddings.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
