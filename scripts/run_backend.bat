@echo off
cd /d D:\demo1\backend
"D:\Python313\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> ..\logs\be_out.log 2>> ..\logs\be_err.log