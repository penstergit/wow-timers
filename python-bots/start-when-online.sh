#!/usr/bin/env bash
# Waits for network connectivity then starts all bots.
# Intended for use with @reboot cron on systems where network
# may not be available immediately at boot.

until ping -c1 discord.com &>/dev/null; do sleep 5; done
exec "$(dirname "$0")/start.sh"
