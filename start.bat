@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

rem ============================================================
rem Mudan launcher
rem ============================================================

set "PROJECT_DIR=%~dp0"
for %%I in ("%PROJECT_DIR%..") do set "PACKAGE_DIR=%%~fI"
set "PYTHON=%PACKAGE_DIR%\.venv\Scripts\python.exe"

rem ============================================================
rem Bundled uv
rem ============================================================

set "UV_EXE=%PACKAGE_DIR%\runtime\uv\uv.exe"

rem PyTorch wheels must match the recipient machine.
rem uv auto-detects the installed GPU/driver and selects the PyTorch backend.
set "UV_TORCH_BACKEND=auto"

rem Use full copies instead of Windows hardlinks so first-time setup works
rem cleanly even when the uv cache and Packages are on different volumes.
set "UV_LINK_MODE=copy"

if not exist "%UV_EXE%" (
    echo.
    echo [ERROR] Bundled uv was not found:
    echo "%UV_EXE%"
    echo.
    echo Put uv at Packages\runtime\uv\uv.exe and retry.
    echo.
    pause
    exit /b 1
)


rem ============================================================
rem 1. Prepare Python runtime
rem ============================================================

if not exist "%PYTHON%" (

    if not defined UV_EXE (
        echo.
        echo [ERROR] uv was not found.
        echo Install uv and run start.bat again.
        echo.
        pause
        exit /b 1
    )

    echo.
    echo [SETUP] Creating shared Packages Python runtime...
    echo.

    "%UV_EXE%" venv --python 3.12 "%PACKAGE_DIR%\.venv"

    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to create Python runtime.
        echo.
        pause
        exit /b 1
    )
)


rem ============================================================
rem 2. Check Python dependencies
rem
rem Keep the fast module-presence check separate from the CUDA check.
rem sentence-transformers needs torch, and this Mudan build currently
rem initializes the embedding model on CUDA.
rem ============================================================

echo [CHECK] Checking Python dependencies...

call :check_dependencies

if errorlevel 1 (

    echo.
    echo [SETUP] Installing Mudan dependencies...
    echo [SETUP] PyTorch backend: auto-detect GPU/driver
    echo.

    "%UV_EXE%" pip install ^
        --python "%PYTHON%" ^
        -r "%PROJECT_DIR%requirements.txt"

    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency installation failed.
        echo.
        pause
        exit /b 1
    )

    call :check_dependencies

    if errorlevel 1 (
        echo.
        echo [ERROR] Some Python dependencies are still missing.
        echo Check requirements.txt.
        echo.
        pause
        exit /b 1
    )
)

rem A CPU-only torch can satisfy sentence-transformers but cannot run the
rem current CUDA embedding path. Detect that explicitly and repair torch.
call :check_cuda_torch

if errorlevel 1 (
    echo.
    echo [SETUP] CUDA-enabled PyTorch is missing or unusable.
    echo [SETUP] Reinstalling torch for this machine...
    echo.

    "%UV_EXE%" pip install ^
        --python "%PYTHON%" ^
        --reinstall-package torch ^
        torch

    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install a compatible PyTorch build.
        echo.
        pause
        exit /b 1
    )

    call :check_cuda_torch

    if errorlevel 1 (
        echo.
        echo [ERROR] CUDA-enabled PyTorch is still unavailable.
        echo [ERROR] This Mudan build currently requires an NVIDIA CUDA-capable GPU.
        echo [INFO] Update/install the NVIDIA display driver, then run start.bat again.
        echo.
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import torch; print('[OK] PyTorch', torch.__version__, 'CUDA', torch.version.cuda, 'GPU', torch.cuda.get_device_name(0))"

echo [OK] Python runtime is ready.


rem ============================================================
rem --check
rem ============================================================

if /I "%~1"=="--check" (
    echo.
    echo [OK] Mudan runtime check completed.
    exit /b 0
)

:start_mudan

echo.
echo ============================================================
echo Starting Mudan...
echo ============================================================
echo.

"%PYTHON%" "%PROJECT_DIR%main.py"

set "MUDAN_EXIT_CODE=%ERRORLEVEL%"


rem ============================================================
rem 10. Final result
rem ============================================================

if not "%MUDAN_EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Mudan stopped unexpectedly.
    echo [ERROR] Exit code: %MUDAN_EXIT_CODE%
    echo.
    pause
    exit /b %MUDAN_EXIT_CODE%
)

exit /b 0


rem ============================================================
rem Helpers
rem ============================================================


:check_dependencies

"%PYTHON%" -c "import importlib.util,sys; mods=['PySide6','pygame','edge_tts','av','sounddevice','numpy','faiss','sentence_transformers','torch','jieba','pyaudio','websocket','sniffio','openai','dotenv']; missing=[m for m in mods if importlib.util.find_spec(m) is None]; print('[MISSING] '+', '.join(missing)) if missing else None; sys.exit(1 if missing else 0)" >nul 2>nul

exit /b %ERRORLEVEL%


:check_cuda_torch

"%PYTHON%" -c "import sys,torch; ok=(torch.version.cuda is not None and torch.cuda.is_available()); sys.exit(0 if ok else 1)" >nul 2>nul

exit /b %ERRORLEVEL%


