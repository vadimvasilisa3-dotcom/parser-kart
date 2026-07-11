@echo off
chcp 65001 >nul
title Салон-Маркетолог — запуск
cd /d "%~dp0"

echo.
echo  Салон-Маркетолог — настраиваю и запускаю...
echo.

:: Python
where py >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Установите Python 3 с python.org
  pause
  exit /b 1
)

:: .env для бэкенда
if not exist "backend\.env" (
  copy /Y "backend\.env.example" "backend\.env" >nul
  echo [OK] Создан backend\.env — ключи VK/Яндекс добавите позже
)

:: Виртуальное окружение + зависимости
if not exist "backend\.venv\Scripts\python.exe" (
  echo [..] Устанавливаю зависимости бэкенда (первый раз ~1 мин)...
  py -3 -m venv backend\.venv
  backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
  echo [OK] Зависимости установлены
)

:: Проверка: бэкенд уже на 8000?
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  start "Салон-Маркетолог — сервер OAuth" /min cmd /c "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000"
  echo [OK] Сервер OAuth запущен на порту 8000
) else (
  echo [OK] Сервер OAuth уже работает на 8000
)

:: Проверка: фронт уже на 8777?
netstat -ano | findstr ":8777 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  start "Салон-Маркетолог — сайт" /min cmd /c "cd /d "%~dp0" && py -3 -m http.server 8777 --bind 127.0.0.1"
  echo [OK] Сайт запущен на порту 8777
) else (
  echo [OK] Сайт уже работает на 8777
)

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8777"

echo.
echo  Готово! Браузер откроется сам.
echo  Закрыть: закройте два маленьких окна «Салон-Маркетолог» в панели задач.
echo.
pause
