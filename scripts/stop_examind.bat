@echo off
title Stop EXAMIND
color 0c
echo ===============================================================
echo            Menghentikan Seluruh Layanan EXAMIND
echo ===============================================================
echo.
echo Menghentikan proses Backend (Python uvicorn)...
taskkill /F /IM python.exe 2>nul
echo Menghentikan proses Frontend (Node.js vite)...
taskkill /F /IM node.exe 2>nul
echo.
echo Layanan EXAMIND berhasil dihentikan.
echo ===============================================================
pause
