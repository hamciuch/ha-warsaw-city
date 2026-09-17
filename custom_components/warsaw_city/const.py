DOMAIN = "warsaw_city"
CONF_API_KEY = "api_key"
CONF_STOPS = "stops"

BASE_URL = "https://dane.um.warszawa.pl/api/action"
VEHICLES_ENDPOINT = "get_ztm_lokalizacja_pojazdow"
STOPS_ENDPOINT = "get_ztm_przystanki_komunikacji_miejskiej"
DEPARTURES_ENDPOINT = "get_ztm_odjazdy_linii_z_przystanku"

# Alerts remain sourced from the community GTFS-RT bridge until the new city portal
# exposes a documented disruptions endpoint suitable for line filtering.
ALERTS_URL = "https://mkuran.pl/gtfs/warsaw/alerts.json"

DEFAULT_DEPARTURES = 6
VEHICLE_MAX_AGE_SECONDS = 180
