#!/bin/bash
set -e
cd /root/coirnabot
.venv/bin/pip install -r requirements.txt --quiet
cd dashboard && npm install --silent && npm run build && cd ..
systemctl restart coirnabot
echo "Deploy complete, bot restarted"
