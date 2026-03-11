#!/bin/bash
set -e
cd /root/arbitragebot

# Update systemd service if changed
cp scripts/arbitragebot.service /etc/systemd/system/arbitragebot.service
systemctl daemon-reload

# Install Python dependencies
.venv/bin/pip install -r requirements.txt --quiet

# Restart (service handles cleanup of port 8765)
systemctl restart arbitragebot
echo "Deploy complete, bot restarted"
