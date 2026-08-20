"""
checks.py
Role-based permission helpers.

- Admin: the real Discord server owner, or anyone with the real Discord
  "Administrator" permission. Not a configurable bot role, on purpose —
  nothing to set up, nothing that can lock a server out. Full control
  (setchannel, roles, tester management, everything testers can do).
- Staff / TierTester roles: configurable, grant /pull /result /openqueue
  /closequeue /skip access.
- Admin always passes every check (admin is a superset).
"""

import discord
from storage import load


def _has_role(member: discord.Member, role_id: int | None) -> bool:
    if role_id is None:
        return False
    return any(r.id == role_id for r in member.roles)


def is_admin(member: discord.Member) -> bool:
    if member.guild.owner_id == member.id:
        return True
    return member.guild_permissions.administrator


def is_staff(member: discord.Member) -> bool:
    if is_admin(member):
        return True
    data = load(member.guild.id)
    return _has_role(member, data["config"]["staff_role"])


def is_tiertester(member: discord.Member) -> bool:
    if is_admin(member) or is_staff(member):
        return True
    data = load(member.guild.id)
    return _has_role(member, data["config"]["tiertester_role"])


def is_lt3(member: discord.Member) -> bool:
    data = load(member.guild.id)
    return _has_role(member, data["config"]["lt3_role"])


class NotAdmin(discord.app_commands.CheckFailure):
    pass


class NotTierTester(discord.app_commands.CheckFailure):
    pass


def require_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            raise NotAdmin()
        if not is_admin(interaction.user):
            raise NotAdmin()
        return True
    return discord.app_commands.check(predicate)


def require_tiertester():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            raise NotTierTester()
        if not is_tiertester(interaction.user):
            raise NotTierTester()
        return True
    return discord.app_commands.check(predicate)
