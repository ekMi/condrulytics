import argparse
import logging
from pathlib import Path
import pandas as pd

from utils.logging_config import setup_logging
from extraction.unzip import unzip_all
from parsing.services import parse_folder
from cleaning.clean import clean
from loading.load import load_parquet_to_postgres


PARQUET_DIR = Path("data/processed/parquet")
PROCESSED_PATH = Path("data/processed/results.parquet")
CLEANED_PATH = Path("data/cleaned/results.parquet")


def build_final_dataset():
    logger = logging.getLogger("pipeline")

    files = list(PARQUET_DIR.glob("*.parquet"))

    if not files:
        logger.warning("No parquet files found for consolidation")
        return

    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    df = df.drop_duplicates(subset=["racekey", "Nom"])

    df.to_parquet(PROCESSED_PATH, index=False)

    logger.info(f"Final dataset written: {PROCESSED_PATH} ({len(df)} rows)")


def main():
    parser = argparse.ArgumentParser(description="ETL Pipeline")
    parser.add_argument(
        "--step",
        choices=["all", "unzip", "parse", "build", "clean", "load"],
        default="all",
        help="Step to run"
    )
    parser.add_argument(
        "--log",
        default="logs/pipeline.log",
        help="Log file path"
    )

    args = parser.parse_args()

    setup_logging(args.log)
    logger = logging.getLogger("pipeline")

    logger.info("=== START PIPELINE ===")

    # ---------------- UNZIP ----------------
    if args.step in ["all", "unzip"]:
        logger.info("Step: Unzip")
        unzip_all(
            input_dir="data/raw/zip",
            output_dir="data/raw/pdf",
            report_file="logs/unzip_report.txt"
        )

    # ---------------- PARSE ----------------
    if args.step in ["all", "parse"]:
        logger.info("Step: Parse PDFs")

        parse_folder(
            folder_path="data/raw/pdf",
            output_dir=str(PARQUET_DIR),
            report_path="logs/parse_report.txt"
        )

    # ---------------- BUILD ----------------
    if args.step in ["all", "build"]:
        logger.info("Step: Build final dataset")
        build_final_dataset()


    # ---------------- CLEAN ----------------
    if args.step in ["all", "clean"]:
        logger.info("Step: Clean")
        clean(
            processed_path=PROCESSED_PATH, 
            cleaned_path=CLEANED_PATH
        )

    # ---------------- LOAD ----------------
    if args.step in ["all", "load"]:
        logger.info("Step: Load DB")
        load_parquet_to_postgres(
            parquet_path="data/cleaned/results.parquet"
        )

    logger.info("=== END PIPELINE ===")


if __name__ == "__main__":
    main()