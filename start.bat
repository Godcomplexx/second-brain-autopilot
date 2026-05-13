@echo off
echo Starting Ollama...
start "" "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" serve
timeout /t 3 /nobreak >nul
echo Starting Smart Notes Aggregator...
cd /d "%~dp0"
python interview_trainer\server.py
