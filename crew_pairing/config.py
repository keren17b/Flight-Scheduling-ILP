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

# Inclusive departure-date intervals for the active dataset.
# January 15-21 is required; the surrounding days are optional padding.
PADDING_DATE_RANGES = (
    (date(2000, 1, 12), date(2000, 1, 14)),
    (date(2000, 1, 22), date(2000, 1, 24)),
)
