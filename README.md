# OtakuTiers Bot

MCTiers-style tier testing bot. Panel with **Verify Account** / **Enter
Waitlist**, a live-updating queue board per gamemode, `/pull` opening a
private evaluation ticket, `/close` finishing it off, and `/result` for
manual posting or public lookups.

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Create the bot in the Discord Developer Portal

1. https://discord.com/developers/applications → New Application.
2. Bot tab → Add Bot → copy the token.
3. Bot tab → enable **Server Members Intent** (required — the bot uses it to
   verify players and manage roles).
4. OAuth2 → URL Generator → scopes `bot` + `applications.commands` → permissions:
   Manage Roles, Manage Channels, Send Messages, Embed Links, Read Message
   History, Manage Messages. Use the generated URL to invite the bot.

## 3. Run it

```bash
export DISCORD_TOKEN=your_token_here
python bot.py
```

Data is stored per-server in `data/<guild_id>.json` — no external database.

## 4. First-time server setup

Admin isn't a role you configure — it's simply the real Discord **server
owner**, or anyone with real Discord **Administrator** permission. Nothing
to set up, nothing that can lock a server out. Run these as that person:

```
/roles set type:staff       role:@Staff
/roles set type:tiertester  role:@TierTester
/roles set type:lt3         role:@LT3
/roles set type:verified    role:@Verified

/roles set type:tier_LT5 role:@LT5   (repeat for HT5, LT4, HT4, LT3, HT3, LT2, HT2, LT1, HT1)

/setchannel type:panel            channel:#verify
/setchannel type:waitlist         channel:#waitlist
/setchannel type:results          channel:#results
/setchannel type:ticket_category  channel:<a category>

/panel                        (posts the Verify Account / Enter Waitlist buttons)
/openqueue gamemode:NethPot   (repeat per gamemode you want open)
```

> **LT3 is used two different ways:** `type:lt3` is the *waitlist* role —
> whoever holds it gets a ticket instead of the queue. `type:tier_LT3` is the
> *cosmetic* rank role given after an LT3 evaluation. They can point at the
> same Discord role or two different ones.

### How admin access actually works

One rule, enforced by the bot itself on every admin command:

- Real server **owner** → always passes, unconditionally, forever.
- Real Discord **Administrator** permission (granted via any role in
  Server Settings → Roles) → also always passes.
- Everyone else → blocked from admin commands, full stop. There's no
  bot-side admin role to configure, no bootstrap step, and no way for that
  to ever get stuck or hijacked.

Want to add more people as "admins" without giving them the real Discord
Administrator permission directly? Use `/roles set type:staff` instead —
Staff gets full TierTester-level access (pull, close, queue management)
without touching server config, roles, or channels. Only the actual
Administrator permission unlocks `/setchannel` and `/roles`.

If you want to *additionally* hide these commands from the slash-command
menu for non-admins (a cosmetic nicety, not required for security — the
check above is the real gate), you can set that up per-server via
**Server Settings → Integrations → [your bot] → Command Permissions** — a
native Discord feature, no bot code involved.

## Commands

| Command | Who | What |
|---|---|---|
| `/panel` | Admin | Posts the Verify Account / Enter Waitlist panel |
| `/setchannel type: channel:` | Admin | Sets panel / waitlist / results / log / ticket_category channels |
| `/roles set type: role:` | Admin | Sets admin / staff / tiertester / lt3 / verified / tier_XXn roles |
| `/roles view` | Admin | Shows current role config |
| `/addtester` / `/removetester` | Admin | Grants / revokes the TierTester role |
| `/setcooldown days:` | Admin | Cooldown before a tested player can rejoin the waitlist |
| `/openqueue gamemode:` | TierTester+ | Posts the live queue board and opens the queue |
| `/closequeue gamemode:` | TierTester+ | Closes the queue, stops the board refresh |
| `/skip gamemode:` | TierTester+ | Moves the next queued player to the back instead of pulling them |
| `/pull gamemode:` | TierTester+ | Pulls the next queued player into a private ticket |
| `/close ranking:` | TierTester+ | Run inside a ticket — posts the result, locks the ticket |
| `/leave` | Everyone | Removes you from any queue you're in |
| `/result player:` | Everyone | Looks up that player's current rank |
| `/result player: rank_earned: [...]` | TierTester+ | Posts a result manually, without a ticket |

**Admin** (server owner, or real Discord Administrator permission — not a
configurable bot role) always has everything TierTester can do, plus config
access. **Staff** has the same access as TierTester.

## The queue board

`/openqueue gamemode:NethPot` posts a red embed in the channel you run it in,
pings `@here`, and attaches **Join Queue** / **Leave Queue** buttons:

> **Tester(s) Available!**
> 🔄 The queue updates every 10 seconds.
> Use the buttons below (or `/leave`) if you wish to be removed from the queue.
>
> **Queue (3/20):**
> 1. @player1
> 2. @player2
> 3. @player3
>
> **Active Testers:**
> 1. @tester1
>
> [ Join Queue ]  [ Leave Queue ]

That same message **edits itself every 10 seconds** for as long as the queue
stays open, showing the live queue (capped at 20) and which testers
currently have someone pulled. The buttons work exactly like `/leave` or the
panel's Enter Waitlist flow — same verification check, cooldown check, and
LT3-gets-a-ticket-instead behavior — but scoped to this specific gamemode,
no picker needed. They keep working even if the bot restarts, since the
gamemode is encoded directly in the button rather than tracked in memory.

`/closequeue` stops the refresh, edits the board to say it's closed, and
removes the buttons.

`/skip gamemode:` lets a tester pass on the next person in line without
pulling them — moves them to the back of the queue instead of removing them,
so the next player up gets pulled instead.

## The ticket flow (`/pull` → `/close`)

1. A tester runs `/pull gamemode:NethPot`. The next person in queue gets a
   private ticket channel (`#nethpot-username`), visible to them, the
   TierTester role, and the bot. It's posted with their exact **Username**,
   **Region**, and **Preferred Server** from Verify Account, and marks that
   tester as "active" on the board.
2. Testing happens in the ticket.
3. The tester runs `/close ranking:"Low Tier 5"` **inside that ticket**.
   Region, Username, and Previous Rank are all pulled automatically from the
   player's stored data — the tester only picks the rank. This:
   - posts the result embed to the results channel (ping above it, skin
     render, Tester/Region/Username/Previous Rank/Rank Earned fields)
   - swaps their tier role
   - revokes waitlist access and starts their cooldown
   - renames the ticket to `closed-...` and hides it from the player
   - clears them from the "Active Testers" list on the board

LT3 players get the same kind of ticket immediately on clicking **Enter
Waitlist** (skipping the queue entirely) — `/close` works the same way
inside those too.

`/result` still exists separately for posting a result with no ticket
involved (`rank_earned:` set) or for anyone to look a player up
(`rank_earned:` left blank).

## Cooldown

Every time a result is posted (`/close` or `/result` in record mode), the
player's waitlist-channel access is revoked and a cooldown timer starts —
`/setcooldown days:` (default 3). Clicking **Enter Waitlist** again before
it's up shows how much time is left.

## How the panel behaves

Posted with `/panel`:

> **📝 Evaluation Testing Waitlist**
> Upon applying, you will be added to a waitlist channel.
> Here you will be pinged when a tester of your region is available.
> If you are LT3 or higher, a priority ticket will be created.
>
> • Region should be the region of the server you wish to test on
>
> • Username should be the name of the account you will be testing on
>
> 🛑 **Failure to provide authentic information will result in a denied test.**

- **Verify Account** → modal (IGN / region / preferred server) → saves it,
  grants the Verified role, opens up the waitlist channel.
- **Enter Waitlist** → must be verified first, and not on cooldown.
  - LT3 role → private ticket immediately.
  - Otherwise → gamemode picker → joins that queue if it's open.

> One thing this can't replicate: the "Done reading? Check out #general" bar
> at the bottom of Discord mobile screenshots is a native Discord
> channel-onboarding prompt, not a bot message — configured under Server
> Settings → Onboarding, not through this bot.

## Files

```
bot.py            entry point, loads all cogs, syncs slash commands
storage.py         JSON-file storage (data/<guild_id>.json)
checks.py          admin / staff / tiertester / lt3 permission helpers
constants.py        TIERS (low->high) and human-readable tier labels
tickets.py           shared ticket-channel creation, used by panel.py + queue.py
util.py             cooldown math, duration formatting
cogs/panel.py       Verify Account + Enter Waitlist buttons, LT3 ticket creation
cogs/admin.py       /setchannel, /roles, /addtester, /removetester, /setcooldown
cogs/queue.py       /openqueue (live board + buttons), /closequeue, /pull, /skip, /leave
cogs/tester.py      /result, /close
cogs/debug.py        /whoami diagnostic — currently loaded by default since
                     you're mid-testing; safe to remove from bot.py's COGS
                     list (or delete the file) once everything's confirmed working
```

## Testing tip: instant command sync

Set a `TEST_GUILD_ID` environment variable to your server's Discord ID and
commands sync to that one server **instantly** instead of Discord's normal
"up to an hour" delay for global commands. Remove the variable once you're
done testing and want the bot's commands available in every server it's in.

## Running it 24/7 for free

A Discord bot has to be a long-running process — something has to keep
`python bot.py` alive around the clock. There's no way around needing *some*
always-on machine; the honest free options are:

### Option A — Oracle Cloud "Always Free" VM (best option, actually free forever)

Oracle gives a genuinely free-forever small VM (not a trial), which is
enough for a bot like this.

1. Sign up at oracle.com/cloud/free, create an **Always Free** Compute
   instance (Ampere A1 or the free x86 shape — either works fine here),
   Ubuntu image.
2. SSH in, then:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv
   git clone <your repo, or just scp the otakutiers-bot folder up>
   cd otakutiers-bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   export DISCORD_TOKEN=your_token_here
   ```
3. Keep it running permanently with `systemd` (survives reboots and crashes):
   ```bash
   sudo tee /etc/systemd/system/otakutiers.service << 'EOF'
   [Unit]
   Description=OtakuTiers Discord Bot
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/home/ubuntu/otakutiers-bot
   Environment=DISCORD_TOKEN=your_token_here
   ExecStart=/home/ubuntu/otakutiers-bot/venv/bin/python bot.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   EOF

   sudo systemctl daemon-reload
   sudo systemctl enable --now otakutiers
   sudo systemctl status otakutiers   # confirm it's running
   journalctl -u otakutiers -f        # live logs
   ```
   That's it — it survives reboots, restarts itself if it crashes, and
   costs $0 indefinitely (no trial period to run out).

### Option B — Railway / Render free tier

Both let you deploy straight from a GitHub repo with a `Procfile`
(`worker: python bot.py`) or a `Dockerfile`. Free tiers are usage-capped
(Railway gives limited monthly hours, Render's free web services spin down
when idle — use their **background worker** type, not "web service", since
this bot doesn't serve HTTP). Good for testing; Oracle's free VM is more
reliable for a server that needs to be up constantly.

### Option C — A spare always-on computer / Raspberry Pi

Same systemd approach as Option A works identically on any Linux machine
you already have running 24/7.

### What to avoid

- **Replit free tier** — bots get killed when the tab/browser isn't active;
  the old "ping it with UptimeRobot" trick no longer reliably works for
  always-on background processes and can get your bot rate-limited.
- Running it just from your own laptop — works, but only while the laptop
  is on and connected.

Whichever you pick, the bot itself doesn't need to change — `DISCORD_TOKEN`
env var + `python bot.py`, same as local testing.
