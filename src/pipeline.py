# pipeline.py
import argparse
import logging
from utils.logging_config import setup_logging
from extraction.unzip import unzip_all

def main():
    parser = argparse.ArgumentParser(description="ETL Pipeline")
    parser.add_argument(
        "--step",
        choices=["all", "unzip", "parse", "load"],
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

    if args.step in ["all", "unzip"]:
        logger.info("Step: Unzip")
        unzip_all(
            input_dir="data/raw/zip",
            output_dir="data/raw/pdf",
            report_file="logs/unzip_report.txt"
        )

    if args.step in ["all", "parse"]:
        logger.info("Step: Parse (TODO)")

    if args.step in ["all", "load"]:
        logger.info("Step: Load DB (TODO)")

    logger.info("=== END PIPELINE ===")


if __name__ == "__main__":
    main()