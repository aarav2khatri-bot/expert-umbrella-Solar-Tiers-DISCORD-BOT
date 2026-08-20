"""
cogs/debug.py
Temporary diagnostic command — run /whoami and screenshot the result.
Delete this file (and its line in bot.py's COGS list) once the admin
lockout issue is confirmed fixed.
"""

import discord
from discord import app_commands
from discord.ext import commands

from checks import is_admin


class DebugCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="whoami", description="Diagnostic: shows what the bot sees for your permissions.")
    async def whoami(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild

        lines = [
            f"Your user ID: `{member.id}`",
            f"Guild owner ID: `{guild.owner_id}`",
            f"Are you the owner?: `{guild.owner_id == member.id}`",
            f"isinstance Member: `{isinstance(member, discord.Member)}`",
        ]

        if isinstance(member, discord.Member):
            lines.append(f"guild_permissions.administrator: `{member.guild_permissions.administrator}`")
            lines.append(f"your role ids: `{[r.id for r in member.roles]}`")
            lines.append(f"is_admin() result: `{is_admin(member)}`")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DebugCog(bot))
