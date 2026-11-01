@echo off
title NEXUS Backend (FastAPI)
cd /d D:\Nexus
echo Starting NEXUS FastAPI Backend on http://localhost:8000 ...
"C:\Users\skart\anaconda3\envs\spidy\python.exe" -m uvicorn nexus.api.main:app --host 0.0.0.0 --port 8000 --reload
pause

