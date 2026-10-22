"""Acesso ao Google Agenda do dono do bot."""
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None


def service():
    global _service
    if _service is None:
        creds = Credentials(
            token=None,
            refresh_token=config.GOOGLE_REFRESH_TOKEN,
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _localize(value: str) -> str:
    """Aceita ISO com ou sem fuso; sem fuso, assume o fuso configurado."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.TZ)
    return dt.isoformat()


def _simplify(event: dict) -> dict:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "titulo": event.get("summary", "(sem título)"),
        "inicio": start.get("dateTime") or start.get("date"),
        "fim": end.get("dateTime") or end.get("date"),
        "dia_inteiro": "date" in start,
        "local": event.get("location"),
        "descricao": event.get("description"),
    }


def list_events(start: str, end: str, query: str | None = None) -> list[dict]:
    params = {
        "calendarId": config.CALENDAR_ID,
        "timeMin": _localize(start),
        "timeMax": _localize(end),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 50,
    }
    if query:
        params["q"] = query
    items = service().events().list(**params).execute().get("items", [])
    return [_simplify(e) for e in items]


def create_event(
    title: str,
    start: str,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
    all_day: bool = False,
) -> dict:
    body: dict = {"summary": title}
    if all_day:
        day = datetime.fromisoformat(start).date()
        last = datetime.fromisoformat(end).date() if end else day
        body["start"] = {"date": day.isoformat()}
        body["end"] = {"date": (last + timedelta(days=1)).isoformat()}
    else:
        start_iso = _localize(start)
        end_iso = _localize(end) if end else (datetime.fromisoformat(start_iso) + timedelta(hours=1)).isoformat()
        body["start"] = {"dateTime": start_iso, "timeZone": config.TIMEZONE}
        body["end"] = {"dateTime": end_iso, "timeZone": config.TIMEZONE}
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    created = service().events().insert(calendarId=config.CALENDAR_ID, body=body).execute()
    return _simplify(created)


def update_event(
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    current = service().events().get(calendarId=config.CALENDAR_ID, eventId=event_id).execute()
    patch: dict = {}
    if title is not None:
        patch["summary"] = title
    if location is not None:
        patch["location"] = location
    if description is not None:
        patch["description"] = description
    if start is not None:
        start_iso = _localize(start)
        if end is None and "dateTime" in current.get("start", {}):
            # Mantém a duração original ao remarcar só o início
            old_start = datetime.fromisoformat(current["start"]["dateTime"])
            old_end = datetime.fromisoformat(current["end"]["dateTime"])
            end = (datetime.fromisoformat(start_iso) + (old_end - old_start)).isoformat()
        patch["start"] = {"dateTime": start_iso, "timeZone": config.TIMEZONE}
    if end is not None:
        patch["end"] = {"dateTime": _localize(end), "timeZone": config.TIMEZONE}
    updated = service().events().patch(calendarId=config.CALENDAR_ID, eventId=event_id, body=patch).execute()
    return _simplify(updated)


def delete_event(event_id: str) -> dict:
    service().events().delete(calendarId=config.CALENDAR_ID, eventId=event_id).execute()
    return {"ok": True, "id": event_id}
