@echo off
title Paytm Vyapar Saathi - Mock Production Backend
echo Starting Paytm Mock Backend Server on port 8000...
python -m uvicorn mock_backend.main:app --host 127.0.0.1 --port 8000 --reload
pause
