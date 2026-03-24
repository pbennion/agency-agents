@echo off
chcp 65001 >nul
title Kommo MCP — Установка

echo ================================================
echo   Kommo MCP Server — Автоматическая установка
echo ================================================
echo.

:: --- Проверка Python ---
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установи Python 3.10+ с https://python.org и убедись,
    echo что при установке отмечена галочка "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python найден:
python --version
echo.

:: --- Проверка git ---
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Git не найден. Скачиваем ZIP вместо клонирования...
    set USE_ZIP=1
) else (
    set USE_ZIP=0
)
echo.
:: --- Папка установки ---
set INSTALL_DIR=%USERPROFILE%\kommo-mcp
echo [INFO] Папка установки: %INSTALL_DIR%
echo.

if %USE_ZIP%==0 (
    :: --- Клонирование через git ---
    if exist "%INSTALL_DIR%" (
        echo [INFO] Папка уже существует, обновляем...
        cd /d "%INSTALL_DIR%"
        git pull
    ) else (
        git clone https://github.com/NatrixAi/kommo-mcp.git "%INSTALL_DIR%"
    )
) else (
    :: --- Скачивание ZIP через PowerShell ---
    if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
    echo [INFO] Скачиваем архив с GitHub...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/NatrixAi/kommo-mcp/archive/refs/heads/main.zip' -OutFile '%TEMP%\kommo-mcp.zip'"
    powershell -Command "Expand-Archive -Path '%TEMP%\kommo-mcp.zip' -DestinationPath '%TEMP%\kommo-mcp-unzip' -Force"
    xcopy /E /I /Y "%TEMP%\kommo-mcp-unzip\kommo-mcp-main\*" "%INSTALL_DIR%\"
    echo [OK] Файлы распакованы.
)
echo.

:: --- Установка зависимостей ---
echo [INFO] Устанавливаем Python-зависимости...
pip install -r "%INSTALL_DIR%\requirements.txt"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)
echo [OK] Зависимости установлены.
echo.
:: --- Запрос данных Kommo ---
echo ================================================
echo   Введи данные Kommo CRM
echo ================================================
echo.
set /p KOMMO_TOKEN=Введи KOMMO_TOKEN (API-ключ): 
set /p KOMMO_SUBDOMAIN=Введи KOMMO_SUBDOMAIN (например mycompany): 
echo.

:: --- Путь к server.py ---
set SERVER_PATH=%INSTALL_DIR%\server.py
set SERVER_PATH_JSON=%INSTALL_DIR:\=\\%\\server.py

:: --- Путь к конфигу Claude Desktop ---
set CONFIG_DIR=%APPDATA%\Claude
set CONFIG_FILE=%CONFIG_DIR%\claude_desktop_config.json

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
echo [INFO] Путь к конфигу: %CONFIG_FILE%
echo.
:: --- Запись конфига через PowerShell ---
echo [INFO] Записываем конфиг Claude Desktop...

powershell -Command ^
  "$config = @{};" ^
  "if (Test-Path '%CONFIG_FILE%') { try { $config = Get-Content '%CONFIG_FILE%' -Raw | ConvertFrom-Json -AsHashtable } catch {} };" ^
  "if (-not $config.ContainsKey('mcpServers')) { $config['mcpServers'] = @{} };" ^
  "$config['mcpServers']['kommo'] = @{ command='python'; args=@('%SERVER_PATH_JSON%'); env=@{ KOMMO_TOKEN='%KOMMO_TOKEN%'; KOMMO_SUBDOMAIN='%KOMMO_SUBDOMAIN%' } };" ^
  "$config | ConvertTo-Json -Depth 10 | Set-Content '%CONFIG_FILE%' -Encoding UTF8"

if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось записать конфиг.
    pause
    exit /b 1
)
echo [OK] Конфиг записан.
echo.
:: --- Финал ---
echo ================================================
echo   Установка завершена успешно!
echo ================================================
echo.
echo Что делать дальше:
echo  1. Закрой Claude Desktop полностью (через трей)
echo  2. Открой Claude Desktop заново
echo  3. В новом чате должен появиться значок молотка (инструменты)
echo  4. Спроси: "покажи мои лиды в Kommo" — и проверь работу
echo.
echo Файлы установлены в: %INSTALL_DIR%
echo Конфиг Claude Desktop: %CONFIG_FILE%
echo.
pause
