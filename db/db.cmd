@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set "DIR=%~dp0"

if "%~1"=="reset" (
  docker compose -f "%DIR%docker-compose.yml" down -v
)

docker compose -f "%DIR%docker-compose.yml" up -d --build
exit /b !ERRORLEVEL!
