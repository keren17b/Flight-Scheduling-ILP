"""Default crew legality limits and dataset-specific padding dates."""

from datetime import date, timedelta


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

# Padding dates for the supplied week-one dataset.
PADDING_START_DATE = date(2000, 1, 8)
PADDING_END_DATE = date(2000, 1, 10)
