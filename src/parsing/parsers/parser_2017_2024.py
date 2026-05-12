import re
import logging
import pandas as pd
import pdfplumber

from pathlib import Path
from ..base import ParserStrategy
from ..utils import (
    extract_year,
    extract_distance,
    normalize_name,
    normalize_course_name,
    sex_from_category,
    extract_date
)

logger = logging.getLogger(__name__)

class Parser2017_2024(ParserStrategy):

    @staticmethod
    def can_handle(full_text: str) -> bool:
        year = extract_year(full_text)
        dist = extract_distance(full_text)
        return year in [i for i in range(2016, 2025)] and dist > 2 and 'http' in full_text
    
    def _extract_name(self, text):
        name_match = re.search(
            r"\n([^\n]+?)\s+DISTANCE",
            text,
            re.IGNORECASE
        )

        name = "UNKNOWN"
        if name_match:
            line = name_match.group(1)

            name = re.split(r"\s+(?:DA|A\d|SE|V\d|ED|EH|ESF|ESP|JUF|JUH|SEF|SD)\s*:", line)[0].strip()

        return normalize_course_name(name)
    
    def _extract_expected(self, text: str) -> int:
        match = re.search(r"Nombre de participants arriv[é]s\s*:\s*(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None
    
    def parse(self, pdf_path: str | Path) -> tuple[pd.DataFrame, dict]:
        rows = []
        
        with pdfplumber.open(pdf_path) as pdf:
            first_text = pdf.pages[0].extract_text() or ""
            name = self._extract_name(first_text)
            date =  extract_date(first_text)
            dist = extract_distance(first_text)
            expected = self._extract_expected(first_text)

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        rank = row[0]
                        if not rank.isdigit():
                            continue

                        temps = row[6]
                        # si la colonne n'est pas une colonne de temps
                        if not re.match(r"\d{1,2}:\d{2}:\d{2}", temps):
                            # c'est un score et il faut décaller
                            temps = row[7]

                        cat = row[4]
                        if cat == '1':
                            continue
                        rank_category = row[5]
                        nom = normalize_name(row[2])
                        if not nom or nom == "0" or "/" in nom:
                            continue
                        club = normalize_name(row[3])
                        sex = sex_from_category(cat)

                        if club == "*" or club =="-":
                            club = ""

                        rows.append({
                            "Position": rank,
                            "Nom": nom,
                            "Club": club,
                            "Sexe": sex,
                            "Categorie": cat,
                            "Position Catégorie": rank_category,
                            "Temps": temps,
                            "NomCourse": name,
                            "Date": date,
                            "Distance": dist,
                        })

        df = pd.DataFrame(rows)
        
        metadata = {
                "expected_count": expected,
                "parsed_count": len(df)
        }

        logger.info(
                f"{pdf_path.name}: parsed={len(df)} expected={expected}"
        )

        return df, metadata