from __future__ import annotations

from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

from aiohttp import ClientSession

from .const import ALERTS_URL, BASE_URL, EVENTS_DATASET, LINES_DATASET, TIMETABLE_DATASET


class WarsawApiError(Exception):
    pass


def _rows(result: Any) -> list[dict[str, Any]]:
    out = []
    if not isinstance(result, list):
        return out
    for row in result:
        vals = row.get("values", []) if isinstance(row, dict) else []
        out.append({v.get("key"): v.get("value") for v in vals if isinstance(v, dict)})
    return out


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


class WarsawApi:
    def __init__(self, session: ClientSession, api_key: str) -> None:
        self.session = session
        self.api_key = api_key

    async def _get(self, endpoint: str, **params: Any) -> Any:
        params = {**params, "apikey": self.api_key}
        async with self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(data, dict) and data.get("error"):
            raise WarsawApiError(str(data.get("error")))
        if isinstance(result, str) and result.lower() in {"false", "błędna metoda lub parametry wywołania"}:
            raise WarsawApiError(result)
        return data

    async def validate(self) -> None:
        await self.dictionary()

    async def dictionary(self) -> dict[str, Any]:
        data = await self._get("public_transport_dictionary")
        return data.get("result") or {}

    async def routes(self) -> dict[str, Any]:
        data = await self._get("public_transport_routes")
        return data.get("result") or {}

    async def find_stop_groups(self, query: str) -> list[dict[str, str]]:
        groups = (await self.dictionary()).get("zespoly_przystankowe", {})
        q = query.casefold().strip()
        exact = [{"id": str(i), "name": str(n)} for i, n in groups.items() if str(n).casefold() == q]
        if exact:
            return sorted(exact, key=lambda x: x["name"])
        matches = [{"id": str(i), "name": str(n)} for i, n in groups.items() if q in str(n).casefold()]
        return sorted(matches, key=lambda x: x["name"])[:40]

    async def stop_posts(self, stop_id: str) -> list[str]:
        routes = await self.routes()
        posts: set[str] = set()
        for variants in routes.values():
            if not isinstance(variants, dict):
                continue
            for sequence in variants.values():
                if not isinstance(sequence, dict):
                    continue
                for item in sequence.values():
                    if isinstance(item, dict) and str(item.get("nr_zespolu")) == stop_id:
                        nr = item.get("nr_przystanku")
                        if nr:
                            posts.add(str(nr))
        return sorted(posts)

    async def stop_lines(self, stop_id: str, stop_nr: str) -> list[str]:
        data = await self._get("dbtimetable_get", id=LINES_DATASET, busstopId=stop_id, busstopNr=stop_nr)
        return sorted({str(r.get("linia")) for r in _rows(data.get("result")) if r.get("linia")})

    async def departures(self, stop_id: str, stop_nr: str, limit: int = 6) -> tuple[list[dict[str, Any]], list[str]]:
        now = datetime.now().astimezone()
        lines = await self.stop_lines(stop_id, stop_nr)
        departures: list[dict[str, Any]] = []
        for line in lines:
            data = await self._get(
                "dbtimetable_get", id=TIMETABLE_DATASET, busstopId=stop_id, busstopNr=stop_nr, line=line
            )
            for row in _rows(data.get("result")):
                raw = row.get("czas")
                if not raw:
                    continue
                try:
                    h, m, s = (int(x) for x in str(raw).split(":"))
                except Exception:
                    continue
                day_add, h = divmod(h, 24)
                dep = now.replace(hour=h, minute=m, second=s, microsecond=0) + timedelta(days=day_add)
                if dep < now - timedelta(seconds=30):
                    continue
                minutes = max(0, int((dep - now).total_seconds() // 60))
                departures.append({
                    "line": line,
                    "direction": row.get("kierunek") or "",
                    "route": row.get("trasa") or "",
                    "brigade": row.get("brygada") or "",
                    "scheduled": dep.isoformat(),
                    "time": dep.strftime("%H:%M"),
                    "minutes": minutes,
                })
        departures.sort(key=lambda x: x["scheduled"])
        return departures[:limit], lines

    async def air_quality(self, home_lat: float, home_lon: float) -> dict[str, Any]:
        data = await self._get("air_sensors_get")
        stations = data.get("result") or []
        valid = []
        for s in stations:
            try:
                lat, lon = float(s.get("lat")), float(s.get("lon"))
            except (TypeError, ValueError):
                continue
            s = dict(s)
            s["distance_km"] = round(_distance_km(home_lat, home_lon, lat, lon), 2)
            valid.append(s)
        if not valid:
            return {}
        station = min(valid, key=lambda s: s["distance_km"])
        measurements = {}
        for item in station.get("data", []) or []:
            code = str(item.get("param_code") or item.get("param_name") or "unknown").lower()
            measurements[code] = {
                "name": item.get("param_name"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "time": item.get("time"),
                "index": (item.get("ijp") or {}).get("name") if isinstance(item.get("ijp"), dict) else None,
            }
        return {
            "station": station.get("name") or station.get("station"),
            "station_id": station.get("station"),
            "distance_km": station.get("distance_km"),
            "address": station.get("address") or {},
            "index": (station.get("ijp") or {}).get("name") if isinstance(station.get("ijp"), dict) else None,
            "recommendations": (station.get("ijp") or {}).get("recommendations") if isinstance(station.get("ijp"), dict) else None,
            "measurements": measurements,
        }

    async def events(self) -> list[dict[str, Any]]:
        data = await self._get("events_calendar", id=EVENTS_DATASET)
        result = data.get("result") or []
        events = []
        for e in result:
            if not isinstance(e, dict):
                continue
            categories = e.get("category") or []
            category = ", ".join(str(x.get("name")) for x in categories if isinstance(x, dict) and x.get("name"))
            events.append({
                "title": e.get("title") or e.get("name") or "Wydarzenie",
                "category": category,
                "lead": e.get("lead"),
                "start": e.get("startDate") or e.get("start_date") or e.get("date_start") or e.get("date"),
                "end": e.get("endDate") or e.get("end_date") or e.get("date_end"),
                "place": e.get("place") or e.get("location"),
                "url": e.get("url") or e.get("link"),
            })
        return events[:50]

    async def alerts(self, lines: set[str]) -> list[dict[str, Any]]:
        try:
            async with self.session.get(ALERTS_URL, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except Exception:
            return []
        filtered = []
        for alert in data.get("alerts", []) if isinstance(data, dict) else []:
            routes = {str(x) for x in alert.get("routes", [])}
            hit = sorted(routes & lines)
            if not hit:
                continue
            filtered.append({
                "id": alert.get("id"),
                "title": alert.get("title"),
                "lines": hit,
                "effect": alert.get("effect"),
                "link": alert.get("link"),
                "body": alert.get("body"),
            })
        return filtered
