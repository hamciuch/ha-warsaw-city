from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import (
    ALERTS_URL,
    BASE_URL,
    DEPARTURES_ENDPOINT,
    STOPS_ENDPOINT,
    VEHICLES_ENDPOINT,
    VEHICLE_MAX_AGE_SECONDS,
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


def _flatten_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}

    if isinstance(row.get("values"), list):
        out: dict[str, Any] = {}
        for item in row["values"]:
            if (
                isinstance(item, dict)
                and item.get("key") is not None
            ):
                out[_norm_key(item.get("key"))] = item.get("value")
        return out

    return {
        _norm_key(k): v
        for k, v in row.items()
    }


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    data = payload

    if isinstance(data, dict):
        if data.get("error"):
            raise WarsawApiError(str(data["error"]))

        if "result" in data:
            data = data.get("result")
        elif "records" in data:
            data = data.get("records")

    if isinstance(data, dict):
        for key in (
            "records",
            "data",
            "items",
            "featurememberproperties",
        ):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    return [
        _flatten_row(row)
        for row in data
        if isinstance(row, dict)
    ]


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
        self._departures_cache = None
        self._vehicles_cache = None

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
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
            await self._post(STOPS_ENDPOINT)
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

    async def _all_departure_rows(
        self,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        now = time.monotonic()

        if (
            not force
            and self._departures_cache
            and now - self._departures_cache[0] < 300
        ):
            return self._departures_cache[1]

        rows = _as_rows(
            await self._post(DEPARTURES_ENDPOINT)
        )

        self._departures_cache = (
            now,
            rows,
        )

        return rows

    async def stop_lines(
        self,
        stop_id: str,
        stop_nr: str,
    ) -> list[str]:
        """Return all lines serving the selected stop post."""
        stop_id = str(stop_id)
        stop_nr = str(stop_nr).zfill(2)

        lines = set()

        for row in await self._all_departure_rows():
            rid = _pick(
                row,
                "zespol",
                "nr_zespolu",
                "stop_id",
                "busstopid",
                "id_zespolu",
            )
            rnr = _pick(
                row,
                "slupek",
                "nr_przystanku",
                "stop_nr",
                "busstopnr",
                "nr_slupek",
            )

            if (
                str(rid or "") != stop_id
                or str(rnr or "").zfill(2) != stop_nr
            ):
                continue

            line = str(
                _pick(
                    row,
                    "linia",
                    "line",
                    "lines",
                )
                or ""
            ).strip()

            if line:
                lines.add(line)

        return sorted(lines)

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
        rows = await self._all_departure_rows()
        vehicles = await self.vehicles()

        stop_id = str(stop_id)
        stop_nr = str(stop_nr).zfill(2)

        departures = []
        lines = set()

        for row in rows:
            rid = _pick(
                row,
                "zespol",
                "nr_zespolu",
                "stop_id",
                "busstopid",
                "id_zespolu",
            )
            rnr = _pick(
                row,
                "slupek",
                "nr_przystanku",
                "stop_nr",
                "busstopnr",
                "nr_slupek",
            )

            if (
                str(rid or "") != stop_id
                or str(rnr or "").zfill(2) != stop_nr
            ):
                continue

            line = str(
                _pick(
                    row,
                    "linia",
                    "line",
                    "lines",
                )
                or ""
            ).strip()

            if (
                not line
                or (
                    line_filter
                    and line not in line_filter
                )
            ):
                continue

            raw_time = _pick(
                row,
                "czas",
                "time",
                "godzina",
                "departure_time",
            )

            if not raw_time:
                continue

            lines.add(line)

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

            if dep < now - timedelta(seconds=30):
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
                    "vehicle": live,
                }
            )

        departures.sort(
            key=lambda x: x["scheduled"]
        )

        return (
            departures[:limit],
            sorted(lines),
        )

    async def air_quality(
        self,
        home_lat: float,
        home_lon: float,
    ) -> dict[str, Any]:
        return {}

    async def events(self) -> list[dict[str, Any]]:
        return []

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
                        "title": alert.get(
                            "title"
                        ),
                        "lines": hit,
                        "effect": alert.get(
                            "effect"
                        ),
                        "link": alert.get(
                            "link"
                        ),
                        "body": alert.get(
                            "body"
                        ),
                    }
                )

        return filtered
