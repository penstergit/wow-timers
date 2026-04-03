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
    get_agm_state, rank_prefix, send_pings, setup_logging,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN_ARENA")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN_ARENA is not set in .env")

setup_logging("agm")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "agm-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"


class AGMBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
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


@bot.tree.command(name="setupagm", description="Configure Arena Grand Master chest alert channel and role")
@app_commands.default_permissions(administrator=True)
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

    # 20-minute warning
    if not state["isUp"] and not bot.warned_next and state["msUntilNext"] <= 20 * 60 * 1000:
        await send_pings(bot, CONFIG_PATH, lambda rid:
            f"<@&{rid}> ⚔️ **Arena Grand Master** chest spawns in 20 minutes!"
        )
        bot.warned_next = True

    # Role ping when chest just spawned
    if bot.was_up is False and state["isUp"]:
        await send_pings(bot, CONFIG_PATH, lambda rid:
            f"<@&{rid}> ⚔️ **Arena Grand Master** chest has spawned! "
            "Grab it fast — you have 5 minutes!"
        )
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
@app_commands.default_permissions(administrator=True)
async def testagm(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await send_pings(bot, CONFIG_PATH, lambda rid:
        f"<@&{rid}> ⚔️ **Arena Grand Master** chest has spawned! "
        "Grab it fast — you have 5 minutes!"
    )
    await interaction.followup.send("✅ Test ping sent.", ephemeral=True)

bot.run(TOKEN)
