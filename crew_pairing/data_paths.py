"""Locations of the sample data files shipped with this project."""

from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BASES_DIR = DATA_DIR / "bases"
FLIGHTS_DIR = DATA_DIR / "flights"
