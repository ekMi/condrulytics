import re
from datetime import datetime
import unicodedata
from pathlib import Path
import pdfplumber


CAT_MEN  = re.compile(r"^(E?SH|JH|V\d+|SE|EH|SEN|V\d+H|VE\d+|SEH|JUH|ESP|H|GAR|DISH)$")
CAT_WOMEN = re.compile(r"^(E?SF|JF|SD|A\d+|DA|JUF|AI\d+|DAM|SEF|EF|V\d+F|F|FIL|ED|DISF)$")

MONTH = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12
}

def extract_year(text: str):
    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    return int(year_match.group(1)) if year_match else 0


def extract_distance(text: str):
    dist_match = re.search(r"([\d.,]+)\s*km", text.lower())
    return float(dist_match.group(1).replace(",", ".")) if dist_match else 0


def normalize_course_name(raw: str) -> str:
    name = re.sub(r"\b20\d{2}\b", "", raw)
    name = re.sub(r"\s+", " ", name).strip().title()
    name = unicodedata.normalize("NFD", name)
    return "".join(c for c in name if unicodedata.category(c) != "Mn")


def normalize_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw).strip().title()
    name = unicodedata.normalize("NFD", name)
    return "".join(c for c in name if unicodedata.category(c) != "Mn")


def ascii_lower(text: str) -> str:
    if text is None:
        return ""
    return text.encode("ascii", "ignore").decode("ascii").lower().strip()


def extract_full_text(pdf_path: str | Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
    

def sex_from_category(cat: str) -> str:
    if CAT_MEN.match(cat):
        return "H"
    if CAT_WOMEN.match(cat):
        return "F"
    return "X"


def extract_date(text: str):
    pattern = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})"

    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        jour = int(match.group(1))
        mois_num = MONTH[match.group(2).lower()]
        annee = int(match.group(3))

        date = datetime(annee, mois_num, jour)
        return date

def cell(row, idx):
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def find_header_indices(row, col_defs):
    mapping = {}
    cells = [ascii_lower(c) for c in row]

    for col_name, keywords in col_defs:
        for i, cell_value in enumerate(cells):
            if cell_value and any(ascii_lower(k) in cell_value for k in keywords):
                mapping[col_name] = i
                break

    return mapping


def find_header_row(table, col_defs, min_matches=3):
    for i, row in enumerate(table):
        mapping = find_header_indices(row, col_defs)
        if len(mapping) >= min_matches:
            return i, mapping
    return -1, {}


def cells_between(row, mapping, start_col, end_col):
    i_start = mapping.get(start_col)
    i_end = mapping.get(end_col)

    if i_start is None:
        return ""

    if i_end is None or i_end <= i_start:
        return cell(row, i_start)

    parts = [(row[i] or "").strip() for i in range(i_start, i_end) if i < len(row)]
    parts = [p for p in parts if p]

    if not parts:
        return ""

    result = parts[0]
    for p in parts[1:]:
        sep = "" if p[0].islower() else " "
        result += sep + p

    return result.strip()