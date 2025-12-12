#!/usr/bin/env bash
set -e  # stop on errors

PROJECT_DIR=$(python3 -c "import os, sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))" "$0")
cd "$PROJECT_DIR" || exit

APP_FILE="app.py"
VENV_DIR="venv"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment"
  python3 -m venv "$VENV_DIR"
fi

# Activate it
source "$VENV_DIR/bin/activate"

# Optimization: Only install if we can't import fastapi
# This makes the 'paperapp' command start much faster on subsequent runs
if ! python -c "import fastapi" &> /dev/null; then
    echo "Installing dependencies..."
    pip install -q fastapi==0.115.2 uvicorn==0.30.6 httpx==0.27.2
fi

# Export mailto (edit for your lab email)
export PD_MAILTO="${PD_MAILTO:-your_email@example.com}"

# --- FIX: AUTO-KILL OLD PROCESSES ON PORT 8000 ---
if lsof -ti :8000 >/dev/null; then
    echo "Port 8000 is busy. Killing old process..."
    lsof -ti :8000 | xargs kill -9
fi
# -------------------------------------------------

# Launch server
echo "Starting Paper Digest app"

# If running inside Docker, listen on 0.0.0.0 (required for external access)
# If running on a normal Mac/PC, listen on 127.0.0.1 (safer, prevents firewall popups)
if [ -f "/.dockerenv" ]; then
    HOST_IP="0.0.0.0"
    echo "🐳 Docker environment detected. Listening on 0.0.0.0"
else
    HOST_IP="127.0.0.1"
fi

uvicorn ${APP_FILE%.*}:app --host "$HOST_IP" --port 8000 --reload &

PID=$!
sleep 2

# Open browser (Mac only)
if command -v open >/dev/null; then
  open "http://127.0.0.1:8000"
elif command -v xdg-open >/dev/null; then
  xdg-open "http://127.0.0.1:8000"
else
  echo "Visit: http://127.0.0.1:8000"
fi

# Cleanup: If script is killed, kill the server
trap "kill $PID" EXIT

wait $PID