"""PIREP slash-field parser.

A PIREP looks like:

    UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP /RM "SMOOTH RIDE"

We split on "/" tokens, treat the leading `UA`/`UU` prefix as the report
type marker, then walk the rest as (key, value) pairs. Values may
contain spaces (e.g. `/TB MOD CHOP`); the rule is that the next "/"
starts the next field.

If the input contains no recognised slash field at all, we raise
`ParseError` — the caller decides whether to quarantine or drop.
Otherwise missing fields become `None`.

See `docs/MODULE_DESIGN.md` §3.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from chopcast.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PirepFields:
    """Structured view of one parsed PIREP string.

    Missing or unparseable fields are `None`. `raw` is preserved verbatim
    so downstream code (and golden-corpus tests) can re-parse if needed.
    """

    location: str | None
    location_parsed: tuple[float, float] | None
    obs_time: datetime | None
    flight_level: int | None
    aircraft_type: str | None
    turbulence: str | None
    sky_conditions: str | None
    weather: str | None
    temperature: int | None
    icing: str | None
    remarks: str | None
    raw: str


# ---------------------------------------------------------------------------
# Field grammar
# ---------------------------------------------------------------------------
# Order matters: longer tokens must be tried before shorter prefixes
# (e.g. "/SKC" before "/SK").
_FIELD_KEYS: tuple[str, ...] = (
    "/OV",  # location
    "/TM",  # time
    "/FL",  # flight level
    "/TP",  # aircraft type
    "/TB",  # turbulence
    "/SK",  # sky conditions
    "/WX",  # weather
    "/TA",  # temperature (C)
    "/IC",  # icing
    "/RM",  # remarks (free text, may contain spaces and slashes)
)

# Time: HHMM or HHMMSS, with optional Z suffix.
_TIME_RE = re.compile(r"^(?P<h>\d{2})(?P<m>\d{2})(?P<s>\d{2})?Z?$")

# /OV: may be a 3-letter navaid, a 4-letter airport ICAO, or a 4-char
# radial+distance like "SFO030020" (3-letter navaid, 3-digit radial,
# 3-digit distance). We accept anything that starts with letters and
# is followed by 0-6 digits; navaid lookup is the parser's, not ours.
_OV_RE = re.compile(r"^[A-Z]{3,4}(?:\d{3,6})?$")

# /FL: digits, possibly with trailing "FT" or "FL"; examples: "350",
# "35000", "FL350", "350FT".
_FL_RE = re.compile(r"^(?:FL)?(?P<digits>\d{1,5})(?:FT)?$", re.IGNORECASE)

# /TA: signed integer in Celsius.
_TA_RE = re.compile(r"^(?P<sign>[+-]?)(?P<mag>\d{1,3})$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tokenize(raw: str) -> list[str]:
    """Split a PIREP into slash-delimited tokens.

    The first token is the report-type marker (`UA`, `UU`, `UA-OVR`,
    etc.); subsequent tokens start with a slash and are field tags.
    We tolerate multiple spaces and the BOM-less ASCII subset.

    We split on the pattern ` /` (slash preceded by whitespace) so
    each slash starts a fresh token. The leading `/` is preserved on
    each field tag. Field tags whose value is glued (`/FL350`,
    `/FLUNKN`) are split only when the tag matches one of the
    known keys in `_FIELD_KEYS` — that prevents accidental splits
    on values like `SFO030020`.
    """
    s = raw.strip()
    if not s:
        return []
    parts = re.split(r"\s+", s, maxsplit=1)
    head = parts[0]
    tail = parts[1] if len(parts) > 1 else ""
    out: list[str] = [head]
    if tail:
        for chunk in re.split(r"\s+/", tail):
            chunk = chunk.strip()
            if not chunk:
                continue
            tag = "/" + chunk if not chunk.startswith("/") else chunk
            # Strip the leading slash for key matching.
            key_candidate = tag[1:].upper()
            matched_key: str | None = None
            for k in _FIELD_KEYS:
                kk = k[1:]
                if key_candidate == kk or key_candidate.startswith(kk):
                    matched_key = k
                    break
            if matched_key and len(key_candidate) > len(matched_key) - 1:
                # The tag has an inline value glued to the key.
                rest = tag[1 + len(matched_key) - 1 :]
                out.append(matched_key)
                out.append(rest.strip())
            elif matched_key and " " in chunk:
                # The tag is the key alone, followed by a value later.
                out.append(matched_key)
            else:
                out.append(tag)
    return out


def _slice_field(tokens: list[str], idx: int) -> str | None:
    """Return the value following token `tokens[idx]`, or None.

    The next slash-field starts at the first later token whose first two
    characters are "/X" where X is alphabetic. So we walk until we see
    a recognised field key.
    """
    parts: list[str] = []
    for j in range(idx + 1, len(tokens)):
        tok = tokens[j]
        if tok.startswith("/") and len(tok) >= 2 and tok[1].isalpha():
            break
        parts.append(tok)
    value = " ".join(parts).strip()
    return value or None


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    hh = int(m.group("h"))
    mm = int(m.group("m"))
    ss = int(m.group("s") or "00")
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return None
    today = datetime.now(timezone.utc).date()
    try:
        return datetime(today.year, today.month, today.day, hh, mm, ss, tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_flight_level(value: str | None) -> int | None:
    if value is None:
        return None
    # The first numeric run wins. We accept both "FL350" and "35000"
    # (feet). Convert flight levels to feet by multiplying by 100 so
    # the downstream "altitude" column is uniform.
    m = _FL_RE.match(value.strip())
    if not m:
        return None
    digits = int(m.group("digits"))
    if value.strip().upper().startswith("FL"):
        return digits * 100
    # If the raw value is small (<600) it's a flight level in hundreds
    # of feet even without the FL prefix; otherwise it is feet.
    if digits < 600:
        return digits * 100
    return digits


def _parse_temperature(value: str | None) -> int | None:
    if value is None:
        return None
    m = _TA_RE.match(value.strip())
    if not m:
        return None
    sign = -1 if m.group("sign") == "-" else 1
    return sign * int(m.group("mag"))


def _parse_location(value: str | None) -> tuple[float, float] | None:
    """Lightweight /OV decoder for already-numeric locations.

    /OV may be a navaid code (e.g. `SFO`) or a relative position
    (`SFO030020` = 30° radial at 20 nm). Navaid lookup is the navaid
    module's job; here we return None for non-numeric input so the
    caller can fall through.
    """
    if value is None:
        return None
    tokens = value.split()
    if len(tokens) >= 2:
        # "SFO 037020" style: lat/lon already given.
        try:
            lat = float(tokens[1][:3])
            lon = -float(tokens[2][:3]) if len(tokens) >= 3 else 0.0
            return (lat, lon)
        except (ValueError, IndexError):
            return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_pirep(raw: str) -> PirepFields:
    """Parse a PIREP string. Returns a `PirepFields`.

    Raises `ParseError` only if the input contains no recognised slash
    field at all — that's not a PIREP and should be quarantined.
    """
    if raw is None:
        raise ValueError("raw must not be None")  # programming error
    tokens = _tokenize(raw)
    if not tokens:
        raise ValueError("raw is empty")  # programming error

    # Walk tokens; for each recognised field key, capture its value.
    captured: dict[str, str | None] = {}
    for i, tok in enumerate(tokens):
        if not tok.startswith("/"):
            continue
        key = tok[:3].upper()
        if key in _FIELD_KEYS:
            captured[key] = _slice_field(tokens, i)

    if not captured:
        log.warning("parser.no_fields_recognised", raw_preview=raw[:60])
        # Surface as a ValueError so the caller can decide. We do not
        # import ParseError here to keep this module dependency-light;
        # the pipeline layer translates.
        raise ValueError(f"no recognised slash fields in: {raw[:60]!r}")

    # Extract structured fields.
    location = captured.get("/OV")
    obs_time = _parse_time(captured.get("/TM"))
    flight_level = _parse_flight_level(captured.get("/FL"))
    aircraft_type = captured.get("/TP")
    turbulence = captured.get("/TB")
    sky_conditions = captured.get("/SK")
    weather = captured.get("/WX")
    temperature = _parse_temperature(captured.get("/TA"))
    icing = captured.get("/IC")
    remarks = captured.get("/RM")

    return PirepFields(
        location=location,
        location_parsed=_parse_location(location),
        obs_time=obs_time,
        flight_level=flight_level,
        aircraft_type=aircraft_type,
        turbulence=turbulence,
        sky_conditions=sky_conditions,
        weather=weather,
        temperature=temperature,
        icing=icing,
        remarks=remarks,
        raw=raw,
    )


__all__ = ["PirepFields", "parse_pirep"]