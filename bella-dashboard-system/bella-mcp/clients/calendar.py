"""
Google Calendar API client.
Uses google-api-python-client with OAuth2 credentials.

Authentication setup (one-time):
1. Go to Google Cloud Console → Create OAuth2 credentials (Desktop app)
2. Download credentials.json → place at path in GOOGLE_CREDENTIALS_JSON env var
3. First run will open browser for OAuth consent → saves token to GOOGLE_TOKEN_JSON path
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


class CalendarClient:
    def __init__(self) -> None:
        self._credentials_path = os.environ.get(
            "GOOGLE_CREDENTIALS_JSON", "credentials.json"
        )
        self._token_path = os.environ.get("GOOGLE_TOKEN_JSON", "token.json")
        self._calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
        self. _service = self._build_service()

    def _build_service(self):
        creds: Credentials | None = None

        # Load existing token
        if os.path.exists(self._token_path):
            creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)

        # Refresh or re-authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self._credentials_path):
                    raise RuntimeError(
                        f"Google credentials file not found at: {self._credentials_path}\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for next run
            with open(self._token_path, "w") as f:
                f.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    # ──────────────────────────────────────────────
    # Calendars
    # ──────────────────────────────────────────────

    def list_calendars(self) -> list[dict[str, Any]]:
        """List all calendars the user has access to."""
        result = self._service.calendarList().list().execute()
        return [
            {
                "id": c["id"],
                "summary": c.get("summary"),
                "primary": c.get("primary", False),
                "access_role": c.get("accessRole"),
                "color": c.get("backgroundColor"),
            }
            for c in result.get("items", [])
        ]

    # ──────────────────────────────────────────────
    # Events
    # ──────────────────────────────────────────────

    def list_events(
        self,
        calendar_id: str | None = None,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int = 50,
        single_events: bool = True,
    ) -> list[dict[str, Any]]:
        """List events in a time range. Defaults to primary calendar."""
        cal_id = calendar_id or self._calendar_id

        now = datetime.now(timezone.utc)
        tmin = (time_min or now).isoformat()
        tmax = (time_max or (now + timedelta(days=30))).isoformat()

        result = (
            self._service.events()
            .list(
                calendarId=cal_id,
                timeMin=tmin,
                timeMax=tmax,
                maxResults=max_results,
                singleEvents=single_events,
                orderBy="startTime",
            )
            .execute()
        )
        return [self._format_event(e) for e in result.get("items", [])]

    def get_today(self, calendar_id: str | None = None) -> list[dict[str, Any]]:
        """Return all events happening today."""
        today = datetime.now(timezone.utc).date()
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return self.list_events(calendar_id=calendar_id, time_min=start, time_max=end)

    def get_week(self, calendar_id: str | None = None) -> list[dict[str, Any]]:
        """Return all events this week (next 7 days from now)."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        return self.list_events(calendar_id=calendar_id, time_min=now, time_max=end)

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        calendar_id: str | None = None,
        timezone: str = "Asia/Riyadh",
    ) -> dict[str, Any]:
        """
        Create a calendar event.
        start/end: ISO 8601 datetime string e.g. "2026-04-10T14:00:00"
        """
        cal_id = calendar_id or self._calendar_id
        event: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": timezone},
            "end": {"dateTime": end, "timeZone": timezone},
        }
        if description:
            event["description"] = description
        if location:
            event["location"] = location

        result = (
            self._service.events()
            .insert(calendarId=cal_id, body=event)
            .execute()
        )
        return self._format_event(result)

    def update_event(
        self,
        event_id: str,
        fields: dict[str, Any],
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Partially update an event. fields can include:
        summary, description, location, start, end, attendees, etc.
        """
        cal_id = calendar_id or self._calendar_id
        # Fetch existing, patch, push back
        existing = self._service.events().get(calendarId=cal_id, eventId=event_id).execute()
        existing.update(fields)
        result = (
            self._service.events()
            .update(calendarId=cal_id, eventId=event_id, body=existing)
            .execute()
        )
        return self._format_event(result)

    def delete_event(
        self, event_id: str, calendar_id: str | None = None
    ) -> dict[str, str]:
        cal_id = calendar_id or self._calendar_id
        self._service.events().delete(calendarId=cal_id, eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}

    # ──────────────────────────────────────────────
    # Free/Busy
    # ──────────────────────────────────────────────

    def find_free_time(
        self,
        target_date: str,
        duration_minutes: int = 60,
        calendar_id: str | None = None,
        work_start_hour: int = 9,
        work_end_hour: int = 22,
    ) -> list[dict[str, Any]]:
        """
        Find free slots on a given date.
        target_date: "YYYY-MM-DD"
        Returns list of available time windows.
        """
        cal_id = calendar_id or self._calendar_id
        d = date.fromisoformat(target_date)
        tz = "Asia/Riyadh"

        time_min = datetime(d.year, d.month, d.day, work_start_hour, 0, tzinfo=_riyadh_tz()).isoformat()
        time_max = datetime(d.year, d.month, d.day, work_end_hour, 0, tzinfo=_riyadh_tz()).isoformat()

        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": tz,
            "items": [{"id": cal_id}],
        }
        result = self._service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(cal_id, {}).get("busy", [])

        # Find free windows
        free_slots = []
        cursor = datetime(d.year, d.month, d.day, work_start_hour, 0, tzinfo=_riyadh_tz())
        end_of_day = datetime(d.year, d.month, d.day, work_end_hour, 0, tzinfo=_riyadh_tz())

        for block in busy:
            block_start = _parse_dt(block["start"])
            block_end = _parse_dt(block["end"])
            if (block_start - cursor).total_seconds() >= duration_minutes * 60:
                free_slots.append({
                    "start": cursor.strftime("%H:%M"),
                    "end": block_start.strftime("%H:%M"),
                    "duration_minutes": int((block_start - cursor).total_seconds() / 60),
                })
            cursor = max(cursor, block_end)

        if (end_of_day - cursor).total_seconds() >= duration_minutes * 60:
            free_slots.append({
                "start": cursor.strftime("%H:%M"),
                "end": end_of_day.strftime("%H:%M"),
                "duration_minutes": int((end_of_day - cursor).total_seconds() / 60),
            })

        return free_slots

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _format_event(event: dict[str, Any]) -> dict[str, Any]:
        start = event.get("start", {})
        end = event.get("end", {})
        return {
            "id": event.get("id"),
            "title": event.get("summary"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "description": event.get("description"),
            "location": event.get("location"),
            "status": event.get("status"),
            "url": event.get("htmlLink"),
            "attendees": [
                a.get("email") for a in event.get("attendees", [])
            ],
        }


def _riyadh_tz():
    """UTC+3 fixed offset for Riyadh (no DST)."""
    return timezone(timedelta(hours=3))


def _parse_dt(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string to aware datetime."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.astimezone(_riyadh_tz())
