"""
cogs/tester.py
/result — dual purpose:
  - Called with just `player`: public lookup of their current rank.
  - Called with `rank_earned` set: tiertester-only, posts a result manually
    (for when there's no ticket — e.g. testing outside the queue flow).
/close  — tiertester-only, run *inside* an evaluation ticket. Auto-fills
    region/username/previous rank from the ticket's player, tester just
    picks the rank earned. Posts the result, then locks the ticket.

Both share the same embed layout and side effects (tier role swap, cooldown,
waitlist-channel revocation) via apply_result().
"""

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStore, load
from checks import is_tiertester
from util import mark_tested
from constants import TIER_LABELS, UNRANKED, UNRANKED_LABEL

PREVIOUS_RANK_CHOICES = [
    app_commands.Choice(name=UNRANKED_LABEL, value=UNRANKED)
] + [
    app_commands.Choice(name=label, value=code) for code, label in TIER_LABELS.items()
]

RANK_EARNED_CHOICES = [
    app_commands.Choice(name=label, value=code) for code, label in TIER_LABELS.items()
]


async def apply_result(
    guild: discord.Guild,
    guild_id: int,
    player: discord.Member,
    tester_member: discord.Member,
    region: str,
    username: str,
    prev_code: str,
    new_code: str,
) -> discord.Embed:
    """Writes the new rank, swaps tier roles, revokes waitlist access, starts
    the cooldown, and returns the built result embed. Sends no messages."""
    prev_label = TIER_LABELS.get(prev_code, UNRANKED_LABEL)
    new_label = TIER_LABELS[new_code]

    with GuildStore(guild_id) as store:
        store["players"].setdefault(str(player.id), {"tiers": {}})
        store["players"][str(player.id)]["rank"] = new_code
        store["players"][str(player.id)]["ign"] = username
        store["players"][str(player.id)]["region"] = region
        mark_tested(store, player.id)  # starts the cooldown clock

        waitlist_channel_id = store["config"]["waitlist_channel"]
        tier_roles = dict(store["config"].get("tier_roles", {}))

    embed = discord.Embed(color=discord.Color.red())
    embed.set_author(name=f"{username}'s Test Results \U0001F3C6", icon_url=player.display_avatar.url)
    embed.add_field(name="Tester", value=tester_member.mention, inline=False)
    embed.add_field(name="Region", value=region, inline=False)
    embed.add_field(name="Username", value=username, inline=False)
    embed.add_field(name="Previous Rank", value=prev_label, inline=False)
    embed.add_field(name="Rank Earned", value=new_label, inline=False)
    embed.set_thumbnail(url=f"https://mc-heads.net/body/{username}/100")

    # revoke access to the waitlist/testing channel — cooldown has started
    if waitlist_channel_id:
        wc = guild.get_channel(waitlist_channel_id)
        if wc:
            try:
                await wc.set_permissions(player, overwrite=None)
            except discord.Forbidden:
                pass

    # auto-assign the earned tier role, removing any other tier role they hold
    if tier_roles.get(new_code):
        new_role = guild.get_role(tier_roles[new_code])
        if new_role:
            other_role_ids = {rid for code, rid in tier_roles.items() if code != new_code}
            to_remove = [r for r in player.roles if r.id in other_role_ids]
            try:
                if to_remove:
                    await player.remove_roles(*to_remove, reason="Rank updated")
                if new_role not in player.roles:
                    await player.add_roles(new_role, reason=f"Earned {new_code}")
            except discord.Forbidden:
                pass

    return embed


class TesterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /result ----------

    @app_commands.command(name="result", description="Look up a player's rank, or (tiertester) post a new result.")
    @app_commands.describe(
        player="The player being looked up or ranked",
        tester="Tester credited for this result (defaults to you)",
        region="Region tested in (defaults to their verified region)",
        username="Minecraft username tested (defaults to their verified IGN)",
        previous_rank="Their rank before this test (defaults to their current stored rank)",
        rank_earned="The rank they just earned — leave blank to just look them up",
    )
    @app_commands.choices(previous_rank=PREVIOUS_RANK_CHOICES, rank_earned=RANK_EARNED_CHOICES)
    async def result(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
        tester: discord.Member = None,
        region: str = None,
        username: str = None,
        previous_rank: app_commands.Choice[str] = None,
        rank_earned: app_commands.Choice[str] = None,
    ):
        guild_id = interaction.guild_id
        data = load(guild_id)
        info = data["players"].get(str(player.id), {})

        # ---------- lookup mode (public) ----------
        if rank_earned is None:
            stored_rank = info.get("rank")
            label = TIER_LABELS.get(stored_rank, UNRANKED_LABEL)
            display_name = info.get("ign", player.display_name)

            embed = discord.Embed(title=f"{display_name}'s Rank", color=discord.Color.gold())
            embed.add_field(name="Rank", value=label)
            embed.set_thumbnail(url=f"https://mc-heads.net/body/{display_name}/100")
            await interaction.response.send_message(embed=embed)
            return

        # ---------- recording mode (tiertester only) ----------
        if not isinstance(interaction.user, discord.Member) or not is_tiertester(interaction.user):
            await interaction.response.send_message("You need the TierTester role to do that.", ephemeral=True)
            return

        tester_member = tester or interaction.user
        final_region = region or info.get("region", "NA")
        final_username = username or info.get("ign", player.display_name)
        prev_code = previous_rank.value if previous_rank else info.get("rank", UNRANKED)
        new_code = rank_earned.value

        embed = await apply_result(
            interaction.guild, guild_id, player, tester_member,
            final_region, final_username, prev_code, new_code,
        )

        await interaction.response.send_message(content=player.mention, embed=embed)

        results_channel_id = load(guild_id)["config"]["results_channel"]
        if results_channel_id:
            ch = interaction.guild.get_channel(results_channel_id)
            if ch and ch.id != interaction.channel_id:
                await ch.send(content=player.mention, embed=embed)

    # ---------- /close ----------

    @app_commands.command(name="close", description="Close an evaluation ticket and post the result (tiertester only).")
    @app_commands.describe(ranking="The rank they earned")
    @app_commands.choices(ranking=RANK_EARNED_CHOICES)
    async def close(self, interaction: discord.Interaction, ranking: app_commands.Choice[str]):
        guild_id = interaction.guild_id
        guild = interaction.guild

        if not isinstance(interaction.user, discord.Member) or not is_tiertester(interaction.user):
            await interaction.response.send_message("You need the TierTester role to do that.", ephemeral=True)
            return

        data = load(guild_id)
        ticket = data["tickets"].get(str(interaction.channel_id))
        if not ticket or ticket.get("status") != "open":
            await interaction.response.send_message(
                "This isn't an open evaluation ticket — run `/close` inside one.", ephemeral=True
            )
            return

        player_id = ticket["user_id"]
        member = guild.get_member(player_id)
        if not member:
            await interaction.response.send_message("Couldn't find that player in this server anymore.", ephemeral=True)
            return

        info = data["players"].get(str(player_id), {})
        region = info.get("region", "NA")
        username = info.get("ign", member.display_name)
        prev_code = info.get("rank", UNRANKED)
        new_code = ranking.value
        gamemode = ticket.get("gamemode")

        embed = await apply_result(guild, guild_id, member, interaction.user, region, username, prev_code, new_code)

        await interaction.response.send_message("Ticket closed and result posted.", ephemeral=True)

        results_channel_id = load(guild_id)["config"]["results_channel"]
        if results_channel_id:
            ch = guild.get_channel(results_channel_id)
            if ch:
                await ch.send(content=member.mention, embed=embed)
        else:
            await interaction.channel.send(content=member.mention, embed=embed)

        with GuildStore(guild_id) as store:
            if str(interaction.channel_id) in store["tickets"]:
                store["tickets"][str(interaction.channel_id)]["status"] = "closed"
            if gamemode and str(interaction.user.id) in store.get("active_testers", {}).get(gamemode, {}):
                del store["active_testers"][gamemode][str(interaction.user.id)]

        try:
            await interaction.channel.edit(name=f"closed-{interaction.channel.name}"[:90])
            await interaction.channel.set_permissions(member, view_channel=False)
        except discord.Forbidden:
            pass

        await interaction.channel.send(
            f"Evaluation closed — {member.mention} earned **{TIER_LABELS[new_code]}**. This ticket is now locked."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TesterCog(bot))
