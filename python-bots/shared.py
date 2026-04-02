"""
Shared utilities for all four WoW TBC Classic Anniversary Discord bots.
  - Timezone helpers (DST-safe via zoneinfo)
  - Per-event state computation (BG rotation, AGM, DMF, STV)
  - Ranking system (①②③④ prefix)
  - Per-guild config (JSON files)
  - Misc helpers
"""
from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo
from pathlib import Path
import discord
import json
import logging
import sys

MT = ZoneInfo("America/Denver")   # Mountain Time (BG weekends)
ET = ZoneInfo("America/New_York")  # Eastern Time (AGM / DMF / STV)

# ── Logging ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent


class _LogStream:
    """File-like wrapper that routes write() calls through a logging handler."""

    def __init__(self, logger: logging.Logger, level: int = logging.INFO) -> None:
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, msg: str) -> int:
        self._buf += msg
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self._logger.log(self._level, line)
        return len(msg)

    def flush(self) -> None:
        if self._buf:
            self._logger.log(self._level, self._buf)
            self._buf = ""


def setup_logging(name: str, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> None:
    """Redirect stdout/stderr to a rotating log file (logs/<name>.log).

    Keeps up to backup_count rotated files, each up to max_bytes (default 5 MB).
    """
    log_dir = SCRIPT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    sys.stdout = _LogStream(logger)
    sys.stderr = _LogStream(logger, logging.ERROR)


# ── Utilities ──────────────────────────────────────────────────────────────

def format_countdown(ms: int) -> str:
    if ms <= 0:
        return "now"
    s = ms // 1000
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m     = s // 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def find_image(base_path: str) -> str | None:
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        p = Path(base_path + ext)
        if p.exists():
            return str(p)
    return None


# ── Config ─────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"[WARN] Could not parse config {path}: {e}")
        return {}


async def send_pings(bot: discord.Client, config_path: str, make_message: Callable[[str], str]) -> None:
    """Send a message to every configured guild channel.

    make_message receives the role_id string and returns the message to send.
    """
    config = load_config(config_path)
    for gid, cfg in config.items():
        try:
            guild = bot.get_guild(int(gid))
            if guild:
                ch = guild.get_channel(int(cfg["channelId"]))
                if ch:
                    await ch.send(make_message(cfg["roleId"]))
        except Exception as e:
            print(f"[WARN] Ping failed for guild {gid}: {e}")


def save_guild_config(path: str, guild_id: int | str,
                      channel_id: int | str, role_id: int | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config(path)
    cfg[str(guild_id)] = {"channelId": str(channel_id), "roleId": str(role_id)}
    p.write_text(json.dumps(cfg, indent=2))


# ── BG Weekend rotation ────────────────────────────────────────────────────

BATTLEGROUNDS = [
    {"name": "Alterac Valley",   "shortName": "AV"},
    {"name": "Eye of the Storm", "shortName": "EOTS"},
    {"name": "Warsong Gulch",    "shortName": "WSG"},
    {"name": "Arathi Basin",     "shortName": "AB"},
]

# Anchor: Tuesday March 24 2026 at 2:00 AM MDT = 08:00 UTC — confirmed AV week
_BG_ANCHOR = datetime(2026, 3, 24, 8, 0, 0, tzinfo=timezone.utc)


def _bg_week_start(now: datetime) -> datetime:
    """Most recent Tuesday 2:00 AM Mountain Time that is <= now."""
    now_mt = now.astimezone(MT)
    # Python weekday: Mon=0 Tue=1 ... Sun=6
    days_since_tue = (now_mt.weekday() - 1) % 7
    tue_date = (now_mt - timedelta(days=days_since_tue)).date()
    tue_2am = datetime(tue_date.year, tue_date.month, tue_date.day, 2, 0, 0, tzinfo=MT)
    if tue_2am.astimezone(timezone.utc) > now:
        # Today is Tuesday but still before 2 AM — step back one week
        prev = tue_date - timedelta(days=7)
        tue_2am = datetime(prev.year, prev.month, prev.day, 2, 0, 0, tzinfo=MT)
    return tue_2am.astimezone(timezone.utc)


def get_rotation_info(now: datetime | None = None) -> dict:
    """
    Returns the current BG rotation state.
    Keys: currentBG, nextBG, isActive, msUntilStart, msUntilEnd
    """
    if now is None:
        now = datetime.now(timezone.utc)
    week_start   = _bg_week_start(now)
    weekend_start = week_start + timedelta(days=2)   # Thursday 2am MT ≈ +48 h UTC
    week_end      = week_start + timedelta(days=7)

    weeks = round((week_start - _BG_ANCHOR).total_seconds() / (7 * 24 * 3600))
    bg_idx   = weeks % len(BATTLEGROUNDS)
    next_idx = (bg_idx + 1) % len(BATTLEGROUNDS)

    now_ms = int(now.timestamp() * 1000)
    ws_ms  = int(weekend_start.timestamp() * 1000)
    we_ms  = int(week_end.timestamp() * 1000)
    is_active = ws_ms <= now_ms < we_ms

    return {
        "currentBG":    BATTLEGROUNDS[bg_idx],
        "nextBG":       BATTLEGROUNDS[next_idx],
        "isActive":     is_active,
        "msUntilStart": max(0, ws_ms - now_ms),
        "msUntilEnd":   max(0, we_ms - now_ms),
    }


# ── Arena Grand Master ─────────────────────────────────────────────────────

_CHEST_INTERVAL_MS = 3 * 60 * 60 * 1000   # 3 hours
_CHEST_WINDOW_MS   = 5 * 60 * 1000         # 5-minute active window


def get_agm_state(now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    et = now.astimezone(ET)
    ms_into_day = (et.hour * 3600 + et.minute * 60 + et.second) * 1000
    slot_ms = ms_into_day % _CHEST_INTERVAL_MS
    is_up   = slot_ms < _CHEST_WINDOW_MS
    return {
        "isUp":        is_up,
        "msUntilNext": _CHEST_INTERVAL_MS - slot_ms,
        "msWindowLeft": max(0, _CHEST_WINDOW_MS - slot_ms),
    }


# ── Darkmoon Faire ─────────────────────────────────────────────────────────

def _dmf_start(year: int, month: int) -> datetime:
    """First Monday on or after the 1st of the month at 00:01 Eastern."""
    first_of_month = datetime(year, month, 1, 0, 0, 0, tzinfo=ET)
    days_until_mon = (7 - first_of_month.weekday()) % 7  # 0 if 1st is already Monday
    monday = first_of_month + timedelta(days=days_until_mon)
    return monday.replace(minute=1)


def get_dmf_state(now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    et = now.astimezone(ET)
    now_ms = int(now.timestamp() * 1000)

    # Check this month and next
    months = [
        (et.year, et.month),
        (et.year + 1, 1) if et.month == 12 else (et.year, et.month + 1),
    ]
    for y, m in months:
        start = _dmf_start(y, m)
        end   = start + timedelta(days=7)
        s_ms  = int(start.astimezone(timezone.utc).timestamp() * 1000)
        e_ms  = int(end.astimezone(timezone.utc).timestamp() * 1000)
        if s_ms <= now_ms < e_ms:
            return {"active": True,  "msUntilEnd": e_ms - now_ms, "msUntilStart": 0}
        if now_ms < s_ms:
            return {"active": False, "msUntilStart": s_ms - now_ms, "msUntilEnd": 0}

    # Fallback to month after next
    y2, m2 = (et.year + 1, 2) if et.month == 11 else (
              (et.year + 1, 1) if et.month == 12 else (et.year, et.month + 2))
    s_ms = int(_dmf_start(y2, m2).astimezone(timezone.utc).timestamp() * 1000)
    return {"active": False, "msUntilStart": s_ms - now_ms, "msUntilEnd": 0}


# ── STV Fishing Extravaganza ───────────────────────────────────────────────

def get_stv_state(now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    et = now.astimezone(ET)
    now_ms = int(now.timestamp() * 1000)

    # Python weekday: Mon=0 ... Sat=5 Sun=6
    days_since_sun = (et.weekday() + 1) % 7   # 0 if today is Sunday
    sunday_dt = et - timedelta(days=days_since_sun)
    sunday_date = sunday_dt.date()

    this_start = datetime(sunday_date.year, sunday_date.month, sunday_date.day, 14, 0, 0, tzinfo=ET)
    this_end   = datetime(sunday_date.year, sunday_date.month, sunday_date.day, 16, 0, 0, tzinfo=ET)
    next_start = this_start + timedelta(days=7)

    ts_ms = int(this_start.astimezone(timezone.utc).timestamp() * 1000)
    te_ms = int(this_end.astimezone(timezone.utc).timestamp() * 1000)
    ns_ms = int(next_start.astimezone(timezone.utc).timestamp() * 1000)

    if ts_ms <= now_ms < te_ms:
        return {"active": True,  "msUntilEnd": te_ms - now_ms, "msUntilStart": 0}
    if now_ms < ts_ms:
        return {"active": False, "msUntilStart": ts_ms - now_ms, "msUntilEnd": 0}
    return {"active": False, "msUntilStart": ns_ms - now_ms, "msUntilEnd": 0}


# ── Ranking ────────────────────────────────────────────────────────────────

RANK_SYMBOLS = ["①", "②", "③", "④"]
_BIG = 100 * 24 * 60 * 60 * 1000   # 100 days — puts inactive events after active ones


def compute_rank(bot: str, now: datetime | None = None) -> int:
    """
    Returns 1-4 rank for the given bot.
    1 = most urgent (active + soonest to end, or soonest to start if all inactive).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    ri  = get_rotation_info(now)
    agm = get_agm_state(now)
    dmf = get_dmf_state(now)
    stv = get_stv_state(now)

    scores = {
        "bg":  ri["msUntilEnd"]      if ri["isActive"]  else _BIG + ri["msUntilStart"],
        "agm": agm["msWindowLeft"]   if agm["isUp"]     else _BIG + agm["msUntilNext"],
        "dmf": dmf["msUntilEnd"]     if dmf["active"]   else _BIG + dmf["msUntilStart"],
        "stv": stv["msUntilEnd"]     if stv["active"]   else _BIG + stv["msUntilStart"],
    }
    ranked = sorted(scores, key=lambda k: scores[k])
    return ranked.index(bot) + 1


def rank_prefix(bot: str, now: datetime | None = None) -> str:
    r = compute_rank(bot, now)
    return RANK_SYMBOLS[r - 1] if r <= 4 else str(r)
