"""
Darkmoon Faire Bot — tracks the monthly Darkmoon Faire.

Active during the first full week of each month (Eastern time).
Starts Monday 00:01 ET, ends 7 days later.

Commands: /setupdmf, /testdmf
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
    get_dmf_state, rank_prefix, send_pings, send_dms, set_dm_enabled,
    setup_logging,
    require_dev_role, install_dev_error_handler,
)

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN_DMF")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN_DMF is not set in .env")

setup_logging("dmf")

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = str(SCRIPT_DIR / "data" / "dmf-config.json")
IMAGES_DIR  = SCRIPT_DIR / "images"

def make_open_msg(loc: dict) -> str:
    """Occurrence message naming the specific zone for this month's faire.

    ``loc`` is a DMF_LOCATIONS entry ({"name", "short"}) from get_dmf_state.
    """
    return (f"🎪 **Darkmoon Faire** is now open in **{loc['name']}** for the week! "
            f"Head over and grab your buffs before your next PvP session.")


class DMFBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True   # needed to enumerate role.members for DM alerts
        super().__init__(intents=intents)
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
install_dev_error_handler(bot.tree)


@bot.tree.command(name="setupdmf", description="Configure Darkmoon Faire alert channel and role")
@require_dev_role()
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


@bot.tree.command(name="testdmf", description="Ping the saved role in the saved channel")
@require_dev_role()
async def testdmf(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    loc = get_dmf_state(datetime.now(timezone.utc))["location"]
    await send_pings(bot, CONFIG_PATH, lambda: make_open_msg(loc))
    await send_dms(bot, CONFIG_PATH, lambda: make_open_msg(loc))
    await interaction.followup.send("✅ Test ping sent.", ephemeral=True)


@bot.tree.command(name="dmfdms", description="Toggle DM alerts to role holders on/off for this server")
@require_dev_role()
@app_commands.describe(enabled="True to DM role holders when the faire opens, False to disable")
async def dmfdms(interaction: discord.Interaction, enabled: bool):
    if not interaction.guild:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    if not set_dm_enabled(CONFIG_PATH, interaction.guild_id, enabled):
        await interaction.response.send_message(
            "No config yet — run /setupdmf first.", ephemeral=True)
        return
    state = "ON" if enabled else "OFF"
    await interaction.response.send_message(f"✅ DMF DM alerts now **{state}**.", ephemeral=True)
    print(f"[DMF] DM alerts {state} for '{interaction.guild.name}'")


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

    # Role ping + DM to role holders when faire opens
    if bot.was_active is False and state["active"]:
        await send_pings(bot, CONFIG_PATH, lambda: make_open_msg(state["location"]))
        await send_dms(bot, CONFIG_PATH, lambda: make_open_msg(state["location"]))
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
    nick   = f"{symbol} DMF {state['location']['short']}"
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
