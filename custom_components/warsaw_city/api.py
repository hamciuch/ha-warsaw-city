from __future__ import annotations

from datetime import datetime, timedelta
import re
import time
from typing import Any

from bs4 import BeautifulSoup

from aiohttp import ClientResponseError, ClientSession

from .const import (
    ALERTS_URL,
    BASE_URL,
    DEPARTURES_ENDPOINT,
    LINES_ENDPOINT,
    STOPS_ENDPOINT,
    VEHICLES_ENDPOINT,
    VEHICLE_MAX_AGE_SECONDS,
)


GIOS_BASE_URL = "https://api.gios.gov.pl/pjp-api/v1/rest"
WARSAW_EVENTS_URL = "https://cam.warszawa.pl/wydarzenia-w-warszawie/"

_EVENT_MONTHS = (
    "sty", "lut", "mar", "kwi", "maj", "cze",
    "lip", "sie", "wrz", "paź", "paz", "lis", "gru",
)


class WarsawApiError(Exception):
    """Base error raised by Warsaw City API client."""


class WarsawApiAuthError(WarsawApiError):
    """Raised when the token is rejected."""


def _norm_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _flatten_key_value_list(items: list[Any]) -> dict[str, Any]:
    """Convert [{key: ..., value: ...}, ...] to a flat dictionary."""
    out: dict[str, Any] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        key = item.get("key", item.get("Key"))
        if key is None:
            continue

        value = item.get("value", item.get("Value"))
        out[_norm_key(key)] = value

    return out


def _flatten_row(row: Any) -> dict[str, Any]:
    """Normalize all record shapes returned by dane.um.warszawa.pl."""

    # New ZTM timetable format:
    # [
    #   {"value":"4","key":"brygada"},
    #   {"value":"Cm. Wolski","key":"kierunek"},
    #   {"value":"21:15:00","key":"czas"}
    # ]
    if isinstance(row, list):
        return _flatten_key_value_list(row)

    if isinstance(row, str):
        return {"linia": row}

    if not isinstance(row, dict):
        return {}

    # Older/alternate format:
    # {"values": [{"key":"czas","value":"21:15:00"}, ...]}
    if isinstance(row.get("values"), list):
        return _flatten_key_value_list(row["values"])

    return {
        _norm_key(k): v
        for k, v in row.items()
    }


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract and normalize records from Warsaw API response shapes."""

    data = payload

    # Unwrap result wrappers recursively.
    while isinstance(data, dict) and "result" in data:
        if data.get("error"):
            raise WarsawApiError(str(data["error"]))
        data = data.get("result")

    if isinstance(data, dict):
        if data.get("error"):
            raise WarsawApiError(str(data["error"]))

        if data.get("success") is False:
            raise WarsawApiError(str(data.get("error") or data))

        for key in (
            "records",
            "data",
            "items",
            "featurememberproperties",
        ):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]

    if data is None:
        return []

    if not isinstance(data, list):
        raise WarsawApiError(
            f"Unexpected API payload type: {type(data).__name__}"
        )

    rows: list[dict[str, Any]] = []

    for row in data:
        flat = _flatten_row(row)
        if flat:
            rows.append(flat)

    return rows


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        key = _norm_key(name)
        if key in row and row[key] not in (None, ""):
            return row[key]

    return None


class WarsawApi:
    def __init__(
        self,
        session: ClientSession,
        api_key: str,
    ) -> None:
        self.session = session
        self.api_key = api_key.strip()

        self._stops_cache = None
        self._lines_cache: dict[
            tuple[str, str], tuple[float, list[str]]
        ] = {}
        self._departures_cache: dict[
            tuple[str, str, str], tuple[float, list[dict[str, Any]]]
        ] = {}
        self._vehicles_cache = None
        self._gios_station_cache = None
        self._events_cache = None

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
            "User-Agent": "ha-warsaw-city/0.2.4",
        }

        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": 30,
        }

        if body is not None:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = body

        try:
            async with self.session.post(
                f"{BASE_URL}/{endpoint}",
                **kwargs,
            ) as resp:
                text = await resp.text()

                if resp.status in (401, 403):
                    raise WarsawApiAuthError(
                        f"HTTP {resp.status}"
                    )

                resp.raise_for_status()

                try:
                    data = await resp.json(content_type=None)
                except Exception as err:
                    raise WarsawApiError(
                        "API returned non-JSON response: "
                        f"{text[:200]}"
                    ) from err

        except ClientResponseError as err:
            raise WarsawApiError(
                f"HTTP {err.status}: {err.message}"
            ) from err

        if isinstance(data, dict) and data.get("error"):
            msg = str(data.get("error"))
            folded = msg.casefold()

            if (
                "apikey" in folded
                or "authorization" in folded
                or "token" in folded
            ):
                raise WarsawApiAuthError(msg)

            raise WarsawApiError(msg)

        return data

    async def validate(self) -> None:
        data = await self._post(
            VEHICLES_ENDPOINT,
            {"type": 1},
        )

        if not isinstance(data, (list, dict)):
            raise WarsawApiError(
                "Unexpected API response"
            )

    async def _all_stops(
        self,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        now = time.monotonic()

        if (
            not force
            and self._stops_cache
            and now - self._stops_cache[0] < 6 * 3600
        ):
            return self._stops_cache[1]

        rows = _as_rows(
            await self._post(STOPS_ENDPOINT, {})
        )

        normalized = []

        for row in rows:
            stop_id = _pick(
                row,
                "zespol",
                "nr_zespolu",
                "stop_id",
                "busstopid",
                "id_zespolu",
            )
            stop_nr = _pick(
                row,
                "slupek",
                "nr_przystanku",
                "stop_nr",
                "busstopnr",
                "nr_slupek",
            )
            name = _pick(
                row,
                "nazwa_zespolu",
                "nazwa",
                "stop_name",
                "name",
            )

            if stop_id is None or name is None:
                continue

            normalized.append(
                {
                    "id": str(stop_id).strip(),
                    "nr": (
                        str(stop_nr).strip().zfill(2)
                        if stop_nr is not None
                        else ""
                    ),
                    "name": str(name).strip(),
                    "raw": row,
                }
            )

        self._stops_cache = (
            now,
            normalized,
        )

        return normalized

    async def find_stop_groups(
        self,
        query: str,
    ) -> list[dict[str, str]]:
        q = query.casefold().strip()
        groups = {}

        for row in await self._all_stops():
            groups[row["id"]] = row["name"]

        exact = [
            {"id": i, "name": n}
            for i, n in groups.items()
            if n.casefold() == q
        ]

        matches = exact or [
            {"id": i, "name": n}
            for i, n in groups.items()
            if q in n.casefold()
        ]

        return sorted(
            matches,
            key=lambda x: (
                x["name"],
                x["id"],
            ),
        )[:40]

    async def stop_posts(
        self,
        stop_id: str,
    ) -> list[str]:
        posts = {
            x["nr"]
            for x in await self._all_stops()
            if (
                x["id"] == str(stop_id)
                and x["nr"]
            )
        }

        return sorted(posts)

    async def stop_lines(
        self,
        stop_id: str,
        stop_nr: str,
        force: bool = False,
    ) -> list[str]:
        stop_id = str(stop_id).strip()
        stop_nr = str(stop_nr).strip().zfill(2)
        cache_key = (stop_id, stop_nr)
        now = time.monotonic()

        cached = self._lines_cache.get(cache_key)
        if (
            not force
            and cached
            and now - cached[0] < 300
        ):
            return cached[1]

        payload = await self._post(
            LINES_ENDPOINT,
            {
                "busstopId": stop_id,
                "busstopNr": stop_nr,
            },
        )

        lines: set[str] = set()

        for row in _as_rows(payload):
            line = _pick(
                row,
                "linia",
                "line",
                "lines",
            )

            if line in (None, "") and len(row) == 1:
                line = next(iter(row.values()))

            if line not in (None, ""):
                lines.add(str(line).strip())

        result = sorted(lines)
        self._lines_cache[cache_key] = (now, result)

        return result

    async def _line_departures(
        self,
        stop_id: str,
        stop_nr: str,
        line: str,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        stop_id = str(stop_id).strip()
        stop_nr = str(stop_nr).strip().zfill(2)
        line = str(line).strip()

        cache_key = (stop_id, stop_nr, line)
        now = time.monotonic()

        cached = self._departures_cache.get(cache_key)
        if (
            not force
            and cached
            and now - cached[0] < 30
        ):
            return cached[1]

        payload = await self._post(
            DEPARTURES_ENDPOINT,
            {
                "busstopId": stop_id,
                "busstopNr": stop_nr,
                "line": line,
            },
        )

        rows = _as_rows(payload)

        self._departures_cache[cache_key] = (
            now,
            rows,
        )

        return rows

    async def vehicles(
        self,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        now_mono = time.monotonic()

        if (
            not force
            and self._vehicles_cache
            and now_mono - self._vehicles_cache[0] < 20
        ):
            return self._vehicles_cache[1]

        records = []
        now = datetime.now().astimezone()

        for vehicle_type in (1, 2):
            payload = await self._post(
                VEHICLES_ENDPOINT,
                {"type": vehicle_type},
            )

            for row in _as_rows(payload):
                stamp = _pick(row, "time")
                stale = True
                parsed_time = None

                if stamp:
                    try:
                        parsed_time = datetime.strptime(
                            str(stamp),
                            "%Y-%m-%d %H:%M:%S",
                        ).astimezone()

                        stale = (
                            abs(
                                (
                                    now - parsed_time
                                ).total_seconds()
                            )
                            > VEHICLE_MAX_AGE_SECONDS
                        )
                    except ValueError:
                        pass

                records.append(
                    {
                        "line": str(
                            _pick(
                                row,
                                "lines",
                                "line",
                            )
                            or ""
                        ),
                        "brigade": str(
                            _pick(
                                row,
                                "brigade",
                                "brygada",
                            )
                            or ""
                        ),
                        "vehicle_number": str(
                            _pick(
                                row,
                                "vehiclenumber",
                                "vehicle_number",
                            )
                            or ""
                        ),
                        "lat": _pick(row, "lat"),
                        "lon": _pick(row, "lon"),
                        "time": (
                            parsed_time.isoformat()
                            if parsed_time
                            else stamp
                        ),
                        "stale": stale,
                        "type": vehicle_type,
                    }
                )

        self._vehicles_cache = (
            now_mono,
            records,
        )

        return records

    async def departures(
        self,
        stop_id: str,
        stop_nr: str,
        limit: int = 6,
        line_filter: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        now = datetime.now().astimezone()

        available_lines = await self.stop_lines(
            stop_id,
            stop_nr,
        )

        if line_filter:
            selected_lines = [
                line
                for line in available_lines
                if line in line_filter
            ]
        else:
            selected_lines = available_lines

        vehicles = await self.vehicles()
        departures: list[dict[str, Any]] = []

        for line in selected_lines:
            rows = await self._line_departures(
                stop_id,
                stop_nr,
                line,
            )

            for row in rows:
                raw_time = _pick(
                    row,
                    "czas",
                    "time",
                    "godzina",
                    "departure_time",
                )

                if not raw_time:
                    continue

                try:
                    h, m, s = (
                        int(x)
                        for x in str(raw_time).split(":")
                    )
                except (TypeError, ValueError):
                    continue

                day_add, h = divmod(h, 24)

                dep = now.replace(
                    hour=h,
                    minute=m,
                    second=s,
                    microsecond=0,
                ) + timedelta(days=day_add)

                # Keep departures for 5 minutes after scheduled time so the
                # Lovelace card can mark a just-departed vehicle in red.
                if dep < now - timedelta(minutes=5):
                    continue

                brigade = str(
                    _pick(
                        row,
                        "brygada",
                        "brigade",
                    )
                    or ""
                ).strip()

                live = next(
                    (
                        v
                        for v in vehicles
                        if (
                            not v["stale"]
                            and v["line"] == line
                            and (
                                not brigade
                                or v["brigade"].lstrip("0")
                                == brigade.lstrip("0")
                            )
                        )
                    ),
                    None,
                )

                departures.append(
                    {
                        "line": line,
                        "direction": str(
                            _pick(
                                row,
                                "kierunek",
                                "direction",
                            )
                            or ""
                        ),
                        "route": str(
                            _pick(
                                row,
                                "trasa",
                                "route",
                            )
                            or ""
                        ),
                        "brigade": brigade,
                        "scheduled": dep.isoformat(),
                        "time": dep.strftime("%H:%M"),
                        "minutes": max(
                            0,
                            int(
                                (
                                    dep - now
                                ).total_seconds()
                                // 60
                            ),
                        ),
                        "minutes_delta": int(
                            (
                                dep - now
                            ).total_seconds()
                            // 60
                        ),
                        "is_past": dep < now,
                        "vehicle": live,
                    }
                )

        departures.sort(
            key=lambda x: x["scheduled"]
        )

        return (
            departures[:limit],
            sorted(selected_lines),
        )

    async def _gios_get(self, path: str) -> Any:
        """GET JSON from the public GIOŚ Air Quality API."""
        url = f"{GIOS_BASE_URL}/{path.lstrip('/')}"
        headers = {
            "Accept": "application/json, application/ld+json",
            "User-Agent": "ha-warsaw-city/0.3.0",
        }

        async with self.session.get(
            url,
            headers=headers,
            timeout=30,
        ) as resp:
            text = await resp.text()
            resp.raise_for_status()

            try:
                return await resp.json(content_type=None)
            except Exception as err:
                raise WarsawApiError(
                    f"GIOŚ returned non-JSON response: {text[:200]}"
                ) from err

    @staticmethod
    def _float_pl(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _distance_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        from math import asin, cos, radians, sin, sqrt

        radius = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = (
            sin(dlat / 2) ** 2
            + cos(radians(lat1))
            * cos(radians(lat2))
            * sin(dlon / 2) ** 2
        )
        return 2 * radius * asin(sqrt(a))

    async def _nearest_gios_station(
        self,
        home_lat: float,
        home_lon: float,
    ) -> dict[str, Any] | None:
        now = time.monotonic()

        if (
            self._gios_station_cache
            and now - self._gios_station_cache[0] < 6 * 3600
        ):
            return self._gios_station_cache[1]

        payload = await self._gios_get("station/findAll?size=500")
        stations = []

        if isinstance(payload, dict):
            stations = (
                payload.get("Lista stacji pomiarowych")
                or payload.get("stations")
                or []
            )
        elif isinstance(payload, list):
            stations = payload

        candidates = []

        for station in stations:
            if not isinstance(station, dict):
                continue

            lat = self._float_pl(
                station.get("WGS84 φ N")
                or station.get("gegrLat")
                or station.get("lat")
            )
            lon = self._float_pl(
                station.get("WGS84 λ E")
                or station.get("gegrLon")
                or station.get("lon")
            )

            if lat is None or lon is None:
                continue

            station_id = (
                station.get("Identyfikator stacji")
                or station.get("id")
            )

            if station_id is None:
                continue

            item = dict(station)
            item["_id"] = station_id
            item["_lat"] = lat
            item["_lon"] = lon
            item["_distance_km"] = self._distance_km(
                home_lat,
                home_lon,
                lat,
                lon,
            )
            candidates.append(item)

        if not candidates:
            self._gios_station_cache = (now, None)
            return None

        station = min(
            candidates,
            key=lambda item: item["_distance_km"],
        )
        self._gios_station_cache = (now, station)
        return station

    async def air_quality(
        self,
        home_lat: float,
        home_lon: float,
    ) -> dict[str, Any]:
        """Return current air quality from the nearest GIOŚ station."""
        station = await self._nearest_gios_station(
            home_lat,
            home_lon,
        )

        if not station:
            return {}

        station_id = station["_id"]

        # Index
        index_name = None
        index_value = None
        critical = None

        try:
            index_payload = await self._gios_get(
                f"aqindex/getIndex/{station_id}"
            )

            index_data = (
                index_payload.get("AqIndex", {})
                if isinstance(index_payload, dict)
                else {}
            )

            index_name = (
                index_data.get("Nazwa kategorii indeksu")
                or index_data.get("stIndexLevel", {}).get("indexLevelName")
                if isinstance(index_data.get("stIndexLevel"), dict)
                else None
            )
            index_value = (
                index_data.get("Wartość indeksu")
                or index_data.get("stIndexLevel", {}).get("id")
                if isinstance(index_data.get("stIndexLevel"), dict)
                else None
            )
            critical = (
                index_data.get("Kod zanieczyszczenia krytycznego")
                or index_data.get("stSourceDataDate")
            )
        except Exception:
            # Measurements are still useful even if index is temporarily absent.
            pass

        sensors_payload = await self._gios_get(
            f"station/sensors/{station_id}?size=500"
        )

        if isinstance(sensors_payload, dict):
            sensors = (
                sensors_payload.get(
                    "Lista stanowisk pomiarowych dla podanej stacji"
                )
                or sensors_payload.get("Lista stanowisk pomiarowych")
                or sensors_payload.get("sensors")
                or []
            )
        elif isinstance(sensors_payload, list):
            sensors = sensors_payload
        else:
            sensors = []

        grouped: dict[str, list[Any]] = {}

        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue

            sensor_id = (
                sensor.get("Identyfikator stanowiska")
                or sensor.get("id")
            )
            code = (
                sensor.get("Wskaźnik - wzór")
                or sensor.get("Wskaźnik - kod")
                or sensor.get("param", {}).get("paramFormula")
                if isinstance(sensor.get("param"), dict)
                else None
            )

            if sensor_id is None or not code:
                continue

            code_norm = str(code).strip().upper()
            grouped.setdefault(code_norm, []).append(sensor_id)

        measurements: dict[str, dict[str, Any]] = {}

        # Prefer useful pollutants in stable order.
        wanted = (
            "PM2.5",
            "PM10",
            "NO2",
            "O3",
            "SO2",
            "CO",
        )

        for code in wanted:
            sensor_ids = grouped.get(code, [])
            latest = None

            # A station can have both manual and automatic positions.
            # Try all IDs and use the first one that provides a current value.
            for sensor_id in sensor_ids:
                try:
                    data_payload = await self._gios_get(
                        f"data/getData/{sensor_id}"
                    )
                except Exception:
                    continue

                if isinstance(data_payload, dict):
                    values = (
                        data_payload.get("Lista danych pomiarowych")
                        or data_payload.get("values")
                        or []
                    )
                else:
                    values = []

                for value in values:
                    if not isinstance(value, dict):
                        continue

                    reading = (
                        value.get("Wartość")
                        if "Wartość" in value
                        else value.get("value")
                    )

                    if reading is None:
                        continue

                    latest = {
                        "value": reading,
                        "time": (
                            value.get("Data")
                            or value.get("date")
                        ),
                    }
                    break

                if latest:
                    break

            if latest:
                key = (
                    code.lower()
                    .replace(".", "")
                    .replace(" ", "")
                )
                measurements[key] = {
                    "name": code,
                    "value": latest["value"],
                    "unit": "µg/m³",
                    "time": latest["time"],
                }

        return {
            "station": (
                station.get("Nazwa stacji")
                or station.get("stationName")
                or f"GIOŚ {station_id}"
            ),
            "station_id": station_id,
            "distance_km": round(
                float(station["_distance_km"]),
                2,
            ),
            "address": (
                station.get("Adres")
                or station.get("addressStreet")
            ),
            "index": index_name,
            "index_value": index_value,
            "critical_pollutant": critical,
            "source": "GIOŚ",
            "measurements": measurements,
        }

    async def events(self) -> list[dict[str, Any]]:
        """Read real event cards from the official CAM Warsaw calendar."""
        now_mono = time.monotonic()

        if (
            self._events_cache
            and now_mono - self._events_cache[0] < 30 * 60
        ):
            return self._events_cache[1]

        headers = {
            "Accept": "text/html",
            "User-Agent": "ha-warsaw-city/0.3.2",
        }

        async with self.session.get(
            WARSAW_EVENTS_URL,
            headers=headers,
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        events: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        month_map = {
            "sty": 1,
            "lut": 2,
            "mar": 3,
            "kwi": 4,
            "maj": 5,
            "cze": 6,
            "lip": 7,
            "sie": 8,
            "wrz": 9,
            "paź": 10,
            "paz": 10,
            "lis": 11,
            "gru": 12,
        }

        now = datetime.now().astimezone()

        # Important: only links to actual event detail pages are accepted.
        # This prevents headings such as "Kalendarz wydarzeń", "Termin",
        # "Kategorie wydarzeń" and "Bilety" from becoming fake events.
        event_links = [
            link
            for link in soup.find_all("a", href=True)
            if "/wydarzenie/" in str(link.get("href") or "")
        ]

        for link in event_links:
            href = str(link.get("href") or "").strip()
            if not href:
                continue

            url = urljoin(WARSAW_EVENTS_URL, href)

            if url in seen_urls:
                continue

            heading = link.find_parent(["h2", "h3", "h4"])
            if heading is None:
                continue

            title = heading.get_text(" ", strip=True)
            if not title:
                continue

            # Find the smallest parent that looks like one complete event card.
            container = heading
            card_text = ""

            for _ in range(8):
                parent = getattr(container, "parent", None)
                if parent is None:
                    break

                container = parent
                candidate = container.get_text("\n", strip=True)

                if (
                    "Organizator:" in candidate
                    and (
                        "Warszawa," in candidate
                        or "Wstęp wolny" in candidate
                        or "Bilet:" in candidate
                    )
                ):
                    card_text = candidate
                    break

            if not card_text:
                continue

            lines = [
                line.strip()
                for line in card_text.splitlines()
                if line.strip()
            ]

            organizer = None
            place = None
            free = "Wstęp wolny" in card_text

            for idx, line_text in enumerate(lines):
                if line_text.startswith("Organizator:"):
                    organizer = (
                        line_text.split("Organizator:", 1)[1].strip()
                        or None
                    )

                if (
                    line_text == "Warszawa,"
                    and idx + 1 < len(lines)
                ):
                    possible_place = lines[idx + 1]
                    if possible_place not in (
                        "Wstęp wolny",
                        "Zapisz się",
                    ) and not possible_place.startswith("Bilet:"):
                        place = possible_place

            # CAM cards expose the date as separate pieces:
            # 17 / wrz / czwartek, godz. 18:00
            day_text = None
            month_text = None
            time_text = None

            for idx, line_text in enumerate(lines):
                if (
                    day_text is None
                    and re.fullmatch(
                        r"\d{1,2}(?:[-–]\d{1,2})?",
                        line_text,
                    )
                ):
                    # The following line should be a Polish month abbreviation.
                    if idx + 1 < len(lines):
                        next_line = lines[idx + 1].casefold()
                        if next_line in month_map:
                            day_text = line_text
                            month_text = next_line
                            if idx + 2 < len(lines):
                                candidate_time = lines[idx + 2]
                                if "godz." in candidate_time:
                                    time_text = candidate_time
                            break

            date_text = None
            start_iso = None

            if day_text and month_text:
                date_text = f"{day_text} {month_text}"
                if time_text:
                    date_text += f", {time_text}"

                # Use the first day for sorting multi-day events.
                first_day = int(
                    re.split(r"[-–]", day_text)[0]
                )
                month_num = month_map[month_text]

                hour = 0
                minute = 0

                if time_text:
                    match = re.search(
                        r"godz\.\s*(\d{1,2}):(\d{2})",
                        time_text,
                    )
                    if match:
                        hour = int(match.group(1))
                        minute = int(match.group(2))

                year = now.year

                try:
                    start_dt = now.replace(
                        year=year,
                        month=month_num,
                        day=first_day,
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    )

                    # If the calendar rolls over into the next year,
                    # keep a far-past date from sorting before current events.
                    if start_dt < now - timedelta(days=180):
                        start_dt = start_dt.replace(
                            year=year + 1
                        )

                    start_iso = start_dt.isoformat()
                except ValueError:
                    start_iso = None

            events.append(
                {
                    "title": title,
                    "organizer": organizer,
                    "date": date_text,
                    "start": start_iso,
                    "place": place,
                    "free": free,
                    "url": url,
                    "source": "CAM Warszawa",
                }
            )
            seen_urls.add(url)

        # Real dated events first; preserve CAM page order as fallback.
        dated = [
            event
            for event in events
            if event.get("start")
        ]
        undated = [
            event
            for event in events
            if not event.get("start")
        ]

        dated.sort(
            key=lambda event: event["start"]
        )

        result = (dated + undated)[:20]

        self._events_cache = (
            now_mono,
            result,
        )
        return result

    async def alerts(
        self,
        lines: set[str],
    ) -> list[dict[str, Any]]:
        if not lines:
            return []

        try:
            async with self.session.get(
                ALERTS_URL,
                timeout=30,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(
                    content_type=None
                )
        except Exception:
            return []

        filtered = []

        alerts = (
            data.get("alerts", [])
            if isinstance(data, dict)
            else []
        )

        for alert in alerts:
            if not isinstance(alert, dict):
                continue

            routes = {
                str(x)
                for x in alert.get(
                    "routes",
                    [],
                )
            }

            hit = sorted(
                routes & lines
            )

            if hit:
                filtered.append(
                    {
                        "id": alert.get("id"),
                        "title": alert.get("title"),
                        "lines": hit,
                        "effect": alert.get("effect"),
                        "link": alert.get("link"),
                        "body": alert.get("body"),
                    }
                )

        return filtered
