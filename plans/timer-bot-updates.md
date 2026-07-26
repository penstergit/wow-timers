# wow-timers — Update & Adjustment Plan

**Source:** Dangitsmcg punch-list (Discord, screenshot 2026-07-22). Collaboration with **penster**,
who owns/organizes these timer bots. This doc breaks each requested change into: intent → current
behavior (with file references) → proposed approach → affected files → open questions.

> Planning only. No bot code is changed by this document. **penster answered the clarifying
> questions on 2026-07-22** (folded in below). Most items are now unblocked; the only remaining
> data dependency is the DMF month→location schedule.
>
> **Repo workflow — RESOLVED:** we have **direct push** access to `penstergit/wow-timers`.
> No fork/PR required (still fine to branch for larger changes).

---

## Architecture recap (grounded in the code)

Four `discord.py` bots under `python-bots/`, each a `discord.Client` with a 1-minute `tasks.loop`
(`do_update`) that: swaps its avatar on state change, pings a per-guild role on the active-edge
transition, updates its Discord presence + server nickname (with a `①②③④` urgency rank prefix).

| Bot | File | Event logic (in `shared.py`) | Pings |
|-----|------|------------------------------|-------|
| BG Weekend | `bot_bg.py` | `get_rotation_info` (AV→EOTS→WSG→AB) | on go-live |
| Arena Grand Master | `bot_agm.py` | `get_agm_state` (chest every 3h, 5-min window) | 10-min warning **and** on spawn |
| Darkmoon Faire | `bot_dmf.py` | `get_dmf_state` (first full week/month) | on open |
| STV Fishing | `bot_stv.py` | `get_stv_state` (Sun 2–4 PM MT) | on start |

Shared helpers: `send_pings(bot, config_path, make_message)` sends `make_message(role_id)` to every
configured guild channel. All ping strings currently **lead** with the role mention `<@&{rid}>`.
All times are **Mountain Time** (`MT = America/Denver`, DST-safe via `zoneinfo`).

---

## 1. `@role` relocated to END of all ping messages  · *all 4 bots*

- **Current:** every ping/`/test` message starts with the mention, e.g.
  `bot_dmf.py:81` → `f"<@&{rid}> 🎪 **Darkmoon Faire** is now open! ..."`. Same pattern in
  `bot_bg.py:86,126`, `bot_agm.py:104,111,141`, `bot_stv.py:79,117`.
- **Proposed:** move `<@&{rid}>` to the end of each message body (the mention still notifies from
  any position). Two ways:
  - **A. Edit each lambda** — lowest-risk, explicit, but touches ~9 strings.
  - **B. Refactor `send_pings`** — have `make_message` return the body *without* the mention and let
    `send_pings` append `f" {mention}"`. One enforced format, but changes the `make_message`
    contract (all call sites simplified). *Recommended* for consistency going forward.
- **Affected:** `shared.py` (if B), `bot_bg.py`, `bot_agm.py`, `bot_dmf.py`, `bot_stv.py`.
- **RESOLVED (penster):** ping goes at the **end** of the message body, not the start
  (`...message text @role` — a single **space** before the mention). Going with **option B** so the
  format is enforced in one place.

## 2. DMF message corrected to include ALL locations  · `bot_dmf.py`

- **Current:** message hardcodes two sites — `"Head to Elwynn Forest or Mulgore."`
  (`bot_dmf.py:81-82`, `119-121`, and `/testdmf` `79-82`). The shipped images
  (`images/dmfef.png`, `dmftb.png`, `dmftf.png`) imply **three** intended sites:
  **E**lwynn **F**orest, **T**hunder **B**luff (Mulgore), **T**erokkar **F**orest.
- **RESOLVED (penster):** DMF uses a **fixed set of locations** (not open-ended). The three site
  names are: **Elwynn Forest**, **Mulgore**, **Terokkar Forest**. The month→location *schedule* is
  still unknown and will be provided later (see item 3).
- **Proposed:** update the message to reference these three sites. Whether it lists all three or the
  current month's single site depends on the schedule (item 3); until the schedule lands, print all
  three site names so the copy is correct regardless.
- **Affected:** `bot_dmf.py` (the three message strings).

## 3. DMF right-hand-side name change based on location  · `bot_dmf.py` + `shared.py`

- **Current:** nick is always `f"{symbol} DMF Week"` — the ternary at `bot_dmf.py:135` is a no-op
  (both branches identical). Avatar swap (`:103-104`) looks for `dmf_active` / `dmf_inactive` / `dmf`
  stems, but the repo ships **location** images (`dmfef/dmftb/dmftf`) — so the avatar swap currently
  finds nothing and never updates.
- **Proposed:**
  1. Add a month→location mapping and expose the current location from `get_dmf_state`
     (e.g. `state["location"]` ∈ `{"Elwynn", "Mulgore", "Terokkar"}`).
  2. Nick suffix becomes the location, e.g. `f"{symbol} DMF {location}"`.
  3. Map avatar stem to the matching image — likely **Elwynn→`dmfef`**, **Mulgore→`dmftb`**
     (Thunder Bluff), **Terokkar→`dmftf`** (confirm stem↔site mapping when the schedule lands).
- **Affected:** `shared.py` (`get_dmf_state` + a location table), `bot_dmf.py` (nick + avatar stems).
- **STILL BLOCKED (penster):** the fixed site set is confirmed (Elwynn / Mulgore / Terokkar) but the
  authoritative **month→location schedule** is not yet known — penster will provide it later. Build
  the mapping table + wiring now; leave the schedule values as a TODO to fill in.

## 4. BG icon update + name change (currently EOTS icon w/ WSG name)  · ~~`bot_bg.py` + images~~ — **RESOLVED / NON-ISSUE**

- **RESOLVED (penster):** this is **not a bug in the repo**. The earlier symptom (WSG name w/ wrong
  icon) came from the **localhost run not having the `images/` folder synced** — so the bot changed
  the name but had no new image to rotate to. `images/wsg.png` is **not** the wrong asset (not EOTS
  art). No code or asset change needed. **Dropped from the work list.**

## 5. BG correct active start/end time — confirm w/ in-game que masters  · `shared.py`

- **Current:** weekend is live **Thu 2 AM MT → Tue 2 AM MT**; `_BG_ANCHOR = 2026-03-24 08:00 UTC`
  (Tue, "confirmed AV week"). In `get_rotation_info`: `weekend_start = week_start + 2 days` (Thu 2 AM),
  `week_end = week_start + 7 days` (Tue 2 AM). Rotation index = whole weeks since anchor mod 4.
- **RESOLVED (penster):** the current timing is **confirmed correct** — the go-live/end times and the
  **AV-week anchor are still valid**. No change to `weekend_start`/`week_end`/`_BG_ANCHOR`.
- **Affected:** none. **Dropped from the work list.**

## 6. AGM — drop the *ping* on chest spawn, keep the message  · `bot_agm.py` + `shared.py`  — **SHIPPED (corrected)**

- **Current:** two pings fired — the **10-min warning** and the **chest-spawned** ping.
  `/testagm` sends the 10-min-warning copy.
- **CORRECTION (Dangitsmcg, screenshot 2026-07-23):** the first pass **deleted the entire
  chest-spawned message**. That was too aggressive — only the **@role ping** was meant to be removed.
  The **"chest has spawned! Grab it fast — you have 5 minutes!"** message must still **post** on the
  up-edge, just **without** a role mention. "Avoid the double ping" = the role is pinged **once**
  (10-min warning), not that the second message disappears.
- **Implemented:**
  - `shared.py` — new `send_broadcast(bot, config_path, make_message)`: same delivery loop as
    `send_pings` but appends **no** mention and forces `allowed_mentions=none` (informational post).
  - `bot_agm.py` — the up-edge branch now posts the "Grab it fast" message via `send_broadcast`
    (no ping) and still resets `warned_next`. The 10-min warning keeps its ping via `send_pings`.
  - `/testagm` unchanged — still fires the 10-min-warning copy (with ping).
- **Affected:** `bot_agm.py`, `shared.py`.
- **Verify:** let the timer run and watch a real spawn — 10-min warning **pings**, drop message
  **posts with no ping**.

## 7. AGM — suppress late-night pings on weekday nights  · `bot_agm.py` (+ helper in `shared.py`)

- **Current:** the 10-min warning fires for **every** 3-hour spawn. Spawns (MT):
  `00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00`.
- **Requested rule (penster):** the AGM chest keeps spawning every 3h 24/7; the **role ping** during
  **late-night hours** should fire on **weekends only, not weekdays**. Both the "late-night hours"
  window and the weekend/weekday split are **defined by penster's screenshot** — treat that screenshot
  as authoritative for the exact hours and days.
- **Proposed:** before sending the 10-min warning, compute the *upcoming spawn's* MT hour and weekday;
  if it falls in the screenshot's late-night window **and** it's a weekday → skip the send (still
  update presence/nick). Best as a small `shared.py` helper, e.g. `agm_ping_suppressed(now) -> bool`,
  with the late-night hours + weekend days encoded as named constants sourced from the screenshot.
- **Affected:** `bot_agm.py` (guard the warning send), `shared.py` (helper).
- **Open Q (still needs pinning down):** transcribe the screenshot into exact values — (a) the precise
  late-night hour window in MT, and (b) which days count as "weekend" (Fri+Sat vs Sat+Sun). Also note
  the warning fires ~10 min **before** the spawn, so a 00:00 spawn's ping lands ~23:50 the prior
  evening — recommend keying the weekday test off the **spawn's** MT day for clarity.

---

## 8. DM role-holders on event fire  · *all 4 bots* · `shared.py` + each bot

**Source:** Dangitsmcg (Discord, 2026-07-25) + penster DM (2026-07-25). New request, added
after the original punch-list. **Time-sensitive:** mcg wants to test on Sunday **2026-07-26**
against the live STV window (2–4 PM MT, 30-min advance ~1:30 PM MT).

- **Intent (mcg):** in addition to the in-channel role ping, the bot should **DM every member
  holding the configured alert role** the same notification. Wants an **ON/OFF toggle** ("some
  sort of menu"), **default ON**. Only **AGM + STV** matter for the classic-twink discord, but
  **bake the shared helper into all 4** (harmless). mcg will hold the roles himself and test live.
- **Prerequisite — DONE:** DMing role members requires enumerating `role.members`, which needs the
  **Server Members privileged intent**. **penster enabled it in the Dev Portal (per bot app) on
  2026-07-25** → unblocked. NB: this is *not* the server Integrations "command permissions" panel
  penster set earlier — that only governs who can *invoke* the commands, not member enumeration.
- **Current:** bots only `send_pings` (channel + `<@&role>`) and `send_broadcast` (channel, silent).
  No DM path. Each bot is constructed with `discord.Intents.default()` (no members intent, so
  `role.members` would be empty).

**Proposed:**

- **`shared.py`:**
  - New **`send_dms(bot, config_path, make_message)`** — same per-guild loop as `send_pings`, but:
    skip guilds where `cfg.get("dmEnabled", True)` is `False` (default ON); resolve
    `guild.get_role(int(cfg["roleId"]))`; iterate `role.members`; skip `m.bot`; `await m.send(...)`
    wrapped in try/except (`discord.Forbidden` = user's DMs closed, `discord.HTTPException`) so one
    failure never aborts the batch. DM body reuses the existing `MSG_*` copy **without** the
    `<@&role>` mention (mentions are inert in DMs).
  - **`dmEnabled: bool`** added to the per-guild config schema. `save_guild_config` must **preserve**
    an existing `dmEnabled` when `/setup` is re-run (it currently replaces the whole guild dict and
    would reset it). Add **`set_dm_enabled(path, guild_id, enabled)`** for the toggle.
- **Each bot (`bot_stv/agm/dmf/bg.py`):**
  - Enable the intent: `intents = discord.Intents.default(); intents.members = True`. **Mandates a
    restart** (safe now that the portal intent is on; relies on discord.py default
    `chunk_guilds_at_startup=True` so `role.members` populates).
  - Call `send_dms` at the notification point(s) (see trigger table).
  - Dev-gated **toggle command** per bot, e.g. `/stvdms enabled:true|false` → `set_dm_enabled`.
    Default stays ON if never run.
  - **Test commands also DM:** `/teststv` + `/testagm` fire `send_dms` alongside the existing send so
    mcg can test on demand without waiting for the clock.

**Trigger design (DM fires where the bot already alerts):**

| Bot | DM on | Volume |
|-----|-------|--------|
| STV | 30-min advance **and** "it started" | ~2/week (light) |
| BG | go-live | ~1/week |
| DMF | open | ~1/month |
| AGM | 10-min advance (spawn DM optional) | 8/day (16 if +spawn) |

**Affected:** `shared.py`, all four `bot_*.py`, `CLAUDE.md` (document the DM path + members-intent
requirement + toggle command, same commit).

**Failure modes handled:** DMs-closed users skipped (`Forbidden`); other bots skipped; missing/renamed
role guarded; batch never aborts on one bad send. Small role → no rate-limit concern (flag for future
if a role grows large — mass DM can trip Discord spam heuristics).

**Deployment sequence:** implement → commit/push → **kill the 4 running bots** (duplicate-process
hazard) and confirm dead → relaunch all 4 → verify `[XXX] Online as …` in each log → mcg tests
`/teststv` + `/testagm`, then the live STV window at 2 PM MT. Ship before ~1:30 PM MT to catch today's
live STV advance.

**Rollback:** `/…dms enabled:false` per guild kills DMs with no redeploy. (A full code revert would
also require removing `intents.members=True` before restart — leaving it on while the portal intent is
off crashes login — so the toggle is the preferred kill switch.)

**Open Q (mcg):** AGM DM volume — **10-min heads-up only (8/day, recommended)** or **also on spawn
(16/day)**?

---

## Cross-cutting notes

- **Coordinate with penster** — he organized these bots. **Push access confirmed** (direct push to
  `penstergit/wow-timers`); branch for larger changes at our discretion, no fork/PR required.
- `data/*-config.json` (per-guild channel+role) and `logs/` are created at runtime; not in the repo.
- Locale/timezone: all schedules are MT and DST-safe already — keep new time logic in MT via `zoneinfo`.
- `requirements.txt`: `discord.py>=2.4.0`, `python-dotenv`, `tzdata`. Python venv per README.

## Suggested sequencing (post-answers)

1. **Ready to build now:**
   - #1 — role mention → end of body, single space, via option B (`send_pings` refactor).
   - #6 — remove AGM chest-drop ping; keep the 10-min warning; `/testagm` sends that copy w/ role at end.
   - #2 — DMF message names all three sites (Elwynn Forest / Mulgore / Terokkar Forest).
2. **Buildable now, one value to transcribe:**
   - #7 — AGM late-night suppression: wire the helper; fill the exact hours + weekend days from the screenshot.
3. **Scaffold now, one value pending from penster:**
   - #3 — DMF location table + nick/avatar wiring; leave the **month→location schedule** as a TODO.
4. **Closed — no work:**
   - #4 — BG WSG icon/name was a localhost image-sync artifact, not a repo bug.
   - #5 — BG start/end times + AV-week anchor confirmed correct.

## Open questions — consolidated (status)

- [x] DMF: fixed set of locations — **Elwynn Forest, Mulgore, Terokkar Forest**. *(schedule below)*
- [ ] DMF: authoritative **month→location schedule** — penster to provide later.
- [x] BG WSG icon/name — **non-issue** (localhost lacked the `images/` folder); no change.
- [x] BG go-live/end times + AV-week anchor — **confirmed valid**; no change.
- [x] AGM `/testagm` — **keep it**, send the 10-min-warning copy, role mention at end, no drop ping.
- [ ] AGM night rule: transcribe the screenshot — exact **late-night MT window** + which days are
      "weekend" (Fri+Sat vs Sat+Sun); recommend keying the test off the **spawn's** day.
- [x] Ping format — **end of message, single space** before `<@&role>`; via option B.
- [x] Repo workflow — **direct push** access confirmed.
- [x] DM feature — **Server Members intent enabled by penster (2026-07-25)**; feature unblocked.
- [x] DM feature — default **ON**, per-guild toggle, baked into all 4, AGM+STV are the priority (mcg).
- [ ] DM feature — AGM DM trigger: **10-min heads-up only (8/day, rec)** vs heads-up + spawn (16/day) —
      mcg to confirm.
