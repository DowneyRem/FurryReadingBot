from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%S%z")

def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        s = s.strip()
        if len(s) >= 5 and (s[-5] in "+-" and s[-3] != ":"):
            s = s[:-2] + ":" + s[-2:]
        return datetime.fromisoformat(s)
    except Exception:
        return None