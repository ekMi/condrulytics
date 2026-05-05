# src/extraction/unzip.py
import zipfile
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def unzip_all(input_dir: str, output_dir: str, report_file: str = None):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    extracted_files = []
    skipped_files = 0
    total_size = 0

    for zip_path in input_path.rglob("*.zip"):
        logger.info(f"Processing zip: {zip_path}")

        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                for member in z.namelist():

                    if member.endswith("/"):
                        continue

                    filename = os.path.basename(member)
                    if not filename:
                        continue

                    dest = output_path / filename

                    if dest.exists():
                        skipped_files += 1
                        continue

                    # Extraction
                    with z.open(member) as source, open(dest, "wb") as target:
                        data = source.read()
                        target.write(data)

                    size = len(data)
                    total_size += size
                    extracted_files.append((dest.name, size))

        except Exception as e:
            logger.error(f"Error processing {zip_path}: {e}")

    logger.info(f"Extracted: {len(extracted_files)} files")
    logger.info(f"Skipped: {skipped_files}")
    logger.info(f"Total size: {total_size} bytes")

    # Génération rapport texte
    if report_file:
        report_path = Path(report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w") as f:
            f.write(f"files_extracted: {len(extracted_files)}\n")
            f.write(f"files_skipped: {skipped_files}\n")
            f.write(f"total_size_bytes: {total_size}\n\n")

            for name, size in extracted_files:
                f.write(f"{name} | {size}\n")

        logger.info(f"Report written to: {report_path}")