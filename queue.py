"""
cogs/queue.py
/openqueue  - tiertester+ only. Posts a live "Tester(s) Available!" board
              (red embed, @here ping) with Join/Leave buttons attached. It
              refreshes every 10 seconds while open, listing the queue
              (capped at 20) and which testers are currently active.
/closequeue - tiertester+ only. Stops the refresh, disables the buttons.
/pull       - tiertester+ only. Pops the next player and opens a private
              ticket for them (their verified IGN/region/preferred server
              shown inside), same as the LT3 flow. Marks the tester "active".
/skip       - tiertester+ only. Moves the next player in queue to the back
              instead of pulling them, so someone else gets pulled next.
/leave      - everyone. Removes you from any queue you're currently in.

The board's Join/Leave buttons use discord.ui.DynamicItem so they keep
working even after a bot restart — the gamemode is encoded right in the
button's custom_id rather than tracked in memory.
"""

import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

from storage import GuildStore, load
from checks import require_tiertester, NotTierTester, is_lt3
from tickets import create_ticket_channel, player_info_embed
from util import cooldown_remaining_seconds, format_duration
from constants import QUEUE_CAP

REFRESH_SECONDS = 10


async def gamemode_choices(interaction: discord.Interaction, current: str):
    data = load(interaction.guild_id)
    return [
        app_commands.Choice(name=gm, value=gm)
        for gm in data["gamemodes"] if current.lower() in gm.lower()
    ][:25]


def build_board_embed(data: dict, gamemode: str) -> discord.Embed:
    queue = data["queues"].get(gamemode, [])
    active = data.get("active_testers", {}).get(gamemode, {})

    queue_lines = [f"{i}. <@{uid}>" for i, uid in enumerate(queue[:QUEUE_CAP], start=1)]
    queue_text = "\n".join(queue_lines) if queue_lines else "*empty*"

    active_lines = [f"{i}. <@{tester_id}>" for i, tester_id in enumerate(active.keys(), start=1)]
    active_text = "\n".join(active_lines) if active_lines else "*none*"

    embed = discord.Embed(
        title="Tester(s) Available!",
        description=(
            "\U0001F504 The queue updates every 10 seconds.\n"
            "Use the buttons below (or `/leave`) if you wish to be removed from the queue.\n\n"
            f"**Queue ({len(queue)}/{QUEUE_CAP}):**\n{queue_text}\n\n"
            f"**Active Testers:**\n{active_text}"
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text=f"Gamemode: {gamemode}")
    return embed


async def try_join_queue(interaction: discord.Interaction, gamemode: str):
    """Shared logic for the board's Join button. Handles verification,
    cooldown, LT3 (ticket instead of queue), capacity, and duplicates."""
    guild_id = interaction.guild_id
    member = interaction.user
    data = load(guild_id)

    if str(member.id) not in data["players"]:
        await interaction.response.send_message("You need to **Verify Account** first (use the panel).", ephemeral=True)
        return

    remaining = cooldown_remaining_seconds(data, member.id)
    if remaining is not None:
        await interaction.response.send_message(
            f"You have **{format_duration(remaining)}** of cooldown left before you can test again.", ephemeral=True
        )
        return

    if is_lt3(member):
        channel, tiertester_role = await create_ticket_channel(interaction.guild, data, member, name_prefix=gamemode)
        with GuildStore(guild_id) as store:
            store["tickets"][str(channel.id)] = {"user_id": member.id, "gamemode": gamemode, "status": "open"}
        info = data["players"].get(str(member.id), {})
        embed = player_info_embed(f"{gamemode} Evaluation Ticket", info)
        ping = tiertester_role.mention if tiertester_role else "Testers"
        await channel.send(content=f"{member.mention} {ping}", embed=embed)
        await interaction.response.send_message(f"Ticket opened: {channel.mention}", ephemeral=True)
        return

    with GuildStore(guild_id) as store:
        if not store["queue_open"].get(gamemode, False):
            await interaction.response.send_message(f"The **{gamemode}** queue is currently closed.", ephemeral=True)
            return
        queue = store["queues"].setdefault(gamemode, [])
        if member.id in queue:
            await interaction.response.send_message(f"You're already in the **{gamemode}** queue.", ephemeral=True)
            return
        if len(queue) >= QUEUE_CAP:
            await interaction.response.send_message(
                f"The **{gamemode}** queue is full ({QUEUE_CAP}/{QUEUE_CAP}). Try again later.", ephemeral=True
            )
            return
        queue.append(member.id)
        position = len(queue)

    await interaction.response.send_message(f"Joined the **{gamemode}** queue — position **#{position}**.", ephemeral=True)


async def try_leave_queue(interaction: discord.Interaction, gamemode: str):
    member = interaction.user
    with GuildStore(interaction.guild_id) as store:
        queue = store["queues"].setdefault(gamemode, [])
        if member.id in queue:
            queue.remove(member.id)
            left = True
        else:
            left = False

    if left:
        await interaction.response.send_message(f"Removed you from the **{gamemode}** queue.", ephemeral=True)
    else:
        await interaction.response.send_message(f"You're not in the **{gamemode}** queue.", ephemeral=True)


class QueueJoinButton(discord.ui.DynamicItem[discord.ui.Button], template=r"otakutiers:qjoin:(?P<gamemode>.+)"):
    def __init__(self, gamemode: str):
        super().__init__(
            discord.ui.Button(label="Join Queue", style=discord.ButtonStyle.green, custom_id=f"otakutiers:qjoin:{gamemode}")
        )
        self.gamemode = gamemode

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match, /):
        return cls(match["gamemode"])

    async def callback(self, interaction: discord.Interaction):
        await try_join_queue(interaction, self.gamemode)


class QueueLeaveButton(discord.ui.DynamicItem[discord.ui.Button], template=r"otakutiers:qleave:(?P<gamemode>.+)"):
    def __init__(self, gamemode: str):
        super().__init__(
            discord.ui.Button(label="Leave Queue", style=discord.ButtonStyle.red, custom_id=f"otakutiers:qleave:{gamemode}")
        )
        self.gamemode = gamemode

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match, /):
        return cls(match["gamemode"])

    async def callback(self, interaction: discord.Interaction):
        await try_leave_queue(interaction, self.gamemode)


def build_board_view(gamemode: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(QueueJoinButton(gamemode))
    view.add_item(QueueLeaveButton(gamemode))
    return view


class QueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.board_tasks: dict[tuple[int, str], tasks.Loop] = {}

    async def cog_load(self):
        # Register the button types once so clicks route correctly even on
        # messages posted before a restart — the gamemode lives in the
        # custom_id, not in any in-memory view instance.
        self.bot.add_dynamic_items(QueueJoinButton, QueueLeaveButton)

        # If the bot restarted while a queue was open, its board stopped
        # refreshing (the task lives in memory, not in the JSON file) —
        # resume those here so nothing needs to be manually reopened.
        from storage import list_guild_ids
        for guild_id in list_guild_ids():
            data = load(guild_id)
            for gamemode, is_open in data.get("queue_open", {}).items():
                if is_open and gamemode in data.get("queue_boards", {}):
                    self._start_board_task(guild_id, gamemode)

    def cog_unload(self):
        for task in self.board_tasks.values():
            task.stop()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, NotTierTester):
            await interaction.response.send_message("You need the TierTester role to do that.", ephemeral=True)
        else:
            raise error

    # ---------- board refresh loop ----------

    def _start_board_task(self, guild_id: int, gamemode: str):
        key = (guild_id, gamemode)
        existing = self.board_tasks.get(key)
        if existing and existing.is_running():
            return

        @tasks.loop(seconds=REFRESH_SECONDS)
        async def refresher():
            data = load(guild_id)
            if not data["queue_open"].get(gamemode, False):
                refresher.stop()
                return
            board = data.get("queue_boards", {}).get(gamemode)
            if not board:
                refresher.stop()
                return
            channel = self.bot.get_channel(board["channel_id"])
            if not channel:
                return
            try:
                msg = await channel.fetch_message(board["message_id"])
            except (discord.NotFound, discord.Forbidden):
                refresher.stop()
                return
            try:
                # No view= passed here on purpose — Discord/discord.py leaves
                # existing components (the Join/Leave buttons) untouched
                # unless a view is explicitly supplied.
                await msg.edit(embed=build_board_embed(data, gamemode))
            except discord.HTTPException:
                pass

        self.board_tasks[key] = refresher
        refresher.start()

    def _stop_board_task(self, guild_id: int, gamemode: str):
        key = (guild_id, gamemode)
        task = self.board_tasks.pop(key, None)
        if task and task.is_running():
            task.stop()

    # ---------- /openqueue ----------

    @app_commands.command(name="openqueue", description="Open the testing queue for a gamemode.")
    @app_commands.autocomplete(gamemode=gamemode_choices)
    @require_tiertester()
    async def openqueue(self, interaction: discord.Interaction, gamemode: str):
        guild_id = interaction.guild_id

        with GuildStore(guild_id) as data:
            if gamemode not in data["gamemodes"]:
                await interaction.response.send_message(f"Unknown gamemode `{gamemode}`.", ephemeral=True)
                return
            data["queue_open"][gamemode] = True

        data = load(guild_id)
        embed = build_board_embed(data, gamemode)
        msg = await interaction.channel.send(content="@here", embed=embed, view=build_board_view(gamemode))

        with GuildStore(guild_id) as store:
            store["queue_boards"][gamemode] = {
                "channel_id": interaction.channel_id, "message_id": msg.id
            }

        self._start_board_task(guild_id, gamemode)
        await interaction.response.send_message(f"Queue for **{gamemode}** is now open.", ephemeral=True)

    # ---------- /closequeue ----------

    @app_commands.command(name="closequeue", description="Close the testing queue for a gamemode.")
    @app_commands.autocomplete(gamemode=gamemode_choices)
    @require_tiertester()
    async def closequeue(self, interaction: discord.Interaction, gamemode: str):
        guild_id = interaction.guild_id

        with GuildStore(guild_id) as data:
            if gamemode not in data["gamemodes"]:
                await interaction.response.send_message(f"Unknown gamemode `{gamemode}`.", ephemeral=True)
                return
            data["queue_open"][gamemode] = False
            board = data.get("queue_boards", {}).get(gamemode)

        self._stop_board_task(guild_id, gamemode)

        if board:
            channel = interaction.guild.get_channel(board["channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(board["message_id"])
                    closed_embed = discord.Embed(
                        title="Queue Closed",
                        description=f"The **{gamemode}** queue is now closed.",
                        color=discord.Color.red(),
                    )
                    await msg.edit(embed=closed_embed, view=None)  # explicitly drop the buttons
                except (discord.NotFound, discord.Forbidden):
                    pass

        await interaction.response.send_message(f"Queue for **{gamemode}** is now **closed**.", ephemeral=True)

    # ---------- /pull ----------

    @app_commands.command(name="pull", description="Pull the next player from a gamemode's queue into a ticket.")
    @app_commands.autocomplete(gamemode=gamemode_choices)
    @require_tiertester()
    async def pull(self, interaction: discord.Interaction, gamemode: str):
        guild_id = interaction.guild_id
        guild = interaction.guild

        with GuildStore(guild_id) as data:
            if gamemode not in data["gamemodes"]:
                await interaction.response.send_message(f"Unknown gamemode `{gamemode}`.", ephemeral=True)
                return
            queue = data["queues"].setdefault(gamemode, [])
            if not queue:
                await interaction.response.send_message(f"The **{gamemode}** queue is empty.", ephemeral=True)
                return
            player_id = queue.pop(0)
            data.setdefault("active_testers", {}).setdefault(gamemode, {})[str(interaction.user.id)] = player_id
            player_info = data["players"].get(str(player_id), {})

        member = guild.get_member(player_id)
        if not member:
            await interaction.response.send_message("That player is no longer in this server.", ephemeral=True)
            return

        channel, tiertester_role = await create_ticket_channel(guild, load(guild_id), member, name_prefix=f"{gamemode}")

        with GuildStore(guild_id) as store:
            store["tickets"][str(channel.id)] = {
                "user_id": player_id, "gamemode": gamemode, "status": "open"
            }

        embed = player_info_embed(f"{gamemode} Evaluation Ticket", player_info)
        await channel.send(content=f"{member.mention} {interaction.user.mention}", embed=embed)
        await channel.send(
            f"{interaction.user.mention}, once done run `/close ranking:<rank>` in this "
            f"channel to finish up and post the result."
        )

        await interaction.response.send_message(f"Pulled {member.mention} into {channel.mention}.", ephemeral=True)

    # ---------- /skip ----------

    @app_commands.command(name="skip", description="Skip the next player in queue — moves them to the back instead of pulling them.")
    @app_commands.autocomplete(gamemode=gamemode_choices)
    @require_tiertester()
    async def skip(self, interaction: discord.Interaction, gamemode: str):
        guild_id = interaction.guild_id

        with GuildStore(guild_id) as data:
            if gamemode not in data["gamemodes"]:
                await interaction.response.send_message(f"Unknown gamemode `{gamemode}`.", ephemeral=True)
                return
            queue = data["queues"].setdefault(gamemode, [])
            if not queue:
                await interaction.response.send_message(f"The **{gamemode}** queue is empty.", ephemeral=True)
                return
            skipped_id = queue.pop(0)
            queue.append(skipped_id)
            new_next = queue[0] if queue else None

        member = interaction.guild.get_member(skipped_id)
        mention = member.mention if member else f"<@{skipped_id}>"
        next_line = ""
        if new_next is not None:
            next_member = interaction.guild.get_member(new_next)
            next_mention = next_member.mention if next_member else f"<@{new_next}>"
            next_line = f" Next up: {next_mention}."

        await interaction.response.send_message(
            f"Skipped {mention} — moved to the back of the **{gamemode}** queue.{next_line}"
        )

    # ---------- /leave ----------

    @app_commands.command(name="leave", description="Remove yourself from the waitlist or a queue.")
    async def leave(self, interaction: discord.Interaction):
        member = interaction.user
        removed_from = []

        with GuildStore(interaction.guild_id) as data:
            for gamemode, queue in data["queues"].items():
                if member.id in queue:
                    queue.remove(member.id)
                    removed_from.append(gamemode)

        if removed_from:
            await interaction.response.send_message(
                f"Removed you from the queue for: {', '.join(removed_from)}.", ephemeral=True
            )
        else:
            await interaction.response.send_message("You're not in any queue.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))
