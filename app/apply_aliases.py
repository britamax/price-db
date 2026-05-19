"""Re-apply alias expansion to existing price_records.search_text + re-embed.

Run after seeding/editing the alias table to propagate changes to existing rows.
"""
import os
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from aliases import expand_aliases, reload_aliases
from embeddings import embed_single, EMBEDDING_MODEL


def main():
    conn = psycopg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "pricedb"),
        user=os.getenv("POSTGRES_USER", "price_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        row_factory=dict_row,
    )

    n_loaded = reload_aliases(conn)
    print(f"Loaded {n_loaded} aliases from DB")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nama, merek, spesifikasi, satuan, supplier, keterangan, search_text
            FROM price_records
            ORDER BY id
            """
        )
        rows = cur.fetchall()

    print(f"Re-processing {len(rows)} rows...")
    changed = 0
    re_embedded = 0
    embed_version = datetime.now(timezone.utc).strftime("%Y%m%d")

    for r in rows:
        # Rebuild canonical search text from source fields
        parts = [str(r.get(k, "") or "") for k in ("nama", "merek", "spesifikasi", "satuan", "supplier", "keterangan")]
        raw = " ".join(p for p in parts if p).strip()
        expanded = expand_aliases(raw)

        if expanded == (r["search_text"] or ""):
            continue  # No change → skip

        # Generate new embedding for the changed text
        try:
            new_emb = embed_single(expanded)
        except Exception as e:
            print(f"  [WARN] row {r['id']} embed failed: {e}")
            continue

        vec_str = "[" + ",".join(str(v) for v in new_emb) + "]"
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE price_records
                SET search_text = %s,
                    embedding = %s::vector,
                    embedding_model = %s,
                    embedding_version = %s,
                    embedded_at = now()
                WHERE id = %s
                """,
                (expanded, vec_str, EMBEDDING_MODEL, embed_version, r["id"]),
            )
        changed += 1
        re_embedded += 1
        if changed % 10 == 0:
            print(f"  [{changed}/{len(rows)}] reprocessed")
            conn.commit()

    conn.commit()
    print(f"\nDone! {changed} rows had updated search_text, {re_embedded} re-embedded.")
    conn.close()


if __name__ == "__main__":
    main()
