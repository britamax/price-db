import json
from typing import Any, Dict, List, Tuple

import psycopg
from psycopg.rows import dict_row

from price_utils import (
    canonical_search_text,
    detect_category,
    map_unit,
    normalize_search_text,
    parse_indonesian_date,
    parse_price_id,
    row_hash_for,
)


def connect_from_env(env: Dict[str, str]):
    return psycopg.connect(
        host=env.get("DB_HOST", "postgres"),
        dbname=env.get("POSTGRES_DB", "pricedb"),
        user=env.get("POSTGRES_USER", "price_admin"),
        password=env.get("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        row_factory=dict_row,
    )


def init_schema(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_batches (
                id BIGSERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                input_source TEXT NOT NULL DEFAULT 'web_upload',
                uploaded_by TEXT,
                uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                status TEXT NOT NULL DEFAULT 'processing',
                total_rows INTEGER NOT NULL DEFAULT 0,
                inserted_rows INTEGER NOT NULL DEFAULT 0,
                duplicate_rows INTEGER NOT NULL DEFAULT 0,
                error_rows INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                file_hash TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_price_rows (
                id BIGSERIAL PRIMARY KEY,
                first_batch_id BIGINT REFERENCES upload_batches(id),
                last_seen_batch_id BIGINT REFERENCES upload_batches(id),
                seen_count INTEGER NOT NULL DEFAULT 1,
                row_number INTEGER,
                source_sheet TEXT,
                raw_json JSONB NOT NULL,
                no_raw TEXT,
                nama_raw TEXT,
                merek_raw TEXT,
                spesifikasi_raw TEXT,
                satuan_raw TEXT,
                grup_raw TEXT,
                harga_raw TEXT,
                supplier_raw TEXT,
                tanggal_raw TEXT,
                lokasi_raw TEXT,
                sumber_raw TEXT,
                keterangan_raw TEXT,
                harga_parsed NUMERIC,
                tanggal_parsed DATE,
                satuan_mapped TEXT,
                row_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_row_events (
                id BIGSERIAL PRIMARY KEY,
                batch_id BIGINT REFERENCES upload_batches(id),
                row_number INTEGER,
                raw_row_id BIGINT REFERENCES raw_price_rows(id),
                row_hash TEXT,
                status TEXT NOT NULL,
                message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id BIGSERIAL PRIMARY KEY,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                UNIQUE(category, subcategory)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS category_rules (
                id BIGSERIAL PRIMARY KEY,
                keyword TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 100,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS price_records (
                id BIGSERIAL PRIMARY KEY,
                raw_price_row_id BIGINT NOT NULL UNIQUE REFERENCES raw_price_rows(id),
                nama TEXT NOT NULL,
                merek TEXT,
                spesifikasi TEXT,
                satuan TEXT,
                category TEXT,
                subcategory TEXT,
                category_source TEXT,
                category_confidence NUMERIC,
                harga NUMERIC NOT NULL,
                harga_raw TEXT,
                supplier TEXT,
                supplier_normalized TEXT,
                effective_date DATE,
                lokasi TEXT,
                sumber TEXT,
                keterangan TEXT,
                search_text TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_records_search_trgm ON price_records USING gin (search_text gin_trgm_ops)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_records_date ON price_records (effective_date DESC NULLS LAST)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_records_category ON price_records (category, subcategory)")
        cur.execute("DROP TABLE IF EXISTS upload_tests")
    conn.commit()


def create_batch(conn, filename: str, uploaded_by: str, input_source: str, notes: str = "", file_hash: str = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO upload_batches (filename, uploaded_by, input_source, notes, file_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (filename, uploaded_by, input_source, notes, file_hash),
        )
        return cur.fetchone()["id"]


def finish_batch(conn, batch_id: int, status: str, total: int, inserted: int, duplicate: int, errors: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE upload_batches SET status=%s,total_rows=%s,inserted_rows=%s,duplicate_rows=%s,error_rows=%s WHERE id=%s",
            (status, total, inserted, duplicate, errors, batch_id),
        )
    conn.commit()


def canonical_row_from_input(row: Dict[str, Any]) -> Dict[str, Any]:
    nama = row.get("nama", "") or ""
    merek = row.get("merek", "") or ""
    spec = row.get("spesifikasi", "") or ""
    satuan_raw = row.get("satuan", "") or row.get("satuan_raw", "") or ""
    satuan, factor, conv_note = map_unit(satuan_raw)
    harga = row.get("harga")
    if harga is None or harga == "":
        harga = parse_price_id(row.get("harga_raw", ""))
    tanggal = row.get("tanggal") or row.get("effective_date")
    tanggal_parsed = tanggal if hasattr(tanggal, "isoformat") else parse_indonesian_date(tanggal)
    category, subcategory, cat_source, cat_conf = detect_category(nama, row.get("grup", ""))
    result = {
        "nama": str(nama).strip(),
        "merek": str(merek).strip(),
        "spesifikasi": str(spec).strip(),
        "satuan": satuan,
        "grup": row.get("grup", "") or subcategory or category,
        "harga": harga,
        "supplier": str(row.get("supplier", "") or "").strip(),
        "tanggal": tanggal_parsed,
        "lokasi": str(row.get("lokasi", "") or "").strip(),
        "sumber": str(row.get("sumber", "") or "").strip(),
        "keterangan": str(row.get("keterangan", "") or "").strip(),
        "category": row.get("category") or category,
        "subcategory": row.get("subcategory") or subcategory,
        "category_source": row.get("category_source") or cat_source,
        "category_confidence": row.get("category_confidence") or cat_conf,
        "harga_raw": str(row.get("harga_raw", row.get("harga", "")) or ""),
        "satuan_raw": str(satuan_raw),
    }
    return result


def import_rows(conn, batch_id: int, rows: List[Dict[str, Any]], source_sheet: str = None) -> Dict[str, int]:
    inserted = duplicate = errors = total = 0
    for idx, original in enumerate(rows, start=1):
        total += 1
        try:
            row = canonical_row_from_input(original)
            if not row["nama"] or row["harga"] is None:
                raise ValueError("nama dan harga wajib ada")
            h = row_hash_for(row)
            raw_json = json.dumps(original, ensure_ascii=False, default=str)
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM raw_price_rows WHERE row_hash=%s", (h,))
                existing = cur.fetchone()
                if existing:
                    raw_id = existing["id"]
                    cur.execute("UPDATE raw_price_rows SET seen_count=seen_count+1,last_seen_batch_id=%s,updated_at=now() WHERE id=%s", (batch_id, raw_id))
                    cur.execute("INSERT INTO upload_row_events (batch_id,row_number,raw_row_id,row_hash,status,message) VALUES (%s,%s,%s,%s,'duplicate','duplicate row_hash')", (batch_id, idx, raw_id, h))
                    duplicate += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO raw_price_rows (
                            first_batch_id,last_seen_batch_id,row_number,source_sheet,raw_json,
                            no_raw,nama_raw,merek_raw,spesifikasi_raw,satuan_raw,grup_raw,harga_raw,supplier_raw,tanggal_raw,lokasi_raw,sumber_raw,keterangan_raw,
                            harga_parsed,tanggal_parsed,satuan_mapped,row_hash
                        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                        """,
                        (batch_id,batch_id,idx,source_sheet,raw_json,
                         str(original.get("no", "") or ""), row["nama"], row["merek"], row["spesifikasi"], row["satuan_raw"], row["grup"], row["harga_raw"], row["supplier"], str(row["tanggal"] or ""), row["lokasi"], row["sumber"], row["keterangan"],
                         row["harga"], row["tanggal"], row["satuan"], h)
                    )
                    raw_id = cur.fetchone()["id"]
                    search_text = canonical_search_text(row)
                    cur.execute(
                        """
                        INSERT INTO price_records (raw_price_row_id,nama,merek,spesifikasi,satuan,category,subcategory,category_source,category_confidence,harga,harga_raw,supplier,supplier_normalized,effective_date,lokasi,sumber,keterangan,search_text)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (raw_id,row["nama"],row["merek"],row["spesifikasi"],row["satuan"],row["category"],row["subcategory"],row["category_source"],row["category_confidence"],row["harga"],row["harga_raw"],row["supplier"],normalize_search_text(row["supplier"]),row["tanggal"],row["lokasi"],row["sumber"],row["keterangan"],search_text)
                    )
                    cur.execute("INSERT INTO upload_row_events (batch_id,row_number,raw_row_id,row_hash,status,message) VALUES (%s,%s,%s,%s,'inserted','ok')", (batch_id, idx, raw_id, h))
                    inserted += 1
            conn.commit()
        except Exception as exc:
            conn.rollback()
            errors += 1
            with conn.cursor() as cur:
                cur.execute("INSERT INTO upload_row_events (batch_id,row_number,row_hash,status,message) VALUES (%s,%s,%s,'invalid',%s)", (batch_id, idx, None, str(exc)))
            conn.commit()
    return {"total": total, "inserted": inserted, "duplicate": duplicate, "errors": errors}


def list_batches(conn, limit: int = 100, offset: int = 0):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id,filename,uploaded_by,uploaded_at,input_source,status,total_rows,inserted_rows,duplicate_rows,error_rows,notes FROM upload_batches ORDER BY uploaded_at DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        return list(cur.fetchall())


def get_batch_detail(conn, batch_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM upload_batches WHERE id=%s", (batch_id,))
        batch = cur.fetchone()
        if not batch:
            return None, []
        cur.execute(
            "SELECT id,row_number,raw_row_id,row_hash,status,message,created_at FROM upload_row_events WHERE batch_id=%s ORDER BY id ASC LIMIT 500",
            (batch_id,),
        )
        events = list(cur.fetchall())
        return batch, events


def list_raw_rows(conn, search: str = "", limit: int = 100, offset: int = 0):
    with conn.cursor() as cur:
        if search:
            like = f"%{search.strip().lower()}%"
            cur.execute(
                "SELECT id,first_batch_id,last_seen_batch_id,seen_count,nama_raw,merek_raw,satuan_mapped,harga_parsed,supplier_raw,tanggal_parsed,row_hash,created_at FROM raw_price_rows WHERE LOWER(COALESCE(nama_raw,'')||' '||COALESCE(merek_raw,'')||' '||COALESCE(supplier_raw,'')) LIKE %s ORDER BY id DESC LIMIT %s OFFSET %s",
                (like, limit, offset),
            )
        else:
            cur.execute(
                "SELECT id,first_batch_id,last_seen_batch_id,seen_count,nama_raw,merek_raw,satuan_mapped,harga_parsed,supplier_raw,tanggal_parsed,row_hash,created_at FROM raw_price_rows ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
        return list(cur.fetchall())


def count_raw_rows(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM raw_price_rows")
        return cur.fetchone()["c"]


def list_category_rules(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id,keyword,category,subcategory,priority,active FROM category_rules ORDER BY priority ASC, keyword ASC")
        return list(cur.fetchall())


def add_category_rule(conn, keyword: str, category: str, subcategory: str, priority: int = 100):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO category_rules (keyword,category,subcategory,priority,active) VALUES (LOWER(%s),%s,%s,%s,TRUE) ON CONFLICT (keyword) DO UPDATE SET category=EXCLUDED.category,subcategory=EXCLUDED.subcategory,priority=EXCLUDED.priority,active=TRUE",
            (keyword.strip(), category.strip(), subcategory.strip(), priority),
        )
    conn.commit()


def delete_category_rule(conn, rule_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM category_rules WHERE id=%s", (rule_id,))
    conn.commit()


def stats_summary(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM price_records")
        records = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM raw_price_rows")
        raws = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM upload_batches")
        batches = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(DISTINCT supplier_normalized) AS c FROM price_records WHERE supplier_normalized IS NOT NULL AND supplier_normalized<>''")
        suppliers = cur.fetchone()["c"]
    return {"records": records, "raws": raws, "batches": batches, "suppliers": suppliers}


def search_prices(conn, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Legacy trigram-only search (fallback when embeddings unavailable)."""
    q = normalize_search_text(query)
    if not q:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *, similarity(search_text, %s) AS match_score
            FROM price_records
            WHERE search_text %% %s OR search_text ILIKE %s
            ORDER BY effective_date DESC NULLS LAST, match_score DESC, harga ASC
            LIMIT %s
            """,
            (q, q, f"%{q}%", limit),
        )
        return list(cur.fetchall())


def search_hybrid(conn, query: str, query_embedding: List[float], limit: int = 10,
                   w_cosine: float = 0.5, w_trigram: float = 0.3, w_tsvector: float = 0.2) -> List[Dict[str, Any]]:
    """Hybrid search: cosine (embedding) + trigram + tsvector."""
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM search_hybrid(%s::vector, %s, %s, %s, %s, %s)",
            (vec_str, query, limit, w_cosine, w_trigram, w_tsvector),
        )
        return list(cur.fetchall())
