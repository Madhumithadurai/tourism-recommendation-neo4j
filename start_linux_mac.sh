#!/usr/bin/env bash
# One-click start for Linux / macOS:  ./start_linux_mac.sh
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created backend/.env - set NEO4J_PASSWORD in it, then run this script again."
  exit 0
fi
python app.py
