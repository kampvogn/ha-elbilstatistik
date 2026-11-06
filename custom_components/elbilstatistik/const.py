"""Constants for Elbilstatistik."""

DOMAIN = "elbilstatistik"
API_BASE = "https://api.elbilstatistik.dk/v1"
REQUEST_TIMEOUT = 15

CONF_API_KEY = "api_key"
CONF_CACHE_HOURS = "cache_hours"
CONF_FUZZY = "fuzzy"

DEFAULT_CACHE_HOURS = 24
DEFAULT_FUZZY = True

SERVICE_LOOKUP_PLATE = "lookup_plate"
EVENT_VEHICLE = "elbilstatistik_vehicle"
SIGNAL_UPDATED = f"{DOMAIN}_updated"

# Seconds to stay quiet after a 429 without a usable Retry-After header.
DEFAULT_RETRY_AFTER = 60

# Where to get a free API key (shown in the setup form).
ACCOUNT_URL = "https://api.elbilstatistik.dk/account/"
