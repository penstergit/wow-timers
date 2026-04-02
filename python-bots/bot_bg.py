"""
BG Weekend Bot — tracks the Battleground Weekend rotation.

Rotation: AV → EOTS → WSG → AB (resets Tuesday 2am MT)
Event live: Thursday 2am MT → Tuesday 2am MT

Commands: /setupbg  (admins configure alert channel + role)
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
    get_rotation_info, rank_prefix, send_pings, setup_logging,
)

load_dotenv()
setup_logging("bg")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set in .env")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "bg-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"

BG_IMAGE_STEMS = {"AV": "av", "EOTS": "eots", "WSG": "wsg", "AB": "ab"}


# ── Bot class ──────────────────────────────────────────────────────────────

class BGBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree         = app_commands.CommandTree(self)
        self.last_bg_nick: str | None = None          # tracks last avatar swap
        self.was_active:   bool | None = None
        self.last_nicks:   dict[int, str] = {}

    async def setup_hook(self):
        await self.tree.sync()
        update_loop.start()

    async def on_ready(self):
        print(f"[BG] Online as {self.user}  ({self.user.id})")
        print(f"[BG] Invite: https://discord.com/api/oauth2/authorize"
              f"?client_id={self.user.id}&permissions=2214661120&scope=bot%20applications.commands")


bot = BGBot()


# ── Slash command ──────────────────────────────────────────────────────────

@bot.tree.command(name="setupbg", description="Configure BG Weekend alert channel and role")
@app_commands.default_permissions(administrator=True)
async def cmd_setup_bg(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    save_guild_config(CONFIG_PATH, interaction.guild_id, channel.id, role.id)
    await interaction.response.send_message(
        f"✅ BG Weekend alerts set up! Will ping <@&{role.id}> in <#{channel.id}> when the event goes live.",
        ephemeral=True,
    )
    print(f"[BG] /setupbg configured for '{interaction.guild.name}'")


@bot.tree.command(name="testbg", description="Ping the saved role in the saved channel")
@app_commands.default_permissions(administrator=True)
async def testbg(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    short = get_rotation_info()["currentBG"]["shortName"]
    await send_pings(bot, CONFIG_PATH, lambda rid: f"<@&{rid}> 🏟️ **{short} Weekend** is now live!")
    await interaction.followup.send("✅ Test ping sent.", ephemeral=True)


# ── Update loop ────────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def update_loop():
    await do_update()


@update_loop.before_loop
async def before_loop():
    await bot.wait_until_ready()


async def do_update():
    now  = datetime.now(timezone.utc)
    info = get_rotation_info(now)
    bg   = info["currentBG"]
    short = bg["shortName"]

    # Avatar — swap once per week when the BG changes
    if bot.last_bg_nick != short:
        stem = BG_IMAGE_STEMS.get(short, short.lower())
        img  = find_image(str(IMAGES_DIR / stem))
        if img:
            try:
                with open(img, "rb") as f:
                    await bot.user.edit(avatar=f.read())
                print(f"[BG] Avatar → {img}")
            except discord.HTTPException as e:
                print(f"[WARN] Avatar update failed: {e}")
        else:
            print(f"[INFO] No image found for {short} — place images/{stem}.png")
        bot.last_bg_nick = short

    # Role ping when weekend goes live
    if bot.was_active is False and info["isActive"]:
        await send_pings(bot, CONFIG_PATH, lambda rid:
            f"<@&{rid}> 🏟️ **{short} Weekend** is now live! "
            f"Active for {format_countdown(info['msUntilEnd'])}."
        )
    bot.was_active = info["isActive"]

    # Status
    ms     = info["msUntilEnd"] if info["isActive"] else info["msUntilStart"]
    status = f"Active! | Ends in {format_countdown(ms)}" if info["isActive"] else f"Starts in {format_countdown(ms)}"
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=status)
    )
    print(f"[BG] Status: {status}")

    # Nickname (all guilds, only when changed)
    symbol = rank_prefix("bg", now)
    nick   = f"{symbol} {short} Weekend"
    for guild in bot.guilds:
        if bot.last_nicks.get(guild.id) == nick:
            continue
        try:
            await guild.me.edit(nick=nick)
            bot.last_nicks[guild.id] = nick
            print(f"[BG] Nick in '{guild.name}': {nick}")
        except Exception as e:
            print(f"[WARN] Nickname failed in '{guild.name}': {e}")


bot.run(TOKEN)
