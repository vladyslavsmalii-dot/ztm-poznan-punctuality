#!/bin/bash
# Installs the collector as a systemd service.
# Tested on Debian 13 (Google Cloud e2-micro). Usage: bash collector/install.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

command -v python3 >/dev/null || { sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3; }
mkdir -p "$HOME/ztm"
cp "$DIR/collector.py" "$HOME/ztm/collector.py"

sudo tee /etc/systemd/system/ztm-collector.service > /dev/null <<UNIT
[Unit]
Description=ZTM Poznan GTFS-RT collector
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
ExecStart=/usr/bin/python3 $HOME/ztm/collector.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

sudo install -m 755 "$DIR/ztm-status.sh" /usr/local/bin/ztm-status
sudo systemctl daemon-reload
sudo systemctl enable --now ztm-collector
echo "Installed. Check it with: ztm-status"
