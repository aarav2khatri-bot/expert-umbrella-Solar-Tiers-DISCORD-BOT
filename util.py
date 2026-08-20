"""
util.py
Small shared helpers used by more than one cog.
"""

import time


def mark_tested(data: dict, member_id: int) -> None:
    """Stamp a player as just-evaluated, for cooldown purposes."""
    data["players"].setdefault(str(member_id), {"tiers": {}})
    data["players"][str(member_id)]["last_tested_at"] = time.time()


def cooldown_remaining_seconds(data: dict, member_id: int) -> float | None:
    """Returns remaining cooldown in seconds, or None if not on cooldown."""
    info = data["players"].get(str(member_id))
    if not info or "last_tested_at" not in info:
        return None

    cooldown_days = data["config"].get("cooldown_days", 3)
    elapsed = time.time() - info["last_tested_at"]
    remaining = (cooldown_days * 86400) - elapsed
    return remaining if remaining > 0 else None


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not days and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append("less than a minute")
    return ", ".join(parts)
