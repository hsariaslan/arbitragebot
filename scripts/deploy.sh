#!/bin/bash
set -e
cd /root/coirnabot

# Update systemd service if changed
cp scripts/coirnabot.service /etc/systemd/system/coirnabot.service
systemctl daemon-reload

# Install dependencies and build dashboard
.venv/bin/pip install -r requirements.txt --quiet
cd dashboard && npm install --silent && npm run build && cd ..

# Restart (service handles cleanup of port 8765)
systemctl restart coirnabot
echo "Deploy complete, bot restarted"
