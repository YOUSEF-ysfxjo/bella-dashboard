"""
Google Calendar MCP tools — registered on the FastMCP server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.calendar import CalendarClient


def register(mcp: "FastMCP", calendar: "CalendarClient") -> None:
    """Register all Calendar tools on the MCP server."""

    @mcp.tool()
    def calendar_list_calendars() -> list[dict[str, Any]]:
        """List all calendars connected to the Google account."""
        return calendar.list_calendars()

    @mcp.tool()
    def calendar_list_events(
        calendar_id: str = "",
        time_min: str = "",
        time_max: str = "",
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List events in a time range.
        calendar_id: Calendar ID (empty = primary calendar).
        time_min: Start datetime ISO 8601, e.g. "2026-04-06T00:00:00+03:00" (empty = now).
        time_max: End datetime ISO 8601 (empty = 30 days from now).
        """
        from datetime import datetime, timezone

        tmin = datetime.fromisoformat(time_min) if time_min else None
        tmax = datetime.fromisoformat(time_max) if time_max else None
        return calendar.list_events(
            calendar_id=calendar_id if calendar_id else None,
            time_min=tmin,
            time_max=tmax,
            max_results=max_results,
        )

    @mcp.tool()
    def calendar_get_today(calendar_id: str = "") -> list[dict[str, Any]]:
        """
        Get all events scheduled for today.
        Returns: event titles, start/end times, locations, descriptions.
        """
        return calendar.get_today(calendar_id=calendar_id if calendar_id else None)

    @mcp.tool()
    def calendar_get_week(calendar_id: str = "") -> list[dict[str, Any]]:
        """
        Get all events for the next 7 days.
        Good for weekly planning and scheduling.
        """
        return calendar.get_week(calendar_id=calendar_id if calendar_id else None)

    @mcp.tool()
    def calendar_create_event(
        title: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        calendar_id: str = "",
        timezone: str = "Asia/Riyadh",
    ) -> dict[str, Any]:
        """
        Create a new calendar event.
        start: ISO 8601 datetime e.g. "2026-04-10T14:00:00"
        end: ISO 8601 datetime e.g. "2026-04-10T15:00:00"
        timezone: Defaults to Asia/Riyadh (Makkah time).
        """
        return calendar.create_event(
            title=title,
            start=start,
            end=end,
            description=description if description else None,
            location=location if location else None,
            calendar_id=calendar_id if calendar_id else None,
            timezone=timezone,
        )

    @mcp.tool()
    def calendar_update_event(
        event_id: str,
        fields: str,
        calendar_id: str = "",
    ) -> dict[str, Any]:
        """
        Update an existing event.
        event_id: Event ID from calendar_list_events or calendar_get_today.
        fields: JSON string of fields to update.
        Example: '{"summary": "New Title", "description": "Updated description"}'
        """
        import json
        fields_dict = json.loads(fields)
        return calendar.update_event(
            event_id=event_id,
            fields=fields_dict,
            calendar_id=calendar_id if calendar_id else None,
        )

    @mcp.tool()
    def calendar_delete_event(
        event_id: str,
        calendar_id: str = "",
    ) -> dict[str, str]:
        """
        Delete a calendar event by its ID.
        event_id: Event ID from list/get operations.
        """
        return calendar.delete_event(
            event_id=event_id,
            calendar_id=calendar_id if calendar_id else None,
        )

    @mcp.tool()
    def calendar_find_free_time(
        target_date: str,
        duration_minutes: int = 60,
        calendar_id: str = "",
        work_start_hour: int = 9,
        work_end_hour: int = 22,
    ) -> list[dict[str, Any]]:
        """
        Find free time slots on a given day.
        target_date: "YYYY-MM-DD" format.
        duration_minutes: Minimum slot length to return (default 60 min).
        work_start_hour / work_end_hour: Only look within these hours (24h, Riyadh time).
        Returns: list of free windows with start time, end time, and duration.
        """
        return calendar.find_free_time(
            target_date=target_date,
            duration_minutes=duration_minutes,
            calendar_id=calendar_id if calendar_id else None,
            work_start_hour=work_start_hour,
            work_end_hour=work_end_hour,
        )
