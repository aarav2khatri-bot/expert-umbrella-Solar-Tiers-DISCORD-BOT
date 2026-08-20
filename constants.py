"""
constants.py
Shared constants used across cogs.

TIERS is ordered worst -> best (LT5 .. HT1), matching how /close's dropdown
and every other tier picker in the bot should read.
"""

TIERS = [
    "LT5", "HT5", "LT4", "HT4", "LT3", "HT3",
    "LT2", "HT2", "LT1", "HT1",
]

TIER_LABELS = {
    "LT5": "Low Tier 5", "HT5": "High Tier 5",
    "LT4": "Low Tier 4", "HT4": "High Tier 4",
    "LT3": "Low Tier 3", "HT3": "High Tier 3",
    "LT2": "Low Tier 2", "HT2": "High Tier 2",
    "LT1": "Low Tier 1", "HT1": "High Tier 1",
}

UNRANKED = "UNRANKED"
UNRANKED_LABEL = "Unranked"

QUEUE_CAP = 20  # matches the queue board's "(X/20)" display
