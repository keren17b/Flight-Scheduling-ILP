"""Input paths, default crew legality limits, and dataset-specific padding dates."""

from datetime import date, timedelta

from crew_pairing.data_paths import GENERATED_DIR, INPUT_DIR


# Active input files.
FLIGHTS_FILE_PATH = GENERATED_DIR / "archive_instance1_2000-01-14_padding3_flights.csv"
HUBS_FILE_PATH =  INPUT_DIR / "instance1_listOfBases.csv"

# Flight connections.
DEFAULT_MIN_CONNECTION = timedelta(minutes=30)
DEFAULT_MAX_CONNECTION = timedelta(hours=8)

# Duties.
MAX_ELAPSED_DUTY_TIME = timedelta(hours=12)
MAX_FLIGHTS_PER_DUTY = 5
MAX_ACTUAL_FLIGHT_TIME = timedelta(hours=8)

# Connections between duties.
MIN_REST_BETWEEN_DUTIES = timedelta(hours=10)
MAX_LAYOVER_BETWEEN_DUTIES = timedelta(hours=48)

# Pairings. Rest between duties counts toward the total pairing time.
MAX_PAIRING_TIME = timedelta(days=5)
MAX_DUTIES_PER_PAIRING = 5

# Inclusive departure-date intervals for the active dataset.
# January 14-20 is required; the surrounding days are optional padding.
# Keep these ranges aligned with FLIGHTS_FILE_PATH above.

PADDING_DATE_RANGES = (
    (date(2000, 1, 11), date(2000, 1, 13)),
    (date(2000, 1, 21), date(2000, 1, 23)),
)
