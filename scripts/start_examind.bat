@echo off
title EXAMIND — AI Examination Platform
color 0b
rem Jalankan dari folder mana pun: script ini mencari repo sibling examind-fe & examind-be
set ROOT_DIR=%~dp0..\..
set FE_DIR=%ROOT_DIR%\examind-fe
set BE_DIR=%ROOT_DIR%\examind-be
echo ===============================================================
echo                EXAMIND — AI Examination Platform
echo ===============================================================
echo.
echo Repos yang dipakai:
echo   Frontend: %FE_DIR%
echo   Backend : %BE_DIR%
echo.
echo [1/3] Memastikan MySQL XAMPP berjalan...
netstat -ano | findstr :3306 >nul
if %errorlevel% neq 0 (
    echo       Menjalankan mysqld standalone...
    start /B "" "c:\xampp\mysql\bin\mysqld.exe" --defaults-file="c:\xampp\mysql\bin\my.ini" --standalone
) else (
    echo       MySQL sudah aktif di port 3306.
)
echo.
echo [2/3] Menjalankan Backend FastAPI (Python AI Core)...
netstat -ano | findstr :8000 >nul
if %errorlevel% neq 0 (
    if not exist "%BE_DIR%\app\main.py" (
        echo       GAGAL: backend tidak ditemukan di %BE_DIR%
        echo       Clone dulu: git clone https://github.com/Rnov24/examind-be.git
    ) else (
        start /B "" cmd /c "cd /d "%BE_DIR%" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        echo       Backend FastAPI aktif di http://localhost:8000
    )
) else (
    echo       Backend sudah aktif di port 8000.
)
echo.
echo [3/3] Menjalankan Frontend Vue 3 (Vite Engine)...
netstat -ano | findstr :3000 >nul
if %errorlevel% neq 0 (
    if not exist "%FE_DIR%\package.json" (
        echo       GAGAL: frontend tidak ditemukan di %FE_DIR%
        echo       Clone dulu: git clone https://github.com/Rnov24/examind-fe.git
    ) else (
        start /B "" cmd /c "cd /d "%FE_DIR%" && npm run dev"
        echo       Frontend aktif di http://localhost:3000
    )
) else (
    echo       Frontend sudah aktif di port 3000.
)
echo.
echo Menyiapkan koneksi dan membuka browser...
timeout /t 3 /nobreak >nul
start http://localhost:3000
echo.
echo ===============================================================
echo  Aplikasi EXAMIND siap digunakan:
echo  - Web Application : http://localhost:3000
echo  - API Swagger Docs: http://localhost:8000/docs
echo.
echo  Tekan sembarang tombol untuk menutup jendela launcher ini.
echo  (Server tetap akan berjalan di latar belakang).
echo ===============================================================
pause
