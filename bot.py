"""
bot.py
OtakuTiers Discord bot — MCTiers-style tier testing bot.

Setup:
1. pip install -r requirements.txt
2. Set the DISCORD_TOKEN environment variable (or edit TOKEN below).
3. python bot.py

Testing tip: set a TEST_GUILD_ID environment variable to your server's ID
and commands sync to that server INSTANTLY instead of taking up to an hour
(Discord's normal delay for global command updates). Remove it once you're
done testing and want commands available in every server the bot is in.

First-time server setup (run as the server owner, or anyone with real
Discord Administrator permission — that's all "Admin" means here, nothing
to configure):
    /roles set type:tiertester role:@TierTester
    /roles set type:lt3 role:@LT3
    /roles set type:verified role:@Verified        (optional but recommended)
    /roles set type:tier_HT1 role:@HT1             (repeat for each tier — see README)
    /setchannel type:panel channel:#verify
    /setchannel type:waitlist channel:#waitlist
    /setchannel type:results channel:#results
    /setchannel type:ticket_category channel:<a category>
    /panel                                          (posts the Verify/Waitlist buttons)
    /openqueue gamemode:NethPot                     (per gamemode, as needed)
"""

import os
import logging

import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("DISCORD_TOKEN", "PUT_YOUR_TOKEN_HERE")
TEST_GUILD_ID = os.environ.get("TEST_GUILD_ID")  # optional, for instant command sync while testing

INTENTS = discord.Intents.default()
INTENTS.members = True  # needed to resolve members for verification / roles

COGS = [
    "cogs.panel",
    "cogs.admin",
    "cogs.queue",
    "cogs.tester",
    "cogs.debug",  # temporary — /whoami diagnostic, remove this line once the issue's confirmed fixed
]


class OtakuTiersBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!otaku ", intents=INTENTS, help_command=None)

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logging.info(f"Loaded {cog}")
            except Exception:
                # A single broken cog (e.g. a typo in a new file) must NOT
                # take every other command down with it — log it clearly and
                # keep going so the rest of the bot still syncs and works.
                logging.exception(f"FAILED to load {cog} — its commands will be missing until this is fixed")

        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logging.info(f"Synced {len(synced)} slash commands instantly to guild {TEST_GUILD_ID}.")
        else:
            synced = await self.tree.sync()
            logging.info(f"Synced {len(synced)} slash commands globally (can take up to an hour to appear).")

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (id={self.user.id})")


bot = OtakuTiersBot()


if __name__ == "__main__":
    if TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise SystemExit(
            "Set the DISCORD_TOKEN environment variable (or edit TOKEN in bot.py) before running."
        )
    bot.run(TOKEN)
