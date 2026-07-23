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

## 6. AGM — remove the "chest dropped" ping, keep only the 10-min advance  · `bot_agm.py`

- **Current:** two pings fire — the **10-min warning** (`bot_agm.py:102-106`) and the
  **chest-spawned** ping (`:109-113`). `/testagm` (`:136-144`) sends the spawn message.
- **Proposed:** delete the chest-spawned `send_pings` block; **keep** the `was_up` state tracking so
  `warned_next` still resets each cycle (`bot.warned_next = False` on the up-edge), just without
  sending. This kills the **double ping** — role is mentioned **only** on the 10-min-prior warning.
- **RESOLVED (penster):** **keep `/testagm`**, sending the **same message**, but with the `@role` at
  the **end** of the message (per item 1), and ping **only on the 10-min-prior** path — do **not**
  ping on the drop. Point `/testagm` at the 10-min-warning copy so tests match live behavior.
- **Affected:** `bot_agm.py` only.

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
