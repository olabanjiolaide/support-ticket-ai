"""Locate bundled reference files in a source checkout or installed wheel."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def data_path(filename: str) -> Path:
    packaged = PACKAGE_ROOT / 'datasets' / filename
    return packaged if packaged.is_file() else PACKAGE_ROOT.parent / 'data' / filename


def report_path(filename: str) -> Path:
    packaged = PACKAGE_ROOT / 'baseline_reports' / filename
    return packaged if packaged.is_file() else PACKAGE_ROOT.parent / 'reports/bitext-baseline-v1' / filename
