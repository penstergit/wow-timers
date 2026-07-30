# CLAUDE.md — wow-timers

Guidance for Claude when working in this repository. Read this first; it reflects
the **actual code**, which has drifted from `README.md` in several places (see
[Doc Drift & Gotchas](#doc-drift--gotchas)).

---

## What this is

Four independent Discord bots that track recurring **WoW Classic Anniversary**
in-game events and alert a configured role/channel when each event fires. Each bot
also live-updates its Discord presence (status), server nickname, and avatar every
minute.

- **Repo:** `penstergit/wow-timers` (remote `origin`, branch **`main`**).
- **Owner:** penster. **Server admin / feature requests:** "mcg" (Dangitsmcg),
  relayed to David and back via the Betty persona.
- **Language:** Python (`discord.py`). The root `package.json` is a **stub only** —
  it exists so the Betty tooling can `project set` onto this repo. There is no
  Node app here.

### The four bots

| Bot | File | Event | Schedule (all Mountain Time) | Advance ping | Occurrence ping |
|-----|------|-------|------------------------------|--------------|-----------------|
| BG Weekend | `bot_bg.py` | Battleground Weekend, rotates AV → EOTS → WSG → AB | Thu 2am → Tue 2am | none | **pings** on go-live |
| Arena Grand Master | `bot_agm.py` | Gurubashi Arena chest | every 3h from midnight, 5-min window | **10-min ping** | silent |
| Darkmoon Faire | `bot_dmf.py` | Darkmoon Faire | first full week each month, Mon 00:01 | none | **pings** on open |
| STV Fishing | `bot_stv.py` | Stranglethorn Fishing Extravaganza | Sundays 2–4pm | **30-min ping** | silent |

**AGM and STV share one style:** the role is pinged only by the *advance warning*;
the actual-occurrence message goes out silent. **BG and DMF share the other style:**
no advance warning, the role is pinged on the occurrence itself. Keep any future
changes consistent within these pairs unless told otherwise.

---

## Architecture

### `shared.py` — the single source of truth

All four bots import from here. Do event-logic changes here, not per-bot, when the
logic is shared.

- **Timezone:** everything is `America/Denver` (`MT`), DST-safe via `zoneinfo`.
  `tzdata` is a hard dependency on Windows (no system zoneinfo db).
- **State functions** (pure, take optional `now`, return ms-based dicts):
  `get_rotation_info` (BG), `get_agm_state` (AGM), `get_dmf_state` (DMF),
  `get_stv_state` (STV). BG rotation is anchored to
  `_BG_ANCHOR = Tue 2026-03-24 08:00 UTC` (confirmed AV week).
- **Ranking:** `compute_rank` / `rank_prefix` assign the ①②③④ nickname prefix by
  urgency (active + soonest-to-end ranks first; inactive events sorted after via a
  +100-day penalty).
- **Delivery — three functions, pick deliberately:**
  - `send_pings(bot, config_path, make_message)` — appends the role mention
    `<@&roleId>` to the END of the body and **pings**. Use for advance warnings and
    for BG/DMF occurrence messages.
  - `send_broadcast(bot, config_path, make_message)` — posts with
    `allowed_mentions=AllowedMentions.none()`, **no ping**. Use for AGM/STV
    occurrence messages.
  - `send_dms(bot, config_path, make_message)` — DMs every non-bot member holding
    the configured role, per guild, **skipping guilds with `dmEnabled == False`**.
    Requires the Server Members privileged intent (`intents.members = True`, set in
    every bot's `__init__`) so `role.members` is populated. Recipients with DMs
    closed raise `discord.Forbidden` and are silently skipped. Mentions are inert in
    DMs, so the body carries no role mention — pass the same plain-body `make_message`
    used for the channel post. Fired **alongside** the channel delivery at each
    trigger: STV (30-min warning + start), AGM (**10-min warning only**, spawn stays
    DM-free), DMF (open), BG (go-live).
- **Access control:** `require_dev_role()` gates a command to members holding a role
  **named "dev"** (`DEV_ROLE_NAME`), matched case-insensitively **by name, not ID**,
  so it is portable across servers. `install_dev_error_handler(tree)` turns a failed
  check into a clean ephemeral message. Discord's `default_permissions` cannot gate
  by role name — that is why this is enforced at runtime.
- **Logging:** `setup_logging(name)` redirects `stdout`/`stderr` into
  `logs/<name>.log`, rotating at 5 MB × 3 backups.
- **Config I/O:** `load_config` / `save_guild_config` / `set_dm_enabled`. Config
  lives in `python-bots/data/<bot>-config.json`, keyed by guild id →
  `{"channelId": "...", "roleId": "...", "dmEnabled": true}`. `dmEnabled` is
  **optional and defaults to ON** (`.get("dmEnabled", True)`); `save_guild_config`
  preserves an existing `dmEnabled` across a re-`/setup`, and `set_dm_enabled(path,
  guild_id, enabled)` flips it (returns `False` if that guild has no saved config).

### Per-bot file shape (all four are near-identical)

1. Load the matching token env var, call `setup_logging`.
2. Subclass `discord.Client` with `intents.members = True` (required for `send_dms`),
   build a `CommandTree`, `tree.sync()` in `setup_hook`, start the 1-minute
   `tasks.loop`.
3. `install_dev_error_handler(bot.tree)` right after constructing the bot.
4. `/setup<x>` (channel + role → saved config), `/test<x>`, and `/<x>dms`
   (per-guild DM toggle) commands, all `@require_dev_role()`.
5. `do_update()` runs every minute: swap avatar on state change → run ping logic →
   set presence status → set nickname (only when changed, tracked in
   `last_nicks`).

### Edge-detection latches (do not break these)

- **Occurrence edge:** `was_active` / `was_up` — fire the occurrence message only on
  the `False → True` transition.
- **Advance-warning latch:** `warned_30` (STV) / `warned_next` (AGM) — fire the
  advance ping once, then **re-arm** only after the window has clearly passed, so a
  bot restart mid-window doesn't double-ping.

### Test commands

- `/teststv` and `/testagm` take a `warning: bool` arg: `warning:true` fires the
  advance ping (via `send_pings`) **and** DMs role holders; `warning:false` fires the
  occurrence message (via `send_broadcast`). STV's occurrence branch also DMs; AGM's
  spawn branch stays ping-free **and** DM-free. This mirrors production exactly.
- `/testbg` and `/testdmf` take **no** arg (single occurrence ping + DM).
- `/<x>dms enabled:<bool>` (one per bot: `/stvdms`, `/agmdms`, `/dmfdms`, `/bgdms`)
  flips that guild's `dmEnabled` via `set_dm_enabled`; replies "No config yet — run
  /setup<x> first." if the guild is unconfigured.

---

## Running locally (Windows — this host)

This machine runs the bots via **Anaconda Python + a batch file**, NOT the `.sh`
scripts (those are for a Linux deploy using `.venv/` and PID files).

**Interpreter:** `C:\Users\david\anaconda3\python.exe` (Python 3.12.7 — has
`discord.py` installed).

**Always set `PYTHONUTF8=1`** before launching. Without it, Windows uses cp1252 and
the emoji/①②③④ log lines cause a `RecursionError` in the logging path.

### Start all four
Double-click or run `python-bots\start_bots.bat`. It cd's to its own dir, sets
`PYTHONUTF8=1`, ensures `logs/`, and launches each bot in its own minimized window
logging to `logs/<name>.log`.

### Manual launch (one bot, from a shell)
```bash
cd /c/Projects/wow-timers/python-bots
PYTHONUTF8=1 /c/Users/david/anaconda3/python.exe bot_stv.py > logs/stv.log 2>&1 &
```

### Verify a bot is up
Tail its log and look for `[XXX] Online as ...` then `Status: ...`:
```bash
for b in stv agm dmf bg; do echo "== $b =="; tail -n 4 python-bots/logs/$b.log; done
```

### Find / kill a specific bot
These are backgrounded `python.exe` processes. WMI can return a **null CommandLine**
for the real python process (and will match Claude's own bash shells whose command
line contains the script name), so **the log ticking every minute is the
authoritative proof a bot is alive**, not the process list. To kill:
```powershell
Get-WmiObject Win32_Process |
  Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*bot_stv.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
**Duplicate processes are a real hazard** — two instances of the same bot cause
double-pings and slash-command "outdated" thrash. Before relaunching, confirm the
old one is dead.

### Env token names (inconsistent — read carefully)
Set in `python-bots/.env`:

| Bot | Variable |
|-----|----------|
| BG | `DISCORD_BOT_TOKEN` (bare, no suffix) |
| AGM | `DISCORD_BOT_TOKEN_ARENA` |
| DMF | `DISCORD_BOT_TOKEN_DMF` |
| STV | `DISCORD_BOT_TOKEN_FISHING` |

---

## Slash-command sync behavior

Commands are re-registered via `tree.sync()` on every startup. Right after a change
+ restart, Discord bumps the command's version and clients may briefly show
**"This command is outdated, please try again in a few minutes."** This is normal
client-cache lag, not a bug — `Ctrl+R` in Discord (or waiting ~5 min) clears it.
After changing a command's **signature** (e.g. adding the `warning` arg), the running
bot must be **restarted** for the new signature to sync into the picker.

---

## Doc Drift & Gotchas

`README.md` is partly stale. When in doubt, trust the code.

1. **`README.md` says "All commands require administrator permissions."** FALSE now.
   Commands are gated by the **"dev" role** via `require_dev_role()`, not by admin
   permission flags.
2. **`README.md` says AGM "pings twice"** (10-min + on drop). FALSE now. AGM pings
   **once** (10-min advance) and posts the spawn message silently — same style as STV.
3. **`bot_dmf.py` docstring says "Eastern time / Mon 00:01 ET."** The code actually
   uses **Mountain** (`_dmf_start` builds the time in `MT`). The docstring is wrong;
   behavior is MT.
4. **`start.sh` / `stop.sh` / `start-when-online.sh` assume a Linux `.venv/`** and PID
   files. They do **not** apply to this Windows host — use `start_bots.bat` +
   Anaconda python here.
5. **DMF nickname shows the rotating zone** (`④ DMF Mulgore` / `Elwynn` / `Terokkar`)
   via `state["location"]`, replacing the old `DMF Week` no-op ternary. The zone is a
   deterministic anchor+modulo (`get_dmf_location` in `shared.py`), **provisional**
   until `_DMF_ANCHOR_*` / `DMF_LOCATIONS` are confirmed against a real faire — there
   is **no live game feed**, the bot only knows *when* the window is open, not *where*.
6. Token env var naming is inconsistent (BG uses the bare `DISCORD_BOT_TOKEN`).

If you make a behavior change that a stale doc line describes, update that doc line
in the same commit.

---

## Conventions

- **Git:** commit + `git push origin main`. Messages: concise imperative under ~72
  chars, no attribution/Co-Authored-By lines, state *what* changed. (Matches the
  global rules in `~/.claude/CLAUDE.md`.)
- **Only commit when explicitly asked.**
- Keep STV/AGM in lockstep (advance-ping + silent occurrence) and BG/DMF in lockstep
  (occurrence-ping, no advance) unless a request explicitly diverges them.
- Shared event/delivery logic goes in `shared.py`; per-bot files stay thin.
- Don't add new files (docs/READMEs) unless asked; prefer editing existing ones.
