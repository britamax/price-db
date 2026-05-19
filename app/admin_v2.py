"""Admin v2: Phase 3 UI routes — Search Playground, Alias Manager, Material Browser, Audit.

Wired into main.py via include_router. Uses existing page() helper + require_admin_cookie.
"""

from __future__ import annotations

import html
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/admin")


# ──────────────────────────────────────────────────────────────────
# Helpers to embed HTMX/Alpine (CDN, no build pipeline)
# ──────────────────────────────────────────────────────────────────
HTMX_SCRIPT = '<script src="https://unpkg.com/htmx.org@1.9.12"></script>'
ALPINE_SCRIPT = '<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>'
CHART_SCRIPT = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1"></script>'


def _nav_v2() -> str:
    """Extended nav with Phase 3 pages."""
    return (
        '<a href="/admin/batches">Batches</a>'
        '<a href="/admin/search">Search Playground</a>'
        '<a href="/admin/aliases">Aliases</a>'
        '<a href="/admin/materials">Materials</a>'
        '<a href="/admin/audit">Audit Log</a>'
        '<a href="/admin/raw">Raw Rows</a>'
        '<a href="/admin/rules">Kategori</a>'
        '<a href="/admin/upload">Upload</a>'
        '<a href="/admin/text-import">Import Teks</a>'
        '<a href="/admin/logout">Logout</a>'
    )


def _page(title: str, body: str, extra_head: str = "") -> str:
    """Variant of page() with extended nav + extra head scripts."""
    return f"""
    <!doctype html><html lang="id"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(title)}</title>
    {HTMX_SCRIPT}{ALPINE_SCRIPT}{extra_head}
    <style>
      body {{ font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
      .wrap {{ max-width:1400px; margin:auto; }}
      .card {{ background:#111827; border:1px solid #334155; border-radius:14px; padding:20px; margin:0 0 16px; box-shadow:0 10px 30px #0005; }}
      h1,h2 {{ color:#38bdf8; margin-top:0; }}
      h3 {{ color:#7dd3fc; }}
      a {{ color:#7dd3fc; }}
      input, textarea, select {{ box-sizing:border-box; padding:8px 10px; margin:4px 0; border-radius:8px; border:1px solid #475569; background:#020617; color:#e2e8f0; }}
      input[type="text"], input[type="number"], input[type="search"], textarea, select {{ width:100%; }}
      button {{ background:#0ea5e9; color:white; border:0; padding:8px 14px; border-radius:8px; cursor:pointer; font-weight:bold; }}
      button.warn {{ background:#f97316; }} button.danger {{ background:#dc2626; }} button.ghost {{ background:#1e293b; color:#7dd3fc; }}
      table {{ width:100%; border-collapse:collapse; font-size:13px; }}
      th,td {{ border-bottom:1px solid #334155; padding:8px; vertical-align:top; }}
      th {{ text-align:left; color:#93c5fd; position:sticky; top:0; background:#111827; }}
      tr:hover {{ background:#0b1220; }}
      .muted {{ color:#94a3b8; font-size:12px; }} .ok {{ color:#86efac; }} .warn {{ color:#fde68a; }} .err {{ color:#fca5a5; }}
      .nav {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }}
      .nav a {{ background:#1e293b; padding:6px 10px; border-radius:8px; text-decoration:none; font-size:13px; }}
      .nav a:hover {{ background:#334155; }}
      .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; }}
      .pill.ok {{ background:#064e3b; color:#bbf7d0; }} .pill.warn {{ background:#713f12; color:#fde68a; }} .pill.err {{ background:#7f1d1d; color:#fecaca; }}
      .grid {{ display:grid; gap:14px; }}
      .grid-2 {{ grid-template-columns:1fr 1fr; }} .grid-3 {{ grid-template-columns:repeat(3,1fr); }}
      @media (max-width:720px) {{ .grid-2, .grid-3 {{ grid-template-columns:1fr; }} }}
      .bar-bg {{ display:inline-block; background:#1e293b; height:6px; border-radius:3px; vertical-align:middle; width:60px; overflow:hidden; }}
      .bar-fg {{ height:100%; background:#38bdf8; }}
      .bar-fg.cos {{ background:#34d399; }} .bar-fg.tri {{ background:#fbbf24; }} .bar-fg.ts {{ background:#a78bfa; }}
      .badge {{ font-size:10px; padding:1px 6px; border-radius:4px; background:#1e293b; color:#7dd3fc; }}
      code {{ background:#020617; padding:2px 6px; border-radius:6px; font-size:12px; }}
      .htmx-indicator {{ opacity:0; transition:opacity 200ms; color:#fbbf24; }}
      .htmx-request .htmx-indicator {{ opacity:1; }}
      .htmx-request.htmx-indicator {{ opacity:1; }}
      details summary {{ cursor:pointer; color:#fbbf24; }}
    </style></head><body><div class="wrap">
    <div class="nav"><a href="/">Search</a>{_nav_v2()}<a href="/health">Health</a></div>
    {body}
    </div></body></html>
    """


def _bar(value: float, color: str = "cos") -> str:
    """Render a 0..1 progress bar."""
    pct = max(0, min(100, int((value or 0) * 100)))
    return f'<span class="bar-bg"><span class="bar-fg {color}" style="width:{pct}%"></span></span> <span class="muted">{value:.2f}</span>'


def _fmt_rp(n) -> str:
    try:
        return f"Rp {float(n):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


# ──────────────────────────────────────────────────────────────────
# Task 3.3 — Search Playground
# ──────────────────────────────────────────────────────────────────
def register_routes(app, get_conn, require_admin_cookie, search_hybrid, embed_single):
    """Register routes on the app instance. Called from main.py at startup."""

    @app.get("/admin/search", response_class=HTMLResponse)
    def admin_search_playground(_: bool = Depends(require_admin_cookie)):
        body = """
        <div class="card">
          <h1>🔍 Search Playground</h1>
          <p class="muted">Test hybrid search dengan score breakdown. Edit bobot untuk lihat efek real-time.</p>
          <form hx-get="/admin/search/run" hx-target="#results" hx-indicator="#spin">
            <div class="grid grid-2">
              <div>
                <label>Query</label>
                <input type="text" name="q" placeholder="kabel listrik 4 mm" autofocus required>
              </div>
              <div>
                <label>Limit</label>
                <input type="number" name="limit" value="10" min="1" max="50">
              </div>
            </div>
            <details>
              <summary>⚙️ Tuning bobot (cosine / trigram / tsvector)</summary>
              <div class="grid grid-3">
                <div><label>w_cosine</label><input type="number" name="w_cos" value="0.4" step="0.1" min="0" max="1"></div>
                <div><label>w_trigram</label><input type="number" name="w_tri" value="0.6" step="0.1" min="0" max="1"></div>
                <div><label>w_tsvector</label><input type="number" name="w_ts" value="0.0" step="0.1" min="0" max="1"></div>
              </div>
              <p class="muted">Default: cos=0.4, tri=0.6, ts=0.0 (tuned via grid search). Total tidak harus = 1.</p>
            </details>
            <button type="submit">Search</button>
            <span id="spin" class="htmx-indicator">⏳ embedding query...</span>
          </form>
        </div>
        <div id="results"></div>
        """
        return HTMLResponse(_page("Search Playground", body))

    @app.get("/admin/search/run", response_class=HTMLResponse)
    def admin_search_run(
        q: str = "",
        limit: int = 10,
        w_cos: float = 0.4,
        w_tri: float = 0.6,
        w_ts: float = 0.0,
        _: bool = Depends(require_admin_cookie),
    ):
        q = (q or "").strip()
        if not q:
            return HTMLResponse('<div class="card err">Query kosong.</div>')

        try:
            emb = embed_single(q)
        except Exception as e:
            return HTMLResponse(f'<div class="card err">Embedding error: {html.escape(str(e))}</div>')

        with get_conn() as conn:
            results = search_hybrid(conn, q, emb, max(1, min(limit, 50)),
                                    w_cosine=w_cos, w_trigram=w_tri, w_tsvector=w_ts)

        if not results:
            return HTMLResponse('<div class="card warn">Tidak ada hasil.</div>')

        rows_html = ""
        for i, r in enumerate(results, 1):
            cos = r.get("cosine_sim", 0) or 0
            tri = r.get("trigram_sim", 0) or 0
            ts = r.get("ts_rank", 0) or 0
            score = r.get("score", 0) or 0
            canon_unit = r.get("canonical_unit") or r.get("satuan") or ""
            ppc = r.get("price_per_canonical_unit")
            ppc_str = _fmt_rp(ppc) + f"/{canon_unit}" if ppc and canon_unit else "-"
            rows_html += f"""
            <tr>
              <td>{i}</td>
              <td><b>{html.escape(r['nama'] or '')}</b><br><span class="muted">{html.escape(r.get('merek') or '')} · {html.escape(r.get('category') or '')}</span></td>
              <td>{html.escape(r.get('satuan') or '')}</td>
              <td>{_fmt_rp(r.get('harga'))}<br><span class="muted">{ppc_str}</span></td>
              <td>{html.escape(r.get('supplier') or '')}<br><span class="muted">{html.escape(str(r.get('effective_date') or ''))}</span></td>
              <td><b style="color:#38bdf8">{score:.3f}</b></td>
              <td>{_bar(cos, 'cos')}<br><span class="muted">cos</span></td>
              <td>{_bar(tri, 'tri')}<br><span class="muted">tri</span></td>
              <td>{_bar(ts, 'ts')}<br><span class="muted">ts</span></td>
            </tr>
            """

        # Optionally show alias expansion info
        try:
            from aliases import expand_aliases
            with get_conn() as conn:
                expanded = expand_aliases(q, conn=conn)
            expansion_html = ""
            if expanded.lower() != q.lower():
                expansion_html = f'<div class="muted">📝 Query expanded: <code>{html.escape(q)}</code> → <code>{html.escape(expanded)}</code></div>'
            else:
                expansion_html = '<div class="muted">📝 No alias expansion applied.</div>'
        except Exception:
            expansion_html = ""

        return HTMLResponse(f"""
        <div class="card">
          <h2>Hasil ({len(results)})</h2>
          {expansion_html}
          <table>
            <thead><tr><th>#</th><th>Material</th><th>Satuan</th><th>Harga</th><th>Supplier · Tgl</th><th>Score</th><th>Cosine</th><th>Trigram</th><th>TS</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """)

    # ──────────────────────────────────────────────────────────────────
    # Task 3.4 — Alias Manager
    # ──────────────────────────────────────────────────────────────────
    @app.get("/admin/aliases", response_class=HTMLResponse)
    def admin_aliases(q: str = "", kind: str = "", _: bool = Depends(require_admin_cookie)):
        with get_conn() as conn:
            with conn.cursor() as cur:
                where = []
                params = []
                if q:
                    where.append("(variant ILIKE %s OR canonical ILIKE %s)")
                    params.extend([f"%{q}%", f"%{q}%"])
                if kind:
                    where.append("kind = %s")
                    params.append(kind)
                where_sql = ("WHERE " + " AND ".join(where)) if where else ""
                cur.execute(
                    f"SELECT id, variant, canonical, kind, confidence, created_by, created_at "
                    f"FROM alias {where_sql} ORDER BY kind, variant LIMIT 200",
                    tuple(params),
                )
                aliases = cur.fetchall()
                cur.execute("SELECT kind, count(*) AS n FROM alias GROUP BY kind ORDER BY kind")
                counts = cur.fetchall()

        counts_html = " · ".join(f"{c['kind']}: <b>{c['n']}</b>" for c in counts) or "Empty"

        rows = ""
        for a in aliases:
            rows += f"""
            <tr id="alias-row-{a['id']}">
              <td><code>{html.escape(a['variant'])}</code></td>
              <td>→</td>
              <td><b>{html.escape(a['canonical'])}</b></td>
              <td><span class="badge">{a['kind']}</span></td>
              <td>{a['confidence']:.2f}</td>
              <td class="muted">{html.escape(a.get('created_by') or '')}</td>
              <td>
                <button class="danger"
                        hx-post="/admin/aliases/{a['id']}/delete"
                        hx-target="#alias-row-{a['id']}"
                        hx-swap="outerHTML"
                        hx-confirm="Hapus alias '{html.escape(a['variant'])}'?">×</button>
              </td>
            </tr>
            """

        body = f"""
        <div class="card">
          <h1>🔤 Alias Manager</h1>
          <p class="muted">Counts: {counts_html}</p>
          <p class="muted">Setelah edit alias, jalankan <code>docker exec price-db-web python apply_aliases.py</code> untuk re-embed corpus.</p>
          <form hx-post="/admin/aliases/add" hx-target="#alias-add-result">
            <div class="grid grid-3">
              <div><label>Variant (apa yang user ketik)</label><input type="text" name="variant" placeholder="kabel listrik" required></div>
              <div><label>Canonical (target)</label><input type="text" name="canonical" placeholder="kabel nya" required></div>
              <div><label>Kind</label>
                <select name="kind">
                  <option value="material">material</option>
                  <option value="unit">unit</option>
                  <option value="brand">brand</option>
                </select>
              </div>
            </div>
            <div class="grid grid-2">
              <div><label>Confidence (0.0 - 1.0)</label><input type="number" name="confidence" value="1.0" step="0.05" min="0" max="1"></div>
              <div style="display:flex;align-items:end"><button type="submit">+ Tambah Alias</button></div>
            </div>
          </form>
          <div id="alias-add-result"></div>
        </div>

        <div class="card">
          <form hx-get="/admin/aliases" hx-trigger="input changed delay:300ms from:input[name=q], change from:select[name=kind]" hx-target="body" hx-swap="outerHTML">
            <div class="grid grid-2">
              <input type="search" name="q" value="{html.escape(q)}" placeholder="Filter variant/canonical...">
              <select name="kind">
                <option value="">— Semua kind —</option>
                <option value="material" {'selected' if kind=='material' else ''}>material</option>
                <option value="unit" {'selected' if kind=='unit' else ''}>unit</option>
                <option value="brand" {'selected' if kind=='brand' else ''}>brand</option>
              </select>
            </div>
          </form>
          <table>
            <thead><tr><th>Variant</th><th></th><th>Canonical</th><th>Kind</th><th>Conf</th><th>By</th><th></th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p class="muted">Showing {len(aliases)} of {sum(c['n'] for c in counts)} aliases (max 200).</p>
        </div>
        """
        return HTMLResponse(_page("Alias Manager", body))

    @app.post("/admin/aliases/add", response_class=HTMLResponse)
    def admin_aliases_add(
        variant: str = Form(...), canonical: str = Form(...), kind: str = Form(...),
        confidence: float = Form(1.0), _: bool = Depends(require_admin_cookie),
    ):
        variant = (variant or "").strip().lower()
        canonical = (canonical or "").strip().lower()
        if not variant or not canonical:
            return HTMLResponse('<div class="err">Variant dan canonical harus diisi.</div>')
        if kind not in ("material", "unit", "brand"):
            return HTMLResponse('<div class="err">Kind invalid.</div>')

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO alias (variant, canonical, kind, confidence, created_by) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (variant, kind) DO UPDATE SET canonical = EXCLUDED.canonical, confidence = EXCLUDED.confidence "
                    "RETURNING id",
                    (variant, canonical, kind, confidence, "admin-ui"),
                )
                new_id = cur.fetchone()["id"]
                # audit log
                cur.execute(
                    "INSERT INTO audit_log (actor, action, entity_type, entity_id, after) VALUES (%s, %s, %s, %s, %s::jsonb)",
                    ("admin-ui", "alias_add", "alias", new_id,
                     json.dumps({"variant": variant, "canonical": canonical, "kind": kind, "confidence": confidence})),
                )
        # Reload cache
        try:
            from aliases import reload_aliases
            with get_conn() as conn:
                reload_aliases(conn)
        except Exception:
            pass

        return HTMLResponse(f'<div class="ok">✓ Alias <code>{html.escape(variant)}</code> → <code>{html.escape(canonical)}</code> ditambahkan. <a href="/admin/aliases">Refresh</a></div>')

    @app.post("/admin/aliases/{alias_id}/delete", response_class=HTMLResponse)
    def admin_aliases_delete(alias_id: int, _: bool = Depends(require_admin_cookie)):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT variant, canonical, kind FROM alias WHERE id = %s", (alias_id,))
                row = cur.fetchone()
                if row:
                    cur.execute("DELETE FROM alias WHERE id = %s", (alias_id,))
                    cur.execute(
                        "INSERT INTO audit_log (actor, action, entity_type, entity_id, before) VALUES (%s, %s, %s, %s, %s::jsonb)",
                        ("admin-ui", "alias_delete", "alias", alias_id, json.dumps(dict(row))),
                    )
        try:
            from aliases import reload_aliases
            with get_conn() as conn:
                reload_aliases(conn)
        except Exception:
            pass
        return HTMLResponse("")  # row removed

    # ──────────────────────────────────────────────────────────────────
    # Task 3.6 — Material Browser
    # ──────────────────────────────────────────────────────────────────
    @app.get("/admin/materials", response_class=HTMLResponse)
    def admin_materials(q: str = "", _: bool = Depends(require_admin_cookie)):
        with get_conn() as conn:
            with conn.cursor() as cur:
                where = "WHERE 1=1"
                params: list = []
                if q:
                    where += " AND nama ILIKE %s"
                    params.append(f"%{q}%")
                cur.execute(f"""
                    SELECT nama,
                           count(*) AS n_entries,
                           min(harga) AS min_h,
                           max(harga) AS max_h,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY harga) AS median_h,
                           max(effective_date) AS last_date,
                           max(canonical_unit) AS canonical_unit,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY price_per_canonical_unit) AS median_ppc
                    FROM price_records
                    {where}
                    GROUP BY nama
                    ORDER BY count(*) DESC, nama
                    LIMIT 200
                """, tuple(params))
                materials = cur.fetchall()

        rows = ""
        for m in materials:
            ppc_str = _fmt_rp(m['median_ppc']) + f"/{m['canonical_unit']}" if m['median_ppc'] and m['canonical_unit'] else "-"
            rows += f"""
            <tr>
              <td><a href="/admin/materials/{html.escape(m['nama'])}"><b>{html.escape(m['nama'])}</b></a></td>
              <td>{m['n_entries']}</td>
              <td>{_fmt_rp(m['min_h'])}</td>
              <td><b>{_fmt_rp(m['median_h'])}</b></td>
              <td>{_fmt_rp(m['max_h'])}</td>
              <td>{ppc_str}</td>
              <td class="muted">{m['last_date']}</td>
            </tr>
            """

        body = f"""
        <div class="card">
          <h1>📦 Material Browser</h1>
          <form hx-get="/admin/materials" hx-target="body" hx-swap="outerHTML" hx-trigger="input changed delay:300ms">
            <input type="search" name="q" value="{html.escape(q)}" placeholder="Filter nama material...">
          </form>
        </div>
        <div class="card">
          <table>
            <thead><tr>
              <th>Material</th><th>Entries</th><th>Min</th><th>Median</th><th>Max</th><th>Median /unit canonical</th><th>Last seen</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p class="muted">Showing {len(materials)} materials (max 200).</p>
        </div>
        """
        return HTMLResponse(_page("Material Browser", body))

    @app.get("/admin/materials/{nama}", response_class=HTMLResponse)
    def admin_material_detail(nama: str, _: bool = Depends(require_admin_cookie)):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, nama, merek, supplier, harga, satuan, canonical_unit,
                           price_per_canonical_unit, effective_date, lokasi, sumber, category
                    FROM price_records
                    WHERE nama = %s
                    ORDER BY effective_date DESC NULLS LAST, id DESC
                """, (nama,))
                rows_data = cur.fetchall()

        if not rows_data:
            return HTMLResponse(_page("Material Detail", '<div class="card err">Not found.</div>'))

        history = [
            {"date": str(r['effective_date'] or ''), "price": float(r['harga'] or 0),
             "supplier": r['supplier'] or ''}
            for r in rows_data
        ]
        history_json = html.escape(json.dumps(history))

        rows_html = ""
        for r in rows_data:
            ppc = _fmt_rp(r['price_per_canonical_unit']) + f"/{r['canonical_unit']}" if r['price_per_canonical_unit'] else "-"
            rows_html += f"""
            <tr>
              <td>{r['effective_date'] or '-'}</td>
              <td>{html.escape(r['supplier'] or '')}</td>
              <td>{html.escape(r['merek'] or '')}</td>
              <td>{_fmt_rp(r['harga'])} <span class="muted">/{html.escape(r['satuan'] or '')}</span></td>
              <td>{ppc}</td>
              <td class="muted">{html.escape(r['lokasi'] or '')}</td>
            </tr>
            """

        body = f"""
        <div class="card">
          <h1>📦 {html.escape(nama)}</h1>
          <p><a href="/admin/materials">← Back to materials</a></p>
        </div>
        <div class="card">
          <h2>Price History ({len(rows_data)} entries)</h2>
          <canvas id="priceChart" height="80"></canvas>
        </div>
        <div class="card">
          <table>
            <thead><tr><th>Date</th><th>Supplier</th><th>Merk</th><th>Harga</th><th>Per canonical</th><th>Lokasi</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        <script>
          const data = {history_json};
          const ctx = document.getElementById('priceChart').getContext('2d');
          new Chart(ctx, {{
            type: 'line',
            data: {{
              labels: data.map(d => d.date),
              datasets: [{{
                label: 'Harga (Rp)',
                data: data.map(d => d.price),
                borderColor: '#38bdf8',
                backgroundColor: '#38bdf833',
                tension: 0.2,
                pointBackgroundColor: '#0ea5e9',
              }}]
            }},
            options: {{
              plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }},
              scales: {{
                x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
                y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
              }}
            }}
          }});
        </script>
        """
        return HTMLResponse(_page(f"Material: {nama}", body, extra_head=CHART_SCRIPT))

    # ──────────────────────────────────────────────────────────────────
    # Task 3.7 — Audit Log
    # ──────────────────────────────────────────────────────────────────
    @app.get("/admin/audit", response_class=HTMLResponse)
    def admin_audit(limit: int = 100, _: bool = Depends(require_admin_cookie)):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, at, actor, action, entity_type, entity_id, before, after
                    FROM audit_log
                    ORDER BY at DESC
                    LIMIT %s
                """, (min(max(1, limit), 500),))
                events = cur.fetchall()

        rows = ""
        for e in events:
            before = json.dumps(e['before'], ensure_ascii=False) if e['before'] else ""
            after = json.dumps(e['after'], ensure_ascii=False) if e['after'] else ""
            rows += f"""
            <tr>
              <td class="muted">{e['at']}</td>
              <td>{html.escape(e['actor'] or '')}</td>
              <td><span class="badge">{e['action']}</span></td>
              <td>{e['entity_type']} #{e['entity_id']}</td>
              <td><code style="font-size:11px">{html.escape(before)[:80]}</code></td>
              <td><code style="font-size:11px">{html.escape(after)[:80]}</code></td>
            </tr>
            """

        body = f"""
        <div class="card">
          <h1>📜 Audit Log</h1>
          <p class="muted">Last {len(events)} actions on alias / material / category-rule write endpoints.</p>
          <table>
            <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Before</th><th>After</th></tr></thead>
            <tbody>{rows or '<tr><td colspan="6" class="muted">No events yet.</td></tr>'}</tbody>
          </table>
        </div>
        """
        return HTMLResponse(_page("Audit Log", body))
