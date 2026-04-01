"""
STV Fishing Extravaganza Bot — tracks the weekly fishing tournament.

Runs every Sunday 2:00 PM – 4:00 PM US Eastern time.

Commands: /setupstv  (admins configure alert channel + role)
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
    get_stv_state, rank_prefix, send_pings,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN_FISHING")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN_FISHING is not set in .env")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "stv-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"


class STVBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree            = app_commands.CommandTree(self)
        self.last_avatar_key: str | None = None
        self.was_active:     bool | None = None
        self.last_nicks:     dict[int, str] = {}

    async def setup_hook(self):
        await self.tree.sync()
        update_loop.start()

    async def on_ready(self):
        print(f"[STV] Online as {self.user}  ({self.user.id})")
        print(f"[STV] Invite: https://discord.com/api/oauth2/authorize"
              f"?client_id={self.user.id}&permissions=2214661120&scope=bot%20applications.commands")


bot = STVBot()


@bot.tree.command(name="setupstv", description="Configure STV Fishing alert channel and role")
@app_commands.default_permissions(administrator=True)
async def cmd_setup_stv(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    save_guild_config(CONFIG_PATH, interaction.guild_id, channel.id, role.id)
    await interaction.response.send_message(
        f"✅ STV alerts set up! Will ping <@&{role.id}> in <#{channel.id}> when the tournament starts.",
        ephemeral=True,
    )
    print(f"[STV] /setupstv configured for '{interaction.guild.name}'")


@bot.tree.command(name="teststv", description="Ping the saved role in the saved channel")
@app_commands.default_permissions(administrator=True)
async def teststv(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await send_pings(bot, CONFIG_PATH, lambda rid:
        f"<@&{rid}> 🎣 **STV Fishing Extravaganza** has started! "
        "Head to Stranglethorn Vale — you have 2 hours!"
    )
    await interaction.followup.send("✅ Test ping sent.", ephemeral=True)


@tasks.loop(minutes=1)
async def update_loop():
    await do_update()


@update_loop.before_loop
async def before_loop():
    await bot.wait_until_ready()


async def do_update():
    now   = datetime.now(timezone.utc)
    state = get_stv_state(now)
    key   = "active" if state["active"] else "inactive"

    if bot.last_avatar_key != key:
        stem = "fishing_active" if state["active"] else "fishing_inactive"
        img  = find_image(str(IMAGES_DIR / stem)) or find_image(str(IMAGES_DIR / "fishing"))
        if img:
            try:
                with open(img, "rb") as f:
                    await bot.user.edit(avatar=f.read())
                print(f"[STV] Avatar → {img}")
            except discord.HTTPException as e:
                print(f"[WARN] Avatar update failed: {e}")
        else:
            print("[INFO] Place images/fishing.png (or fishing_active.png / fishing_inactive.png)")
        bot.last_avatar_key = key

    # Role ping when tournament starts
    if bot.was_active is False and state["active"]:
        await send_pings(bot, CONFIG_PATH, lambda rid:
            f"<@&{rid}> 🎣 **STV Fishing Extravaganza** has started! "
            "Head to Stranglethorn Vale — you have 2 hours!"
        )
    bot.was_active = state["active"]

    status = (
        f"Active! | Ends in {format_countdown(state['msUntilEnd'])}"
        if state["active"]
        else f"Starts in {format_countdown(state['msUntilStart'])}"
    )
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=status)
    )
    print(f"[STV] Status: {status}")

    symbol = rank_prefix("stv", now)
    nick   = f"{symbol} STV Fishing"
    for guild in bot.guilds:
        if bot.last_nicks.get(guild.id) == nick:
            continue
        try:
            await guild.me.edit(nick=nick)
            bot.last_nicks[guild.id] = nick
            print(f"[STV] Nick in '{guild.name}': {nick}")
        except Exception as e:
            print(f"[WARN] Nickname failed in '{guild.name}': {e}")


bot.run(TOKEN)
