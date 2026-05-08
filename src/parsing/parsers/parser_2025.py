import re
import logging
from datetime import datetime
import pandas as pd
import pdfplumber
from pathlib import Path
from ..base import ParserStrategy
from ..utils import (
    normalize_name,
    normalize_course_name,
    find_header_row,
    cell,
    cells_between,
)

logger = logging.getLogger(__name__)


class Parser2025(ParserStrategy):

    _COL_DEFS = [
        ("rank", ["Rank"]),
        ("dos", ["Dos"]),
        ("nom", ["Nom"]),
        ("sexe", ["Sexe", "exe"]),
        ("club", ["Club"]),
        ("cat", ["Cat"]),
        ("rank_cat", ["Pl/Cat"]),
        ("temps", ["Temps"]),
    ]

    _TABLE_SETTINGS = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
    }

    @staticmethod
    def can_handle(full_text: str) -> bool:
        return (
            "goaltiming.be" in full_text.lower()
            and "Rank" in full_text
            and "Nom" in full_text
        )
    
    def _extract_date(self, filename):
        raw_date = filename[:8]

        try:
            if any(x in filename for x in ["Clavier", "solier"]):
                dt = datetime.strptime(raw_date, "%Y%d%m")
            else:
                dt = datetime.strptime(raw_date, "%Y%m%d")
            return datetime(dt.year, dt.month, dt.day)
        except Exception as e:
            logger.warning(f"Date parsing error for {filename}: {e}")
            return None

    def _extract_meta(self, text):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        raw = lines[0] if lines else "Inconnu"

        name = normalize_course_name(raw)

        dist_match = re.search(r"([\d.,]+)\s*km", text.lower())
        dist = float(dist_match.group(1).replace(",", ".")) if dist_match else 0

        return name, dist

    def _extract_expected(self, text: str) -> int:
        match = re.search(r"Nombre de class[ée]s\s*:\s*(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _fallback_parse_line(self, line, name, date, dist):
        parts = line.split()

        if len(parts) < 8:
            return None

        if not parts[0].isdigit():
            return None

        try:
            rank = parts[0]
            sexe = parts[4]

            # trouver le temps
            temps_idx = None
            for i, p in enumerate(parts):
                if re.match(r"\d{2}:\d{2}:\d{2}", p):
                    temps_idx = i
                    break

            if temps_idx is None:
                return None

            temps = parts[temps_idx]

            # trouver la catégorie dynamiquement
            cat = None
            cat_idx = None

            for i in range(5, temps_idx):
                if re.match(r"^(SH|SD|V\d|A\d|ESF|ESH|JH|JF)$", parts[i]):
                    cat = parts[i]
                    cat_idx = i
                    rank_category = parts[i+1]
                    break

            if not cat:
                return None

            # club = entre sexe et catégorie
            club_parts = parts[5:cat_idx]
            club = normalize_name(" ".join(club_parts))

            if club in ("*", "-"):
                club = ""

            nom = normalize_name(" ".join(parts[2:4]))

            return {
                "Position": rank,
                "Nom": nom,
                "Club": club,
                "Sexe": sexe,
                "Categorie": cat,
                "Position Catégorie": rank_category,
                "Temps": temps,
                "NomCourse": name,
                "Date": date,
                "Distance": dist,
            }

        except Exception as e:
            logger.warning(f"Fallback error: {line} -> {e}")
            return None

    def parse(self, pdf_path: str | Path) -> tuple[pd.DataFrame, dict]:
        filename = pdf_path.name
        date = self._extract_date(filename)
        rows = []

        with pdfplumber.open(pdf_path) as pdf:
            first_text = pdf.pages[0].extract_text() or ""
            name, dist = self._extract_meta(first_text)
            expected = self._extract_expected(first_text)

            last_mapping = {}

            for page in pdf.pages:
                tables = page.extract_tables(self._TABLE_SETTINGS)

                parsed_on_page = False

                # =========================
                # TABLE PARSING (principal)
                # =========================
                if tables and not all(len(t) == 0 for t in tables):
                    for table in tables:
                        header_idx, mapping = find_header_row(table, self._COL_DEFS)

                        if header_idx < 0:
                            if not last_mapping:
                                continue
                            mapping = last_mapping
                            data_rows = table
                        else:
                            last_mapping = mapping
                            data_rows = table[header_idx + 1:]

                        for row in data_rows:
                            rank = cell(row, mapping.get("rank"))
                            if not rank or not rank.isdigit():
                                continue

                            temps = cell(row, mapping.get("temps"))
                            if not temps or not re.match(r"\d{2}:\d{2}:\d{2}", temps):
                                continue

                            sexe = cell(row, mapping.get("sexe"))
                            cat = cell(row, mapping.get("cat"))
                            rank_category = cell(row, mapping.get("rank_cat"))

                            nom = normalize_name(cells_between(row, mapping, "nom", "sexe"))
                            club = normalize_name(cells_between(row, mapping, "club", "cat"))

                            if club in ("*", "-"):
                                club = ""

                            rows.append({
                                "Position": rank,
                                "Nom": nom,
                                "Club": club,
                                "Sexe": sexe,
                                "Categorie": cat,
                                "Position Catégorie": rank_category,
                                "Temps": temps,
                                "NomCourse": name,
                                "Date": date,
                                "Distance": dist,
                            })

                            parsed_on_page = True

                # =========================
                # FALLBACK TEXTE
                # =========================
                if not parsed_on_page:
                    text = page.extract_text() or ""

                    for line in text.splitlines():
                        line = line.strip()

                        if not line or not line[0].isdigit():
                            continue

                        parsed = self._fallback_parse_line(line, name, date, dist)
                        if parsed:
                            rows.append(parsed)

        df = pd.DataFrame(rows)

        metadata = {
            "expected_count": expected,
            "parsed_count": len(df)
        }

        logger.info(
            f"{pdf_path.name}: parsed={len(df)} expected={expected}"
        )

        return df, metadata