# WoW Classic Anniversary Timers

Four Discord bots that track in-game events for WoW Classic Anniversary, pinging a configured role when each event goes live.
Arena Grand Master bot pings twice, once at 20 minutes prior, and again at the drop of the chest every 3 hours.

| Bot | Event | Schedule |
|-----|-------|----------|
| **BG Weekend** | Battleground Weekend (AV → EOTS → WSG → AB rotation) | Thu 2am MT – Tue 2am MT |
| **Arena Grand Master** | Gurubashi Arena chest spawns | Every 3 hours from midnight MT, 5-min window |
| **Darkmoon Faire** | Darkmoon Faire | First full week of each month (Mon 00:01 MT) |
| **STV Fishing** | Stranglethorn Fishing Extravaganza | Sundays 2–4 PM MT |

Each bot updates its Discord status and nickname every minute with a live countdown, and swaps its avatar between active/inactive states.

## Setup

### 1. Install dependencies

```bash
cd python-bots
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configure tokens

```bash
cp .env.example .env
# Edit .env and fill in your four bot tokens
```

Create a bot application for each event at https://discord.com/developers/applications. Each bot needs these permissions: **Change Nickname**, **Send Messages**, **View Channel**, **Read Message History**, **Use Application Commands** (permission integer: `2214661120`).

### 3. Add images (optional)

Place images in the `images/` directory to set bot avatars. Supported formats: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`.

| Bot | Image filenames |
|-----|----------------|
| BG Weekend | `av.png`, `eots.png`, `wsg.png`, `ab.png` |
| Arena Grand Master | `arena.png` |
| Darkmoon Faire | `dmf_active.png`, `dmf_inactive.png` (or just `dmf.png`) |
| STV Fishing | `fishing_active.png`, `fishing_inactive.png` (or just `fishing.png`) |

### 4. Start the bots

```bash
./start.sh   # start all bots
./stop.sh    # stop all bots
```

To start automatically on boot (waits for network before starting), add to your crontab (`crontab -e`):

```
@reboot /path/to/wow-timers/python-bots/start-when-online.sh
```

Logs are written to `logs/bg.log`, `logs/agm.log`, `logs/dmf.log`, `logs/stv.log`. Each log file rotates at 5 MB, keeping up to 3 backups.

## Discord commands

All commands require administrator permissions.

| Command | Bot | Description |
|---------|-----|-------------|
| `/setupbg` | BG Weekend | Set alert channel and role |
| `/setupagm` | Arena Grand Master | Set alert channel and role |
| `/setupdmf` | Darkmoon Faire | Set alert channel and role |
| `/setupstv` | STV Fishing | Set alert channel and role |
| `/testbg` | BG Weekend | Send a test ping immediately |
| `/testagm` | Arena Grand Master | Send a test ping immediately |
| `/testdmf` | Darkmoon Faire | Send a test ping immediately |
| `/teststv` | STV Fishing | Send a test ping immediately |

Guild configs are stored in `python-bots/data/bg-config.json`, `python-bots/data/agm-config.json`, etc.
