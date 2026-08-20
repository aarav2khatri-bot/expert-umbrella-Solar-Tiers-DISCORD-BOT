"""
storage.py
Very small JSON-file "database". One file per guild under data/<guild_id>.json.
Everything is loaded into memory and saved back to disk on every write.
This is intentionally simple (no external DB) — good enough for a single-bot,
single-process tier list bot.
"""

import json
import os
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_GUILD_DATA = {
    "config": {
        "staff_role": None,        # role id — trusted staff, same access as tiertester
        "tiertester_role": None,   # role id — can /pull /result etc.
        "lt3_role": None,          # role id — waitlist click -> ticket instead of queue
        "verified_role": None,     # role id given after /verify (Verify Account button)
        "tier_roles": {},          # tier name (e.g. "HT1") -> role id, auto-assigned on /result
        "panel_channel": None,
        "waitlist_channel": None,  # channel verified users get access to
        "results_channel": None,
        "log_channel": None,
        "ticket_category": None,
        "cooldown_days": 3,  # days before a tested player can rejoin the waitlist
    },
    "gamemodes": [
        "NethPot", "Sword", "UHC", "DiaPot", "Vanilla",
        "SMP", "Mace", "Axe", "Cart PvP", "DiaSMP"
    ],
    "queues": {},        # gamemode -> [user_id, ...]
    "queue_open": {},    # gamemode -> bool
    "active_testers": {},  # gamemode -> {tester_id_str: player_id} — who's mid-pull right now
    "queue_boards": {},     # gamemode -> {channel_id, message_id} — the live-updating queue embed
    "players": {},       # user_id -> {ign, region, preferred_server, tiers: {gamemode: tier}, rank}
    "tickets": {},       # channel_id (str) -> {user_id, gamemode, status}
    "panel_message": None,  # {channel_id, message_id}
}


def list_guild_ids() -> list[int]:
    """All guild ids that have a data file on disk."""
    ids = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".json") and not fname.endswith(".tmp"):
            try:
                ids.append(int(fname[:-5]))
            except ValueError:
                continue
    return ids


def _path(guild_id: int) -> str:
    return os.path.join(DATA_DIR, f"{guild_id}.json")


def _deep_merge_defaults(data: dict, defaults: dict) -> dict:
    """Ensures older save files gain new default keys without losing data."""
    for k, v in defaults.items():
        if k not in data:
            data[k] = json.loads(json.dumps(v))  # deep copy
        elif isinstance(v, dict) and isinstance(data[k], dict):
            _deep_merge_defaults(data[k], v)
    return data


def load(guild_id: int) -> dict:
    path = _path(guild_id)
    if not os.path.exists(path):
        data = json.loads(json.dumps(DEFAULT_GUILD_DATA))
        save(guild_id, data)
        return data
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = _deep_merge_defaults(data, DEFAULT_GUILD_DATA)
    return data


def save(guild_id: int, data: dict) -> None:
    path = _path(guild_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


class GuildStore:
    """Convenience wrapper: `with GuildStore(guild_id) as store:` autosaves on exit."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.data: dict[str, Any] = load(guild_id)

    def __enter__(self):
        return self.data

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            save(self.guild_id, self.data)
        return False
