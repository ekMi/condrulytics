import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from parsing.factory import ParserFactory

logger = logging.getLogger(__name__)


def _parse_single_file(file: Path, output_dir: Path):
    """
    Parse un PDF et écrit un parquet.
    Retourne métriques pour reporting.
    """

    output_file = output_dir / f"{file.stem}.parquet"

    if output_file.exists():
        return {
            "file": file.name,
            "status": "SKIPPED",
            "rows": 0,
            "parsed": 0,
            "expected": None,
            "error": None
        }

    try:
        parser = ParserFactory.get_parser(file)
        df, meta = parser.parse(file)

        df["source_file"] = file.name
        df["racekey"] = (
            df["NomCourse"].astype(str).str.strip().str.lower()
            + "_"
            + df["Date"].astype(str).str.strip()
            + "_"
            + df["Distance"].astype(str).str.strip()
        )

        parsed = meta.get("parsed_count", len(df))
        expected = meta.get("expected_count")

        status = "OK"
        if expected is not None and parsed != expected:
            status = "MISMATCH"

        # write parquet
        if not df.empty:
            df.to_parquet(output_file, index=False)

        return {
            "file": file.name,
            "status": status,
            "rows": len(df),
            "parsed": parsed,
            "expected": expected,
            "error": None
        }

    except Exception as e:
        logger.error(f"{file.name} failed: {e}")
        return {
            "file": file.name,
            "status": "FAILED",
            "rows": 0,
            "parsed": 0,
            "expected": None,
            "error": str(e)
        }


# -----------------------------
# MAIN PIPELINE PARSER
# -----------------------------
def parse_folder(
    folder_path,
    output_dir,
    recursive=False,
    report_path="logs/parse_report.txt",
    max_workers=4
):
    start_time = time.time()

    folder = Path(folder_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        folder.rglob("*.pdf") if recursive else folder.glob("*.pdf")
    )

    logger.info(f"Found {len(files)} PDF files")

    results = []

    # -----------------------------
    # PARALLEL EXECUTION
    # -----------------------------
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_parse_single_file, file, output_dir): file
            for file in files
        }

        for future in as_completed(futures):
            res = future.result()
            results.append(res)

    # -----------------------------
    # METRICS
    # -----------------------------
    success = len([r for r in results if r["status"] in ("OK", "MISMATCH")])
    failed = len([r for r in results if r["status"] == "FAILED"])
    skipped = len([r for r in results if r["status"] == "SKIPPED"])
    total_rows = sum(r["rows"] for r in results)

    duration = time.time() - start_time

    # -----------------------------
    # REPORT
    # -----------------------------
    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)

    with open(report, "w") as f:
        f.write("=== GLOBAL ===\n")
        f.write(f"files_total: {len(files)}\n")
        f.write(f"files_success: {success}\n")
        f.write(f"files_failed: {failed}\n")
        f.write(f"files_skipped: {skipped}\n")
        f.write(f"rows_total: {total_rows}\n")
        f.write(f"duration_sec: {round(duration, 2)}\n\n")

        f.write("=== FILE DETAILS ===\n")
        for r in results:
            f.write(
                f"{r['file']} | "
                f"status={r['status']} | "
                f"rows={r['rows']} | "
                f"parsed={r['parsed']} | "
                f"expected={r['expected']} | "
                f"error={r['error']}\n"
            )

    logger.info(f"Report written: {report}")

    return results