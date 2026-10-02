from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_timezone(value: str) -> str:
    # ZoneInfo accepts IANA names and raises for unknown or malformed timezone strings.
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use a valid IANA timezone, such as Asia/Kolkata.") from None
    return value
