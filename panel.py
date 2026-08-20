"""
cogs/panel.py
The public-facing panel: a message with two buttons, "Verify Account" and
"Enter Waitlist" — copy and layout matched to the reference screenshot.

Verify Account -> modal (IGN / Region / Preferred Server) -> saves player,
    gives the verified role, opens up the waitlist channel for them.

Enter Waitlist -> must be verified first.
    - If the member has the LT3 role: a private ticket channel is created
      instead of queueing, showing their exact IGN, region and preferred
      server so a tester can run /result on them.
    - Otherwise: a gamemode picker (select menu) -> added to that gamemode's
      queue, provided the queue is open.
"""

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStore, load
from checks import is_lt3
from util import cooldown_remaining_seconds, format_duration
from tickets import create_ticket_channel, player_info_embed
from constants import QUEUE_CAP

PANEL_TITLE = "📝 Evaluation Testing Waitlist"
PANEL_DESCRIPTION = (
    "Upon applying, you will be added to a waitlist channel.\n"
    "Here you will be pinged when a tester of your region is available.\n"
    "If you are LT3 or higher, a priority ticket will be created.\n\n"
    "• Region should be the region of the server you wish to test on\n\n"
    "• Username should be the name of the account you will be testing on\n\n"
    "🛑 **Failure to provide authentic information will result in a denied test.**"
)


class VerifyModal(discord.ui.Modal, title="Verify Account"):
    ign = discord.ui.TextInput(label="Minecraft Username", max_length=32, required=True)
    region = discord.ui.TextInput(label="Region (NA/EU/AS/etc.)", max_length=16, required=True)
    preferred_server = discord.ui.TextInput(
        label="Preferred Server", max_length=64, required=True
    )

    def __init__(self, cog: "PanelCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_verify_submit(interaction, self.ign.value, self.region.value, self.preferred_server.value)


class GamemodeSelect(discord.ui.Select):
    def __init__(self, cog: "PanelCog", gamemodes: list[str]):
        options = [discord.SelectOption(label=gm) for gm in gamemodes]
        super().__init__(placeholder="Choose a gamemode to queue for...", options=options, min_values=1, max_values=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_join_queue(interaction, self.values[0])


class GamemodeSelectView(discord.ui.View):
    def __init__(self, cog: "PanelCog", gamemodes: list[str]):
        super().__init__(timeout=60)
        self.add_item(GamemodeSelect(cog, gamemodes))


class PanelView(discord.ui.View):
    """Persistent view — must be re-added on bot startup with view timeout=None."""

    def __init__(self, cog: "PanelCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Verify Account", style=discord.ButtonStyle.blurple, custom_id="otakutiers:verify")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal(self.cog))

    @discord.ui.button(label="Enter Waitlist", style=discord.ButtonStyle.blurple, custom_id="otakutiers:waitlist")
    async def waitlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_waitlist_click(interaction)


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Re-register the persistent view so buttons keep working after a restart.
        self.bot.add_view(PanelView(self))

    # ---------- /panel ----------

    @app_commands.command(name="panel", description="Post the Verify Account / Enter Waitlist panel in this channel.")
    async def panel(self, interaction: discord.Interaction):
        from checks import is_admin
        if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
            await interaction.response.send_message("You need the Admin role to do that.", ephemeral=True)
            return

        embed = discord.Embed(
            title=PANEL_TITLE,
            description=PANEL_DESCRIPTION,
            color=discord.Color.red(),
        )
        view = PanelView(self)
        msg = await interaction.channel.send(embed=embed, view=view)

        with GuildStore(interaction.guild_id) as data:
            data["panel_message"] = {"channel_id": interaction.channel_id, "message_id": msg.id}
            data["config"]["panel_channel"] = interaction.channel_id

        await interaction.response.send_message("Panel posted.", ephemeral=True)

    # ---------- verify flow ----------

    async def handle_verify_submit(self, interaction: discord.Interaction, ign: str, region: str, server: str):
        guild_id = interaction.guild_id
        member = interaction.user

        with GuildStore(guild_id) as data:
            data["players"].setdefault(str(member.id), {"tiers": {}})
            data["players"][str(member.id)].update(
                {"ign": ign, "region": region, "preferred_server": server}
            )
            verified_role_id = data["config"]["verified_role"]
            waitlist_channel_id = data["config"]["waitlist_channel"]

        # give verified role, if configured
        if verified_role_id:
            role = interaction.guild.get_role(verified_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Verified via panel")
                except discord.Forbidden:
                    pass

        # open up the waitlist channel for them, if configured
        if waitlist_channel_id:
            channel = interaction.guild.get_channel(waitlist_channel_id)
            if channel:
                try:
                    await channel.set_permissions(member, view_channel=True, send_messages=True)
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            f"Verified as **{ign}** ({region}, preferred server: {server}). "
            f"You now have access to the waitlist channel." if waitlist_channel_id
            else f"Verified as **{ign}** ({region}, preferred server: {server}).",
            ephemeral=True,
        )

    # ---------- waitlist flow ----------

    async def handle_waitlist_click(self, interaction: discord.Interaction):
        member = interaction.user
        data = load(interaction.guild_id)

        if str(member.id) not in data["players"]:
            await interaction.response.send_message(
                "You need to **Verify Account** first.", ephemeral=True
            )
            return

        remaining = cooldown_remaining_seconds(data, member.id)
        if remaining is not None:
            await interaction.response.send_message(
                f"You have **{format_duration(remaining)}** of cooldown left before you can test again.",
                ephemeral=True,
            )
            return

        if is_lt3(member):
            await self.create_ticket(interaction, member, data)
            return

        gamemodes = data["gamemodes"]
        await interaction.response.send_message(
            "Pick a gamemode to join the waitlist for:",
            view=GamemodeSelectView(self, gamemodes),
            ephemeral=True,
        )

    async def handle_join_queue(self, interaction: discord.Interaction, gamemode: str):
        guild_id = interaction.guild_id
        member = interaction.user

        with GuildStore(guild_id) as data:
            if not data["queue_open"].get(gamemode, False):
                await interaction.response.edit_message(content=f"Queue for **{gamemode}** is currently closed.", view=None)
                return

            queue = data["queues"].setdefault(gamemode, [])
            if member.id in queue:
                await interaction.response.edit_message(content=f"You're already in the **{gamemode}** queue.", view=None)
                return

            if len(queue) >= QUEUE_CAP:
                await interaction.response.edit_message(
                    content=f"The **{gamemode}** queue is full ({QUEUE_CAP}/{QUEUE_CAP}). Try again later.", view=None
                )
                return

            queue.append(member.id)
            position = len(queue)

        await interaction.response.edit_message(
            content=f"Joined the **{gamemode}** waitlist — position **#{position}**.", view=None
        )

    # ---------- LT3 ticket flow ----------

    async def create_ticket(self, interaction: discord.Interaction, member: discord.Member, data: dict):
        guild = interaction.guild

        channel, tiertester_role = await create_ticket_channel(guild, data, member, name_prefix="eval")

        with GuildStore(guild.id) as store_data:
            store_data["tickets"][str(channel.id)] = {
                "user_id": member.id, "gamemode": None, "status": "open"
            }

        info = data["players"].get(str(member.id), {})
        embed = player_info_embed("LT3 Evaluation Ticket", info)

        ping = tiertester_role.mention if tiertester_role else "Testers"
        await channel.send(
            content=f"{member.mention} {ping}",
            embed=embed,
        )
        await channel.send(
            f"A tester can run `/close ranking:<rank>` in this channel once "
            f"evaluation is complete — it'll post the result and lock this ticket."
        )

        await interaction.response.send_message(f"Ticket opened: {channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
