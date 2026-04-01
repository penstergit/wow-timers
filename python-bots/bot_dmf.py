"""
Darkmoon Faire Bot — tracks the monthly Darkmoon Faire.

Active during the first full week of each month (Eastern time).
Starts Monday 00:01 ET, ends 7 days later.

Commands: /setupdmf  (admins configure alert channel + role)
"""
import os
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from shared import (
    format_countdown, find_image, load_config, save_guild_config,
    get_dmf_state, rank_prefix,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN_DMF")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN_DMF is not set in .env")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "dmf-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"


class DMFBot(discord.Client):
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
        print(f"[DMF] Online as {self.user}  ({self.user.id})")
        print(f"[DMF] Invite: https://discord.com/api/oauth2/authorize"
              f"?client_id={self.user.id}&permissions=2214661120&scope=bot%20applications.commands")


bot = DMFBot()


@bot.tree.command(name="setupdmf", description="Configure Darkmoon Faire alert channel and role")
@app_commands.default_permissions(administrator=True)
async def cmd_setup_dmf(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    save_guild_config(CONFIG_PATH, interaction.guild_id, channel.id, role.id)
    await interaction.response.send_message(
        f"✅ DMF alerts set up! Will ping <@&{role.id}> in <#{channel.id}> when the faire opens.",
        ephemeral=True,
    )
    print(f"[DMF] /setupdmf configured for '{interaction.guild.name}'")


@tasks.loop(minutes=1)
async def update_loop():
    await do_update()


@update_loop.before_loop
async def before_loop():
    await bot.wait_until_ready()


async def do_update():
    now   = datetime.now(timezone.utc)
    state = get_dmf_state(now)
    key   = "active" if state["active"] else "inactive"

    # Swap avatar between active/inactive variants
    if bot.last_avatar_key != key:
        stem  = "dmf_active" if state["active"] else "dmf_inactive"
        img   = find_image(str(IMAGES_DIR / stem)) or find_image(str(IMAGES_DIR / "dmf"))
        if img:
            try:
                with open(img, "rb") as f:
                    await bot.user.edit(avatar=f.read())
                print(f"[DMF] Avatar → {img}")
            except discord.HTTPException as e:
                print(f"[WARN] Avatar update failed: {e}")
        else:
            print("[INFO] Place images/dmf.png (or dmf_active.png / dmf_inactive.png)")
        bot.last_avatar_key = key

    # Role ping when faire opens
    if bot.was_active is False and state["active"]:
        config = load_config(CONFIG_PATH)
        for gid, cfg in config.items():
            try:
                guild = bot.get_guild(int(gid))
                if guild:
                    ch = guild.get_channel(int(cfg["channelId"]))
                    if ch:
                        await ch.send(
                            f"<@&{cfg['roleId']}> 🎪 **Darkmoon Faire** is now open! "
                            "Head to Elwynn Forest or Mulgore."
                        )
            except Exception as e:
                print(f"[WARN] Ping failed for guild {gid}: {e}")
    bot.was_active = state["active"]

    status = (
        f"Active! | Ends in {format_countdown(state['msUntilEnd'])}"
        if state["active"]
        else f"Starts in {format_countdown(state['msUntilStart'])}"
    )
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=status)
    )
    print(f"[DMF] Status: {status}")

    symbol = rank_prefix("dmf", now)
    nick   = f"{symbol} DMF Active" if state["active"] else f"{symbol} DMF Offline"
    for guild in bot.guilds:
        if bot.last_nicks.get(guild.id) == nick:
            continue
        try:
            await guild.me.edit(nick=nick)
            bot.last_nicks[guild.id] = nick
            print(f"[DMF] Nick in '{guild.name}': {nick}")
        except Exception as e:
            print(f"[WARN] Nickname failed in '{guild.name}': {e}")


bot.run(TOKEN)
