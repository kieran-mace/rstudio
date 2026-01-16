@echo off
REM RStudio TUI Launcher for Windows
REM
REM This script launches the RStudio Terminal User Interface on Windows.
REM

setlocal enabledelayedexpansion

REM Default configuration
set "RSTUDIO_HOST=127.0.0.1"
set "RSTUDIO_PORT=8787"
set "WORKING_DIR=%CD%"
set "DEMO_MODE="

REM Parse command line arguments
:parse_args
if "%~1"=="" goto :run
if /i "%~1"=="-h" (
    set "RSTUDIO_HOST=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--host" (
    set "RSTUDIO_HOST=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="-p" (
    set "RSTUDIO_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--port" (
    set "RSTUDIO_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="-w" (
    set "WORKING_DIR=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--working-dir" (
    set "WORKING_DIR=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--demo" (
    set "DEMO_MODE=--demo"
    shift
    goto :parse_args
)
if /i "%~1"=="--help" (
    echo RStudio TUI - Terminal User Interface for RStudio
    echo.
    echo Usage: rstudio-tui [OPTIONS]
    echo.
    echo Options:
    echo   -h, --host HOST          RStudio session host (default: 127.0.0.1)
    echo   -p, --port PORT          RStudio session port (default: 8787)
    echo   -w, --working-dir DIR    Working directory
    echo   --demo                   Run in demo mode without R session
    echo   --help                   Show this help message
    exit /b 0
)
echo Unknown option: %~1
echo Use --help for usage information
exit /b 1

:run
REM Check for Python
where python >nul 2>nul
if errorlevel 1 (
    echo Error: Python is required but not found
    exit /b 1
)

REM Launch the TUI
python -m rstudio_tui.cli --host %RSTUDIO_HOST% --port %RSTUDIO_PORT% --working-dir "%WORKING_DIR%" %DEMO_MODE%
