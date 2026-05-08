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

                        dos = row[1]
                        # si colonne numéro de dossard absent, on applique un offset 
                        offset = 0 if dos.isdigit() else 1

                        club = row[4-offset]
                        if club.isdigit():
                            offset += 1

                        temps = row[6 - offset]
                        # si la colonne 6 n'est pas un temps
                        if not re.match(r"\d{1,2}:\d{2}:\d{2}", temps):
                            # c'est que le nom et le prénom sont dans deux colonnes et il faut les rassembler
                            temps = row[7 - offset]
                            cat = row[5 - offset]
                            rank_category = row[6 - offset]
                            nom = normalize_name(" ".join(row[2-offset:4-offset]))
                            club =normalize_name(row[4 - offset])
                        else:
                            cat = row[4 - offset]
                            rank_category = row[5 - offset]
                            if club.isdigit():
                                if offset > 1:
                                    nom = normalize_name(row[1])
                                else:
                                    nom = normalize_name(row[2])
                                club = ""
                            else:
                                nom = normalize_name(row[2 - offset])
                                club = normalize_name(row[3 - offset])
                        
                        if not nom or nom == "0":
                            continue
                        
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