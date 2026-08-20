"""
tickets.py
Shared logic for creating a private evaluation ticket channel — used both by
the LT3 waitlist-click flow (panel.py) and by /pull (queue.py).
"""

import discord


async def create_ticket_channel(guild: discord.Guild, data: dict, member: discord.Member, name_prefix: str = "eval"):
    """Creates a private text channel visible only to the member, the
    TierTester role, and the bot. Returns (channel, tiertester_role)."""
    category_id = data["config"]["ticket_category"]
    category = guild.get_channel(category_id) if category_id else None
    tiertester_role_id = data["config"]["tiertester_role"]
    tiertester_role = guild.get_role(tiertester_role_id) if tiertester_role_id else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if tiertester_role:
        overwrites[tiertester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel_name = f"{name_prefix}-{member.name}"[:90]
    channel = await guild.create_text_channel(
        channel_name, category=category, overwrites=overwrites,
        reason=f"Evaluation ticket for {member}"
    )
    return channel, tiertester_role


def player_info_embed(title: str, player_data: dict) -> discord.Embed:
    """Small embed showing a player's verified IGN / region / preferred server."""
    embed = discord.Embed(title=title, color=discord.Color.red())
    embed.add_field(name="Username", value=player_data.get("ign", "unknown"), inline=False)
    embed.add_field(name="Region", value=player_data.get("region", "unknown"), inline=False)
    embed.add_field(name="Preferred Server", value=player_data.get("preferred_server", "unknown"), inline=False)
    return embed
