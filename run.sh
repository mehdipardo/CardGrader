#!/usr/bin/env bash
# Launch CardGrader: FastAPI backend + static frontend server

set -e
cd "$(dirname "$0")"

echo "Starting CardGrader..."
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""
echo "Open http://localhost:3000 in your browser."
echo "Press Ctrl+C to stop both servers."
echo ""

# Start backend
uvicorn src.api:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend (serve the frontend/ directory)
python -m http.server 3000 --directory frontend &
FRONTEND_PID=$!

# Wait for Ctrl+C, then kill both
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
