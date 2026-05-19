from datetime import date

from price_utils import (
    detect_category,
    map_unit,
    normalize_text,
    parse_indonesian_date,
    parse_price_id,
    row_hash_for,
)


def test_parse_price_id_indonesian_formats():
    assert parse_price_id("Rp 25.000") == 25000
    assert parse_price_id("1.250.000") == 1250000
    assert parse_price_id("1.250.000,50") == 1250000.50
    assert parse_price_id("769.800/m") == 769800


def test_parse_indonesian_date_formats():
    assert parse_indonesian_date("3 Desember 2026") == date(2026, 12, 3)
    assert parse_indonesian_date("3-12-26") == date(2026, 12, 3)
    assert parse_indonesian_date("Jumat 8 Mei 2026") == date(2026, 5, 8)


def test_map_unit_and_roll_conversion():
    assert map_unit("m") == ("meter", None, None)
    assert map_unit("mtr") == ("meter", None, None)
    assert map_unit("roll @100m") == ("meter", 100, "roll @100m converted to meter")


def test_detect_category_keywords():
    category, subcategory, source, confidence = detect_category("Kabel NYY 3x4 Supreme", "")
    assert category == "elektrikal"
    assert subcategory == "kabel"
    assert confidence >= 0.8

    category, subcategory, source, confidence = detect_category("Semen Gresik", "")
    assert category == "bahan bangunan"
    assert subcategory == "semen"


def test_row_hash_normalizes_case_spacing_price_date():
    a = {
        "nama": " Kabel NYY 3x4 ",
        "merek": "SUPREME",
        "satuan": "m",
        "harga": "Rp 25.000",
        "supplier": "Pusat Listrik",
        "tanggal": "3 Desember 2026",
        "keterangan": "Tender",
    }
    b = {
        "nama": "kabel   nyy 3x4",
        "merek": "supreme",
        "satuan": "meter",
        "harga": "25000",
        "supplier": "pusat listrik",
        "tanggal": "03/12/2026",
        "keterangan": "tender",
    }
    assert row_hash_for(a) == row_hash_for(b)
