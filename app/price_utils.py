import hashlib
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

MONTHS_ID = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "ags": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12,
}
DAYS_ID = {"senin", "selasa", "rabu", "kamis", "jumat", "jum'at", "sabtu", "minggu"}

CATEGORY_RULES = [
    ("elektrikal", "cable tray", ["cable tray", "kabel tray", "tray kabel"]),
    ("elektrikal", "kabel", ["kabel", "nya", "nym", "nyy", "nyaf", "nyfgby", "nyrgby", "nymhy", "nyyhy"]),
    ("elektrikal", "mcb", ["mcb", "mccb", "rcbo", "elcb"]),
    ("elektrikal", "saklar stop kontak", ["stop kontak", "saklar", "broco"]),
    ("elektrikal", "lampu", ["lampu", "downlight", "fitting lampu"]),
    ("bahan bangunan", "semen", ["semen", "cement", "portland"]),
    ("bahan bangunan", "pasir", ["pasir"]),
    ("bahan bangunan", "bata", ["bata", "batako", "hebel"]),
    ("struktur", "besi beton", ["besi beton", "rebar", "wiremesh"]),
    ("plumbing", "pipa pvc", ["pipa pvc", "pvc"]),
    ("plumbing", "pipa", ["pipa", "conduit", "hdpe", "ppr"]),
    ("finishing", "cat", ["cat", "dulux", "nippon paint", "jotun"]),
]

COLUMN_ALIASES = {
    "no": ["no", "nomor", "no."],
    "nama": ["nama", "nama barang", "item", "item name", "barang", "deskripsi", "uraian", "material"],
    "merek": ["merek", "merk", "brand"],
    "spesifikasi": ["spesifikasi", "spec", "spek", "tipe", "type", "ukuran"],
    "satuan": ["satuan", "unit", "sat", "uom"],
    "grup": ["grup", "group", "kategori", "category", "jenis", "kelompok"],
    "harga": ["harga", "price", "harga satuan", "unit price", "hrg"],
    "supplier": ["supplier", "vendor", "toko", "penyedia", "sumber"],
    "tanggal": ["tanggal", "tgl", "date", "tanggal harga"],
    "lokasi": ["lokasi", "kota", "area", "cabang"],
    "sumber": ["sumber data", "source", "asal"],
    "keterangan": ["keterangan", "ket", "note", "notes", "catatan", "remark"],
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("×", "x").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_search_text(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"(\d+)\s*x\s*(\d+(?:[\.,]\d+)?)", lambda m: f"{m.group(1)}x{m.group(2).replace(',', '.')}", text)
    text = re.sub(r"mm\s*2|mm²", "mm2", text)
    text = re.sub(r"[^a-z0-9\.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_price_id(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value) if isinstance(value, Decimal) else value
    text = normalize_text(value)
    m = re.search(r"(?:rp\s*)?([0-9][0-9\.]*)(?:,([0-9]+))?", text)
    if not m:
        return None
    whole = m.group(1).replace(".", "")
    dec = m.group(2)
    if dec:
        return float(f"{whole}.{dec}")
    return int(whole)


def parse_indonesian_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize_text(value)
    parts = [p for p in re.split(r"\s+", text) if p not in DAYS_ID]
    text = " ".join(parts)
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{2,4})", text)
    if m and m.group(2) in MONTHS_ID:
        day = int(m.group(1)); month = MONTHS_ID[m.group(2)]; year = int(m.group(3))
        if year < 100: year += 2000
        return date(year, month, day)
    m = re.search(r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{2,4})", text)
    if m:
        day = int(m.group(1)); month = int(m.group(2)); year = int(m.group(3))
        if year < 100: year += 2000
        return date(year, month, day)
    for fmt in ("%Y-%m-%d", "%d %m %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def map_unit(value: Any) -> Tuple[str, Optional[float], Optional[str]]:
    text = normalize_text(value)
    if not text:
        return "", None, None
    m = re.search(r"roll\s*@?\s*(\d+)\s*m", text)
    if m:
        qty = int(m.group(1))
        return "meter", qty, f"roll @{qty}m converted to meter"
    if text in {"m", "mtr", "meter", "metre"}:
        return "meter", None, None
    if text in {"pcs", "pc", "buah", "unit"}:
        return "pcs", None, None
    if text in {"btg", "batang"}:
        return "batang", None, None
    if text in {"kg", "kilogram"}:
        return "kg", None, None
    if text in {"zak", "sak"}:
        return "zak", None, None
    if text in {"lbr", "lembar"}:
        return "lembar", None, None
    if text in {"ltr", "liter", "l"}:
        return "liter", None, None
    return text, None, None


def detect_category(nama: Any, group_raw: Any = "") -> Tuple[str, str, str, float]:
    group = normalize_search_text(group_raw)
    if group:
        return group, group, "excel", 1.0
    text = normalize_search_text(nama)
    for category, subcategory, keywords in CATEGORY_RULES:
        for kw in keywords:
            if normalize_search_text(kw) in text:
                return category, subcategory, f"rule:{kw}", 0.9
    return "", "", "unknown", 0.0


def detect_columns(columns: List[Any]) -> Dict[str, str]:
    mapping = {}
    norm_to_original = {normalize_text(c): c for c in columns}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in norm_to_original:
                mapping[target] = norm_to_original[alias]
                break
    return mapping


def row_hash_for(row: Dict[str, Any]) -> str:
    payload = {
        "nama": normalize_search_text(row.get("nama", "")),
        "merek": normalize_search_text(row.get("merek", "")),
        "spesifikasi": normalize_search_text(row.get("spesifikasi", "")),
        "satuan": map_unit(row.get("satuan", ""))[0],
        "grup": normalize_search_text(row.get("grup", "")),
        "harga": parse_price_id(row.get("harga", "")),
        "supplier": normalize_search_text(row.get("supplier", "")),
        "tanggal": str(parse_indonesian_date(row.get("tanggal", "")) or ""),
        "lokasi": normalize_search_text(row.get("lokasi", "")),
        "sumber": normalize_search_text(row.get("sumber", "")),
        "keterangan": normalize_search_text(row.get("keterangan", "")),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def canonical_search_text(row: Dict[str, Any]) -> str:
    return normalize_search_text(" ".join(str(row.get(k, "")) for k in ["nama", "merek", "spesifikasi", "satuan", "grup", "supplier", "keterangan"]))


def parse_supplier_text_prices(text: str, supplier: str, effective_date: Any, general_note: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    parsed_date = parse_indonesian_date(effective_date)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "rp" not in normalize_text(line) and not re.search(r"\d[\d\.]+\s*/\s*m", normalize_text(line)):
            continue
        if "—>" in line:
            left, rest = line.split("—>", 1)
        elif "->" in line:
            left, rest = line.split("->", 1)
        elif "—" in line:
            left, rest = line.split("—", 1)
        elif "-" in line:
            left, rest = line.split("-", 1)
        else:
            continue
        item_name = left.strip()
        alias_note = ""
        if "rp" in normalize_text(rest):
            before_price = re.split(r"(?i)rp\s*|\d[\d\.]+\s*/\s*m", rest, maxsplit=1)[0].strip()
            if before_price:
                alias_note = before_price
        price_matches = list(re.finditer(r"(?i)(rp\s*)?([0-9][0-9\.]*)(?:,([0-9]+))?\s*/\s*(roll\s*@?\s*\d+\s*m|m|meter)\s*(?:\(([^)]*)\))?", rest))
        line_entries = []
        for idx, m in enumerate(price_matches):
            price_raw = m.group(0).strip()
            price = parse_price_id(price_raw)
            unit_raw = m.group(4)
            unit, factor, conv_note = map_unit(unit_raw)
            if factor and price is not None:
                price = price / factor
                if float(price).is_integer():
                    price = int(price)
            paren = (m.group(5) or "").strip()
            brand = ""; extra_note = ""; inferred = False
            if paren:
                pnorm = normalize_text(paren)
                if pnorm in {"supreme", "kabelindo"}:
                    brand = pnorm
                else:
                    extra_note = paren
            line_entries.append({"idx": idx, "price_raw": price_raw, "harga": price, "unit_raw": unit_raw, "unit": unit, "conv_note": conv_note, "merek": brand, "extra_note": extra_note, "brand_inferred": inferred})
        if len(line_entries) >= 2 and not line_entries[0]["merek"] and line_entries[1]["merek"] == "kabelindo":
            line_entries[0]["merek"] = "supreme"
            line_entries[0]["brand_inferred"] = True
        for entry in line_entries:
            notes = [n for n in [alias_note, entry["extra_note"], f"harga asli {entry['price_raw']}", entry["conv_note"], general_note] if n]
            cat, sub, cat_source, conf = detect_category(item_name, "")
            rows.append({
                "nama": item_name,
                "merek": entry["merek"],
                "spesifikasi": "",
                "satuan": entry["unit"],
                "satuan_raw": entry["unit_raw"],
                "grup": sub or cat,
                "category": cat,
                "subcategory": sub,
                "category_source": cat_source,
                "category_confidence": conf,
                "harga": entry["harga"],
                "harga_raw": entry["price_raw"],
                "supplier": supplier,
                "tanggal": parsed_date,
                "keterangan": "; ".join(notes),
                "brand_inferred": entry["brand_inferred"],
                "raw_line": raw_line,
            })
    return rows
