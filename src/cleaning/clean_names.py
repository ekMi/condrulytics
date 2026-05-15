import logging
import re
from collections import defaultdict
from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


# =========================================================
# FONCTIONS UTILITAIRES
# =========================================================

def _normalize_name(name: str) -> str:
    """
    Nettoie un nom :
    - suppression des caractères spéciaux
    - trim espaces
    - majuscules
    """

    if pd.isna(name):
        return ""

    name = name.upper()

    # Remplace tout caractère non alphabétique par un espace
    name = re.sub(r"[^A-Z\s]", " ", name)

    # Supprime les espaces multiples
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def _blocking_key(name: str) -> str:
    """
    Génère une clé de blocage simple.

    Permet de limiter les comparaisons
    uniquement à des noms proches.
    """

    parts = sorted(name.split())

    return "".join(
        p[:3]
        for p in parts
    )


def _speed_score(speed_diff: float) -> int:
    """
    Convertit une différence de vitesse
    en score de similarité.
    """

    if speed_diff < 0.5:
        return 100

    if speed_diff < 1:
        return 80

    if speed_diff < 2:
        return 50

    return 0


def _final_score(name_score: float, speed_score: float) -> float:
    """
    Score final pondéré.
    """

    return round(
        0.9 * name_score +
        0.1 * speed_score,
        1
    )


# =========================================================
# PROFILS COUREURS
# =========================================================

def _build_runner_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construit un profil par coureur.
    """

    return (
        df.groupby("Nom_clean")
        .agg(
            n_races=("Nom_clean", "size"),
            sexe=(
                "Sexe",
                lambda x: (
                    x.mode().iloc[0]
                    if not x.mode().empty
                    else None
                )
            ),
            mean_speed=("speed_kmh", "mean"),
        )
        .reset_index()
    )


# =========================================================
# MATCHING ENTRE COUREURS FRÉQUENTS
# =========================================================

def _find_frequent_matches(
    profiles: pd.DataFrame,
    runner_races: dict,
    min_score: float = 95
) -> pd.DataFrame:
    """
    Recherche les doublons potentiels
    parmi les coureurs fréquents.
    """

    pairs = []

    records = profiles.to_dict("records")

    for a, b in combinations(records, 2):

        # Sexe incompatible
        if a["sexe"] != b["sexe"]:
            continue

        # Impossible d'être la même personne
        # si présents dans la même course
        same_race = len(
            runner_races[a["Nom_clean"]]
            &
            runner_races[b["Nom_clean"]]
        ) > 0

        if same_race:
            continue

        # Similarité nom
        name_score = fuzz.token_sort_ratio(
            a["Nom_clean"],
            b["Nom_clean"]
        )

        # Similarité vitesse
        speed_diff = abs(
            a["mean_speed"] -
            b["mean_speed"]
        )

        speed_score = _speed_score(speed_diff)

        final_score = _final_score(
            name_score,
            speed_score
        )

        if final_score < min_score:
            continue

        pairs.append({
            "name_1": a["Nom_clean"],
            "name_2": b["Nom_clean"],
            "races_1": a["n_races"],
            "races_2": b["n_races"],
            "final_score": final_score,
        })

    return pd.DataFrame(pairs)


# =========================================================
# MATCHING RARE -> FRÉQUENT
# =========================================================

def _find_rare_matches(
    rare_profiles: pd.DataFrame,
    freq_profiles: pd.DataFrame,
    min_name_score: float = 85,
    min_final_score: float = 95
) -> pd.DataFrame:
    """
    Associe les coureurs rares
    aux coureurs fréquents.
    """

    matches = []

    # Clé de blocage
    freq_profiles["block"] = (
        freq_profiles["Nom_clean"]
        .apply(_blocking_key)
    )

    rare_profiles["block"] = (
        rare_profiles["Nom_clean"]
        .apply(_blocking_key)
    )

    # Index des profils fréquents
    freq_index = defaultdict(list)

    for _, row in freq_profiles.iterrows():
        freq_index[row["block"]].append(row)

    # Recherche
    for _, rare in rare_profiles.iterrows():

        candidates = freq_index.get(
            rare["block"],
            []
        )

        if not candidates:
            continue

        candidate_names = [
            c["Nom_clean"]
            for c in candidates
        ]

        results = process.extract(
            rare["Nom_clean"],
            candidate_names,
            scorer=fuzz.token_sort_ratio,
            limit=5
        )

        for matched_name, score, _ in results:

            if score < min_name_score:
                continue

            ref = next(
                c for c in candidates
                if c["Nom_clean"] == matched_name
            )

            # Sexe incompatible
            if rare["sexe"] != ref["sexe"]:
                continue

            speed_diff = abs(
                rare["mean_speed"] -
                ref["mean_speed"]
            )

            speed_score = _speed_score(speed_diff)

            final_score = _final_score(
                score,
                speed_score
            )

            if final_score < min_final_score:
                continue

            matches.append({
                "rare_name": rare["Nom_clean"],
                "freq_name": matched_name,
                "final_score": final_score,
            })

    return pd.DataFrame(matches)


# =========================================================
# DICTIONNAIRE DE CORRECTIONS
# =========================================================

def _build_correction_dict(
    matches_df: pd.DataFrame,
    mode: str
) -> dict:
    """
    Construit le dictionnaire de corrections.
    """

    correction_dict = {}

    for _, row in matches_df.iterrows():

        # fréquent <-> fréquent
        if mode == "frequent":

            if row["races_1"] >= row["races_2"]:
                canonical = row["name_1"]
                other = row["name_2"]
            else:
                canonical = row["name_2"]
                other = row["name_1"]

        # rare -> fréquent
        else:
            canonical = row["freq_name"]
            other = row["rare_name"]

        correction_dict[other] = canonical

    return correction_dict


# =========================================================
# PIPELINE PRINCIPAL
# =========================================================

def clean_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline principal de nettoyage des noms.
    """

    logger.info("Début du nettoyage des noms")

    df = df.copy()

    # =====================================================
    # VARIABLES
    # =====================================================

    df["speed_kmh"] = (
        df["Distance"] /
        (df["temps_sec"] / 3600)
    )

    df["year"] = df["Date"].dt.year

    # =====================================================
    # NORMALISATION DES NOMS
    # =====================================================

    logger.info("Normalisation des noms")

    df["Nom_clean"] = (
        df["Nom"]
        .apply(_normalize_name)
    )

    # =====================================================
    # COUREURS FRÉQUENTS
    # =====================================================

    runner_counts = df["Nom_clean"].value_counts()

    frequent_runners = runner_counts[
        runner_counts >= 3
    ].index

    df_freq = df[
        df["Nom_clean"].isin(frequent_runners)
    ].copy()

    logger.info(
        "Coureurs fréquents détectés : %s",
        len(frequent_runners)
    )

    freq_profiles = _build_runner_profiles(df_freq)

    runner_races = (
        df_freq.groupby("Nom_clean")["racekey"]
        .apply(set)
        .to_dict()
    )

    # =====================================================
    # MATCHING FRÉQUENT ↔ FRÉQUENT
    # =====================================================

    logger.info(
        "Recherche de doublons parmi les coureurs fréquents"
    )

    frequent_matches = _find_frequent_matches(
        freq_profiles,
        runner_races
    )

    logger.info(
        "Doublons fréquents trouvés : %s",
        len(frequent_matches)
    )

    correction_dict = _build_correction_dict(
        frequent_matches,
        mode="frequent"
    )

    df["Nom_clean"] = (
        df["Nom_clean"]
        .replace(correction_dict)
    )

    # =====================================================
    # DEUXIÈME PASSE : RARES -> FRÉQUENTS
    # =====================================================

    runner_counts = df["Nom_clean"].value_counts()

    frequent_runners = runner_counts[
        runner_counts >= 3
    ].index

    rare_runners = runner_counts[
        runner_counts < 3
    ].index

    freq_profiles = _build_runner_profiles(
        df[df["Nom_clean"].isin(frequent_runners)]
    )

    rare_profiles = _build_runner_profiles(
        df[df["Nom_clean"].isin(rare_runners)]
    )

    logger.info(
        "Recherche de correspondances rares -> fréquents"
    )

    rare_matches = _find_rare_matches(
        rare_profiles,
        freq_profiles
    )

    logger.info(
        "Correspondances rares trouvées : %s",
        len(rare_matches)
    )

    rare_corrections = _build_correction_dict(
        rare_matches,
        mode="rare"
    )

    df["Nom_clean"] = (
        df["Nom_clean"]
        .replace(rare_corrections)
    )

    # =====================================================
    # RAPPORT FINAL
    # =====================================================

    total_corrections = (
        len(correction_dict) +
        len(rare_corrections)
    )

    unique_before = (
        df["Nom"]
        .nunique()
    )

    unique_after = (
        df["Nom_clean"]
        .nunique()
    )

    logger.info("========== RAPPORT ==========")
    logger.info(
        "Corrections appliquées : %s",
        total_corrections
    )
    logger.info(
        "Noms uniques avant : %s",
        unique_before
    )
    logger.info(
        "Noms uniques après : %s",
        unique_after
    )
    logger.info(
        "Réduction : %s",
        unique_before - unique_after
    )

    return df