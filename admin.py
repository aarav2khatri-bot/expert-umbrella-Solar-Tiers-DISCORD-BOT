"""
cogs/admin.py
Admin-only configuration: /setchannel and /roles.

Admin is NOT a configurable bot role — see checks.py. It's simply the real
Discord server owner or anyone with real Discord "Administrator" permission.
That means every command in this file uses the exact same @require_admin()
check, with no special-casing or bootstrap step needed anywhere.
"""

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStore, load
from checks import require_admin, NotAdmin
from constants import TIERS

CHANNEL_TYPES = [
    app_commands.Choice(name="panel", value="panel_channel"),
    app_commands.Choice(name="waitlist", value="waitlist_channel"),
    app_commands.Choice(name="results", value="results_channel"),
    app_commands.Choice(name="log", value="log_channel"),
    app_commands.Choice(name="ticket_category", value="ticket_category"),
]

ROLE_TYPES = [
    app_commands.Choice(name="staff", value="staff_role"),
    app_commands.Choice(name="tiertester", value="tiertester_role"),
    app_commands.Choice(name="lt3", value="lt3_role"),
    app_commands.Choice(name="verified", value="verified_role"),
] + [
    app_commands.Choice(name=f"tier_{t}", value=f"tier:{t}") for t in TIERS
]


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, NotAdmin):
            await interaction.response.send_message(
                "Only the server owner or someone with real Discord Administrator permission can do that.",
                ephemeral=True,
            )
        else:
            raise error

    # ---------- /setchannel ----------

    @app_commands.command(name="setchannel", description="Set a config channel (admin only).")
    @app_commands.describe(type="Which channel slot to set", channel="The channel or category to use")
    @app_commands.choices(type=CHANNEL_TYPES)
    @require_admin()
    async def setchannel(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        channel: discord.abc.GuildChannel,
    ):
        with GuildStore(interaction.guild_id) as data:
            data["config"][type.value] = channel.id

        await interaction.response.send_message(
            f"Set **{type.name}** channel to {channel.mention}.", ephemeral=True
        )

    # ---------- /roles ----------

    role_group = app_commands.Group(name="roles", description="Configure bot roles.")

    @role_group.command(
        name="set",
        description="Set a role slot: staff, tiertester, lt3, verified, or a tier (e.g. tier_HT1).",
    )
    @app_commands.describe(type="Which role slot to set", role="The role to assign")
    @app_commands.choices(type=ROLE_TYPES)
    @require_admin()
    async def roles_set(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        role: discord.Role,
    ):
        with GuildStore(interaction.guild_id) as store:
            if type.value.startswith("tier:"):
                tier_name = type.value.split(":", 1)[1]
                store["config"]["tier_roles"][tier_name] = role.id
            else:
                store["config"][type.value] = role.id

        await interaction.response.send_message(
            f"Set **{type.name}** role to {role.mention}.", ephemeral=True
        )

    @role_group.command(name="view", description="View all configured roles.")
    @require_admin()
    async def roles_view(self, interaction: discord.Interaction):
        data = load(interaction.guild_id)
        cfg = data["config"]

        def fmt(role_id):
            if not role_id:
                return "*not set*"
            role = interaction.guild.get_role(role_id)
            return role.mention if role else f"`{role_id}` (missing)"

        embed = discord.Embed(title="OtakuTiers Role Config", color=discord.Color.blurple())
        embed.add_field(
            name="Admin",
            value="Server owner, or anyone with real Discord Administrator permission",
            inline=False,
        )
        embed.add_field(name="Staff", value=fmt(cfg["staff_role"]), inline=True)
        embed.add_field(name="TierTester", value=fmt(cfg["tiertester_role"]), inline=True)
        embed.add_field(name="LT3", value=fmt(cfg["lt3_role"]), inline=True)
        embed.add_field(name="Verified", value=fmt(cfg["verified_role"]), inline=True)

        tier_roles = cfg.get("tier_roles", {})
        tier_lines = "\n".join(f"**{t}**: {fmt(tier_roles.get(t))}" for t in TIERS)
        embed.add_field(name="Tier Roles", value=tier_lines or "*none set*", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @role_group.command(name="add_tester", description="Give a member the TierTester role.")
    @require_admin()
    async def roles_add_tester(self, interaction: discord.Interaction, member: discord.Member):
        await self._add_tester(interaction, member)

    @role_group.command(name="remove_tester", description="Remove a member's TierTester role.")
    @require_admin()
    async def roles_remove_tester(self, interaction: discord.Interaction, member: discord.Member):
        await self._remove_tester(interaction, member)

    # ---------- shared tester add/remove logic ----------

    async def _add_tester(self, interaction: discord.Interaction, member: discord.Member):
        data = load(interaction.guild_id)
        role_id = data["config"]["tiertester_role"]
        if not role_id:
            await interaction.response.send_message("TierTester role isn't set yet — use `/roles set`.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        await member.add_roles(role, reason=f"Added as TierTester by {interaction.user}")
        await interaction.response.send_message(f"Added {member.mention} as a TierTester.", ephemeral=True)

    async def _remove_tester(self, interaction: discord.Interaction, member: discord.Member):
        data = load(interaction.guild_id)
        role_id = data["config"]["tiertester_role"]
        if not role_id:
            await interaction.response.send_message("TierTester role isn't set yet — use `/roles set`.", ephemeral=True)
            return
        role = interaction.guild.get_role(role_id)
        await member.remove_roles(role, reason=f"Removed as TierTester by {interaction.user}")
        await interaction.response.send_message(f"Removed {member.mention} as a TierTester.", ephemeral=True)

    # ---------- /addtester, /removetester (top-level shortcuts) ----------

    @app_commands.command(name="addtester", description="Give a member the TierTester role (admin only).")
    @require_admin()
    async def addtester(self, interaction: discord.Interaction, member: discord.Member):
        await self._add_tester(interaction, member)

    @app_commands.command(name="removetester", description="Remove a member's TierTester role (admin only).")
    @require_admin()
    async def removetester(self, interaction: discord.Interaction, member: discord.Member):
        await self._remove_tester(interaction, member)

    # ---------- /setcooldown ----------

    @app_commands.command(
        name="setcooldown",
        description="Set how many days a player must wait after being tested before rejoining the waitlist.",
    )
    @app_commands.describe(days="Cooldown length in days")
    @require_admin()
    async def setcooldown(self, interaction: discord.Interaction, days: app_commands.Range[int, 0, 365]):
        with GuildStore(interaction.guild_id) as data:
            data["config"]["cooldown_days"] = days

        await interaction.response.send_message(
            f"Cooldown set to **{days} day(s)**.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    cog = AdminCog(bot)
    await bot.add_cog(cog)
