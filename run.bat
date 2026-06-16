@echo off
REM Launch CardGrader: FastAPI backend + static frontend server

echo Starting CardGrader...
echo   Backend  -^> http://localhost:8000
echo   Frontend -^> http://localhost:3000
echo.
echo Open http://localhost:3000 in your browser.
echo Close this window or press Ctrl+C to stop both servers.
echo.

REM Start backend in a new window
start "CardGrader Backend" cmd /k "uvicorn src.api:app --reload --port 8000"

REM Start frontend server in a new window
start "CardGrader Frontend" cmd /k "python -m http.server 3000 --directory frontend"

echo Both servers started in separate windows.
pause
