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

CATEGORIES = {
    "ESF", "SEF", "V1F", "V2F", "V3F",
    "V4F", "ESH", "SEH", "V1H", "V2H", "V3H",
    "V4H", "xxx", "XXX", "ED", "DA", "A1", "A2",
    "A3", "A4" ,"EH", "SE", "V1", "V2", "V3", "V4",
    "DAM", "AI1", "AI2", "AI3", "AI4", "ESP", "SEN"
}

class Parser2008_2016(ParserStrategy):

    @staticmethod
    def can_handle(full_text: str) -> bool:
        year = extract_year(full_text)
        dist = extract_distance(full_text)
        return year in [i for i in range(2008, 2017)] and dist > 2 and 'http' not in full_text
    
    def _extract_name(self, text):
        name_match = re.search(
            r"\n([^\n]+?)\s+DISTANCE",
            text
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

                        has_bib = row[1].isdigit()

                        bib = row[1] if has_bib else None
                        start = 2 if has_bib else 1

                        # colonnes fixes à droite
                        speed = row[-1]
                        pace = row[-2]
                        time = row[-3]
                        rank_category = row[-4]
                        cat = row[-5]

                        middle = row[start:-5]
                        club = None

                        if len(middle) > 1:
                            possible_club = middle[-1]

                            # si le dernier champ n'est PAS une catégorie,
                            # on considère que c'est un club
                            if possible_club not in CATEGORIES:
                                club = normalize_name(possible_club)
                                fullname = normalize_name(" ".join(middle[:-1]))
                            else:
                                fullname = normalize_name(" ".join(middle))
                        else:
                            fullname = normalize_name(middle[0])

                        if not fullname or fullname == "0":
                            continue
                        
                        sex = sex_from_category(cat)
                        if club == "*" or club =="-":
                            club = ""

                        rows.append({
                            "Position": rank,
                            "Nom": fullname,
                            "Club": club,
                            "Sexe": sex,
                            "Categorie": cat,
                            "Position Catégorie": rank_category,
                            "Temps": time,
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