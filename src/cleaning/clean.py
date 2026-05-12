import pandas as pd
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORIES_MAPPING = {
    # catégories invalides
    '': 'XXX',
    '#N/A': 'XXX',
    '#REF!': 'XXX',
    'xxx': 'XXX',
    'XXX': 'XXX',
    '0': 'XXX',

    # A1
    'A1': 'A1',
    'AI1': 'A1',
    'V1F': 'A1',

    # A2
    'A2': 'A2',
    'AI2': 'A2',
    'V2F': 'A2',

    # A3
    'A3': 'A3',
    'AI3': 'A3',
    'V3F': 'A3',

    # A4
    'A4': 'A4',
    'AI4': 'A4',
    'V4F': 'A4',

    # A5
    'A5': 'A5',
    'AI5': 'A5',
    'V45': 'A5',

    # SH
    'SH': 'SH',
    'H': 'SH',
    'SEH': 'SH',
    'SEN': 'SH',
    'DISH': 'SH',
    'SE': 'SH',

    #ESH
    'JUH': 'ESH',
    'JH': 'ESH',
    'EH': 'ESH',
    'ESH': 'ESH',
    'ESP': 'ESH',
    'GAR': 'ESH',

    # SD
    'DA': 'SD',
    'DAM': 'SD',
    'SD': 'SD',
    'F': 'SD',
    'SEF': 'SD',
    'DISF': 'SD',

    #ESF
    'JUF': 'ESF',
    'JF': 'ESF',
    'EF': 'ESF',
    'ESF': 'ESF',
    'FIL': 'ESF',
    'ED': 'ESF',

    # V1
    'V1': 'V1',
    'VE1': 'V1',
    'V1H': 'V1',

    # V2
    'V2': 'V2',
    'VE2': 'V2',
    'V2H': 'V2',

    # V3
    'V3': 'V3',
    'VE3': 'V3',
    'V3H': 'V3',

    # V4
    'V4': 'V4',
    'VE4': 'V4',
    'V4H': 'V4',

    # V5
    'V5': 'V5',
    'VE5': 'V5',
    'V5H': 'V5',
}

INVALID_VALUES = {
    "#VALEUR!"
}
def _normalize_time(value):

    if pd.isna(value):
        return pd.NaT

    value = str(value).strip()

    # valeurs invalides connues
    if value in INVALID_VALUES:
        return pd.NaT

    # suppression espaces parasites
    value = value.replace(" ", "")

    parts = value.split(":")

    # format MM:SS
    if len(parts) == 2:
        mm, ss = parts
        hh = "00"

    # format HH:MM:SS
    elif len(parts) == 3:
        hh, mm, ss = parts

    else:
        return pd.NaT

    # padding
    hh = hh.zfill(2)
    mm = mm.zfill(2)
    ss = ss.zfill(2)

    normalized = f"{hh}:{mm}:{ss}"

    try:
        return pd.to_timedelta(normalized)
    except:
        return pd.NaT

def clean(processed_path: str | Path, cleaned_path: str | Path):
    df = pd.read_parquet(processed_path)
    logger.info(f"Found {len(df)} rows")

    # Global
    # ---------

    # Harmonisation des catégories
    df['categorie_cleaned'] = (
        df['Categorie']
        .map(CATEGORIES_MAPPING)
        .fillna('XXX')
    )

    # Pour la catégorie XXX, mettre Position Catégorie à 0
    mask_xxx = df['categorie_cleaned'] == "XXX"
    df.loc[mask_xxx, 'Position Catégorie'] = '0'

    # Conversion des colonnes Position et Position en Int
    cols = ["Position", "Position Catégorie"]

    for col in cols:
        df[col] = (
            df[col]
            .astype("int")
        )

    # Harmonisation du temps
    # - Suppression des valeurs abérantes (7 entrées avec #VALEUR!)
    # - Conversion au format 00:00:00
    # - Ajout d'une colonne temps_clean (format timedelta)
    # - Ajout d'une colonne temps_sec (le temps en seconde, format)

    df["temps_clean"] = df["Temps"].apply(_normalize_time)
    df = df[df["temps_clean"].notna()]
    df["temps_sec"] = df["temps_clean"].dt.total_seconds().astype("int32")

    # Courses
    # ---------
    # Correction des noms de deux courses
    mask1 = df['NomCourse'] == "Sef : 15 V4F : 0 Seh : 76 V4H : 1"
    mask2 = df['NomCourse'] == "Sef : 29 V4F : 0 Seh : 23 V4H : 0"

    df.loc[mask1, 'NomCourse'] = "Les 10 Miles De Vyle-Tharoul"
    df.loc[mask2, 'NomCourse'] = "Les 10 Miles De Vyle-Tharoul"

    # Correction des distances pour quatre courses
    race1_mask = df["source_file"] == "2012-CONDRUSIEN-MODAVE-11.30.pdf"
    race2_mask = df["source_file"] == "210807-CONDRUSIEN-GOAL TIMING-VILLERS AUX TOURS-5000.pdf"
    race3_mask = df["source_file"] == "2015-CONDRUSIEN-FRAITURE 2- 5.29.pdf"
    race4_mask = df["source_file"] == "2015-CONDRUSIEN-FRAITURE 2- 9.2.pdf"

    df.loc[race1_mask, 'Distance'] = 11.3
    df.loc[race2_mask, 'Distance'] = 5.5
    df.loc[race3_mask, 'Distance'] = 5.29
    df.loc[race4_mask, 'Distance'] = 9.2

    # Coureurs
    # -----------
    # Suppression des noms de coureurs qui commencent par un nombre ou sont N/A
    mask_nom = df['Nom'].str.match(r'^\d', na=False)
    df.drop(df[mask_nom].index, inplace=True)
    df.drop(df[df["Nom"]=="#N/A"].index, inplace=True)
    # Correction du sexe et club pour une coureuse (Mergeai Agnes)
    mask_agnes = (df['Nom'] == "Mergeai Agnes") & (df["Sexe"] != "F")

    df.loc[mask_agnes, 'Club'] = "Neuf Moulin"
    df.loc[mask_agnes, 'Sexe'] = "F"

    # Correction de Simonet Yves (qui commence par (Cid:10))
    df.loc[df['Nom'] == "(Cid:10)Simonet Yves", 'Nom'] = "Simonet Yves"

    # Tentative de récupération des noms.


    df.to_parquet(cleaned_path)
    logger.info(f"Cleaned dataset written: {cleaned_path} ({len(df)} rows)")





