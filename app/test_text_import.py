from price_utils import parse_supplier_text_prices


SAMPLE = """
Kabel NYA 1.5 mm — Rp 413.000/roll @100m (supreme) / Rp 402.000/roll @100m (kabelindo)
Kabel NYY 3x4 mm — Rp 45.400/m / Rp 42.300/m (kabelindo)
Kabel NYM 3x4 mm — Rp 37.700/m (minimal order kelipatan 50m)
Kabel NYYHY 3x2.5 mm —> NYMHY Black 3x2.5mm Rp 28.000/m (supreme)
"""


def test_parse_supplier_text_converts_roll_and_splits_brands():
    rows = parse_supplier_text_prices(
        SAMPLE,
        supplier="Sinar Surabaya Sakti",
        effective_date="Jumat 8 Mei 2026",
        general_note="harga include PPN, tidak mengikat",
    )
    assert len(rows) == 6
    first = rows[0]
    assert first["nama"] == "Kabel NYA 1.5 mm"
    assert first["merek"] == "supreme"
    assert first["harga"] == 4130
    assert first["satuan"] == "meter"
    assert "Rp 413.000/roll @100m" in first["keterangan"]


def test_parse_supplier_text_infers_first_brand_when_second_is_kabelindo():
    rows = parse_supplier_text_prices(
        "Kabel NYY 3x4 mm — Rp 45.400/m / Rp 42.300/m (kabelindo)",
        supplier="Sinar Surabaya Sakti",
        effective_date="8 Mei 2026",
        general_note="",
    )
    assert rows[0]["merek"] == "supreme"
    assert rows[0]["brand_inferred"] is True
    assert rows[0]["harga"] == 45400
    assert rows[1]["merek"] == "kabelindo"


def test_parse_supplier_text_keeps_minimal_order_note():
    rows = parse_supplier_text_prices(
        "Kabel NYM 3x4 mm — Rp 37.700/m (minimal order kelipatan 50m)",
        supplier="Sinar Surabaya Sakti",
        effective_date="8 Mei 2026",
        general_note="",
    )
    assert rows[0]["merek"] == ""
    assert "minimal order kelipatan 50m" in rows[0]["keterangan"]
