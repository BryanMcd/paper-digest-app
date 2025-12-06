#!/usr/bin/env bash
set -e  # stop on errors

APP_FILE="app.py"
VENV_DIR="venv"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment"
  python3 -m venv "$VENV_DIR"
fi

# Activate it
source "$VENV_DIR/bin/activate"

# Install dependencies if missing
echo "Installing dependencies"
pip install -q fastapi==0.115.2 uvicorn==0.30.6 httpx==0.27.2

# Export mailto (edit for your lab email)
export PD_MAILTO="bryanmcd92@gmail.com"

# Launch server
echo "Starting Paper Digest app"
uvicorn ${APP_FILE%.*}:app --reload --port 8000 &

PID=$!
sleep 2

# Open browser automatically
if command -v open >/dev/null; then
  open "http://127.0.0.1:8000"
elif command -v xdg-open >/dev/null; then
  xdg-open "http://127.0.0.1:8000"
else
  echo "Visit: http://127.0.0.1:8000"
fi

wait $PID
