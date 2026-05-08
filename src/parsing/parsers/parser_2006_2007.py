import re
import logging
import pandas as pd
import pdfplumber

from pathlib import Path
from ..base import ParserStrategy
from ..utils import (
    extract_year,
    extract_distance,
    extract_date,
    normalize_name,
    normalize_course_name,
    sex_from_category
)

logger = logging.getLogger(__name__)

class Parser2006_2007(ParserStrategy):

    @staticmethod
    def can_handle(full_text: str) -> bool:
        year = extract_year(full_text)
        return year in [2006, 2007]

    def parse(self, pdf_path: str | Path) -> tuple[pd.DataFrame, dict]:
        rows = []
        
        with pdfplumber.open(pdf_path) as pdf:
            first_text = pdf.pages[0].extract_text() or ""
            name = normalize_course_name(first_text.split("\n")[1])
            date =  extract_date(first_text)
            dist = extract_distance(first_text)
            expected = None

            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        rank = row[0]
                        if not rank.isdigit():
                            continue

                        dos = row[1]
                        # si colonne numéro de dossard absent, on applique un offset 
                        offset = 0 if dos.isdigit() else 1

                        temps = row[6 - offset]
                        if not re.match(r"\d{1,2}:\d{2}:\d{2}", temps):
                            continue

                        cat = row[4 - offset]
                        nom = normalize_name(row[2 - offset])
                        if not nom or nom == "0":
                            continue
                        club = normalize_name(row[3 - offset])
                        sex = sex_from_category(cat)
                        rank_category = row[5 - offset]

                        if club == "*" or club =="-":
                            club = ""

                        rows.append({
                            "Nom": nom,
                            "Position": rank,
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