"""
BG Weekend Bot — tracks the Battleground Weekend rotation.

Rotation: AV → EOTS → WSG → AB (resets Tuesday 2am MT)
Event live: Thursday 2am MT → Tuesday 2am MT

Commands: /setupbg, /testbg
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
    get_rotation_info, rank_prefix, send_pings, send_dms, set_dm_enabled,
    setup_logging,
    require_dev_role, install_dev_error_handler,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set in .env")

setup_logging("bg")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "bg-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"

BG_IMAGE_STEMS = {"AV": "av", "EOTS": "eots", "WSG": "wsg", "AB": "ab"}


# ── Bot class ──────────────────────────────────────────────────────────────

class BGBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True   # needed to enumerate role.members for DM alerts
        super().__init__(intents=intents)
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
install_dev_error_handler(bot.tree)


# ── Slash command ──────────────────────────────────────────────────────────

@bot.tree.command(name="setupbg", description="Configure BG Weekend alert channel and role")
@require_dev_role()
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
@require_dev_role()
async def testbg(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    short = get_rotation_info()["currentBG"]["shortName"]
    make_msg = lambda: f"🏟️ **{short} Weekend** is now live!"
    await send_pings(bot, CONFIG_PATH, make_msg)
    await send_dms(bot, CONFIG_PATH, make_msg)
    await interaction.followup.send("✅ Test ping sent.", ephemeral=True)


@bot.tree.command(name="bgdms", description="Toggle DM alerts to role holders on/off for this server")
@require_dev_role()
@app_commands.describe(enabled="True to DM role holders when the weekend goes live, False to disable")
async def bgdms(interaction: discord.Interaction, enabled: bool):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    if not set_dm_enabled(CONFIG_PATH, interaction.guild_id, enabled):
        await interaction.response.send_message(
            "No config yet — run /setupbg first.", ephemeral=True)
        return
    state = "ON" if enabled else "OFF"
    await interaction.response.send_message(f"✅ BG DM alerts now **{state}**.", ephemeral=True)
    print(f"[BG] DM alerts {state} for '{interaction.guild.name}'")


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

    # Role ping + DM to role holders when weekend goes live
    if bot.was_active is False and info["isActive"]:
        make_live_msg = lambda: (
            f"🏟️ **{short} Weekend** is now live! "
            f"Active for {format_countdown(info['msUntilEnd'])}."
        )
        await send_pings(bot, CONFIG_PATH, make_live_msg)
        await send_dms(bot, CONFIG_PATH, make_live_msg)
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
