"""Locations of the sample data files shipped with this project."""

from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INPUT_DIR = DATA_DIR / "inputs"
GENERATED_DIR = DATA_DIR / "generated"
