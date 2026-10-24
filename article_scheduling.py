"""Editor scheduling: explicit local timezone at the boundary, naive UTC in storage."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TIMEZONES={'Africa/Maputo':'Moçambique (UTC+02:00)','UTC':'UTC'}


def parse_schedule(value, zone='UTC'):
    if zone not in TIMEZONES:raise ValueError('Fuso horário inválido.')
    if not value:return None
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:result=result.replace(tzinfo=ZoneInfo(zone))
    return result.astimezone(timezone.utc).replace(tzinfo=None)


def schedule_local(value, zone='Africa/Maputo'):
    if not value:return ''
    if zone not in TIMEZONES:zone='Africa/Maputo'
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M')
