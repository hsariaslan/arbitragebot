#!/bin/bash
set -e
cd /root/coirnabot

# Update systemd service if changed
cp scripts/coirnabot.service /etc/systemd/system/coirnabot.service
systemctl daemon-reload

# Install Python dependencies
.venv/bin/pip install -r requirements.txt --quiet

# Restart (service handles cleanup of port 8765)
systemctl restart coirnabot
echo "Deploy complete, bot restarted"
