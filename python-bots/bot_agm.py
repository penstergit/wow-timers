"""
Arena Grand Master Bot — tracks the Gurubashi Arena chest spawns.

Chest spawns every 3 hours starting midnight US Mountain.
Active window: ~5 minutes per spawn.

Commands: /setupagm, /testagm
"""
import os
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from shared import (
    format_countdown, find_image, save_guild_config,
    get_agm_state, rank_prefix, send_pings, send_broadcast, send_dms,
    set_dm_enabled, setup_logging,
    require_dev_role, install_dev_error_handler,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN_ARENA")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN_ARENA is not set in .env")

setup_logging("agm")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "agm-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"

MSG_WARN10 = "⚔️ **Arena Grand Master** chest spawns in 10 minutes!"
MSG_SPAWN  = "⚔️ **Arena Grand Master** chest has spawned! Grab it fast — you have 5 minutes!"


class AGMBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True   # needed to enumerate role.members for DM alerts
        super().__init__(intents=intents)
        self.tree        = app_commands.CommandTree(self)
        self.avatar_set  = False
        self.was_up:    bool | None = None
        self.warned_next: bool = False
        self.last_nicks: dict[int, str] = {}

    async def setup_hook(self):
        await self.tree.sync()
        update_loop.start()

    async def on_ready(self):
        print(f"[AGM] Online as {self.user}  ({self.user.id})")
        print(f"[AGM] Invite: https://discord.com/api/oauth2/authorize"
              f"?client_id={self.user.id}&permissions=2214661120&scope=bot%20applications.commands")


bot = AGMBot()
install_dev_error_handler(bot.tree)


@bot.tree.command(name="setupagm", description="Configure Arena Grand Master chest alert channel and role")
@require_dev_role()
async def cmd_setup_agm(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    save_guild_config(CONFIG_PATH, interaction.guild_id, channel.id, role.id)
    await interaction.response.send_message(
        f"✅ AGM alerts set up! Will ping <@&{role.id}> in <#{channel.id}> when the chest spawns.",
        ephemeral=True,
    )
    print(f"[AGM] /setupagm configured for '{interaction.guild.name}'")


@tasks.loop(minutes=1)
async def update_loop():
    await do_update()


@update_loop.before_loop
async def before_loop():
    await bot.wait_until_ready()


async def do_update():
    now   = datetime.now(timezone.utc)
    state = get_agm_state(now)

    if not bot.avatar_set:
        img = find_image(str(IMAGES_DIR / "arena"))
        if img:
            try:
                with open(img, "rb") as f:
                    await bot.user.edit(avatar=f.read())
                bot.avatar_set = True
                print(f"[AGM] Avatar set from {img}")
            except discord.HTTPException as e:
                print(f"[WARN] Avatar update failed: {e}")

    # 10-minute warning — the ONLY ping AGM sends. Also DMs role holders here only
    # (heads-up only, ~8/day). The spawn message stays silent + DM-free to avoid a
    # second notification; a spawn DM can be wired in later if mcg wants it.
    if not state["isUp"] and not bot.warned_next and state["msUntilNext"] <= 10 * 60 * 1000:
        await send_pings(bot, CONFIG_PATH, lambda: MSG_WARN10)
        await send_dms(bot, CONFIG_PATH, lambda: MSG_WARN10)
        bot.warned_next = True

    # Chest just spawned: post the pickup notice (NO ping) and reset the latch.
    # The role is only pinged by the 10-min warning above — this keeps the
    # informational "grab it fast" message while avoiding a second ping.
    if bot.was_up is False and state["isUp"]:
        await send_broadcast(bot, CONFIG_PATH, lambda: MSG_SPAWN)
        bot.warned_next = False
    bot.was_up = state["isUp"]

    status = "Chest is up!" if state["isUp"] else f"Next chest in {format_countdown(state['msUntilNext'])}"
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=status)
    )
    print(f"[AGM] Status: {status}")

    symbol = rank_prefix("agm", now)
    nick   = f"{symbol} AGM Chest"
    for guild in bot.guilds:
        if bot.last_nicks.get(guild.id) == nick:
            continue
        try:
            await guild.me.edit(nick=nick)
            bot.last_nicks[guild.id] = nick
            print(f"[AGM] Nick in '{guild.name}': {nick}")
        except Exception as e:
            print(f"[WARN] Nickname failed in '{guild.name}': {e}")

# 📢 Slash command to PING saved role
@bot.tree.command(name="testagm", description="Ping the saved role in the saved channel")
@require_dev_role()
@app_commands.describe(warning="Send the 10-minute advance warning instead of the spawn message")
async def testagm(interaction: discord.Interaction, warning: bool = False):
    await interaction.response.defer(ephemeral=True)
    if warning:
        # advance warning — pings the role + DMs role holders (matches production)
        await send_pings(bot, CONFIG_PATH, lambda: MSG_WARN10)
        await send_dms(bot, CONFIG_PATH, lambda: MSG_WARN10)
        label = "10-min warning"
    else:
        # spawn message — no ping, no DM (matches production)
        await send_broadcast(bot, CONFIG_PATH, lambda: MSG_SPAWN)
        label = "spawn message"
    await interaction.followup.send(f"✅ Test {label} sent.", ephemeral=True)


@bot.tree.command(name="agmdms", description="Toggle DM alerts to role holders on/off for this server")
@require_dev_role()
@app_commands.describe(enabled="True to DM role holders on the AGM 10-min warning, False to disable")
async def agmdms(interaction: discord.Interaction, enabled: bool):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    if not set_dm_enabled(CONFIG_PATH, interaction.guild_id, enabled):
        await interaction.response.send_message(
            "No config yet — run /setupagm first.", ephemeral=True)
        return
    state = "ON" if enabled else "OFF"
    await interaction.response.send_message(f"✅ AGM DM alerts now **{state}**.", ephemeral=True)
    print(f"[AGM] DM alerts {state} for '{interaction.guild.name}'")

bot.run(TOKEN)
