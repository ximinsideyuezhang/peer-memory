@echo off
rem ============================================================
rem  peer-memory launcher (Windows cmd / PowerShell)
rem
rem  Usage:  mem.cmd <subcommand> [options]
rem
rem  Note: PowerShell's ExecutionPolicy restricts .ps1 files but
rem  NOT .cmd/.bat, so this launcher is the safest entry point
rem  from both cmd.exe and PowerShell.
rem
rem  Picks an interpreter by ACTUALLY RUNNING `--version`, because
rem  a bare path check is not enough: Windows ships a 0-byte
rem  App Execution Alias stub at
rem  %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe
rem  which exists on PATH but fails with exit code 9009.
rem
rem  Override with:  set PEER_PYTHON=C:\path\to\python.exe
rem  PEER_PYTHON is authoritative: if it is set but does not run, the
rem  launcher exits 127 instead of quietly picking a different interpreter.
rem ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul

set "SCRIPT=%~dp0mem.py"
set "PY="

if not exist "%SCRIPT%" (
    echo [peer-memory] mem.py not found next to this launcher: 1>&2
    echo   %SCRIPT% 1>&2
    exit /b 1
)

rem --- 0) explicit override (authoritative) ---------------------
rem  A broken PEER_PYTHON fails loudly instead of silently falling back to
rem  another interpreter. Rationale is documented in bin/mem.sh.
rem  Deliberately NOT written as a parenthesised block: the value is a path
rem  and may contain ")" (e.g. "C:\Program Files (x86)\..."), which would
rem  break block parsing.
if defined PEER_PYTHON call :try "%PEER_PYTHON%"
if defined PEER_PYTHON if not defined PY goto peer_python_bad

rem --- 1) WorkBuddy bundled managed Python (newest first) ------
if not defined PY (
    for /f "delims=" %%D in ('dir /b /ad /o-n "%USERPROFILE%\.workbuddy\binaries\python\versions" 2^>nul') do (
        if not defined PY call :try "%USERPROFILE%\.workbuddy\binaries\python\versions\%%D\python.exe"
    )
)

rem --- 2) python on PATH, skipping the WindowsApps stub --------
if not defined PY (
    for %%C in (python.exe python3.exe) do (
        if not defined PY (
            for /f "delims=" %%P in ('where %%C 2^>nul') do (
                if not defined PY (
                    echo %%P| findstr /i "WindowsApps" >nul || call :try "%%P"
                )
            )
        )
    )
)

rem --- 3) common per-user / system install locations ----------
if not defined PY (
    for %%V in (
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "C:\Python313\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if not defined PY call :try "%%~V"
    )
)

if not defined PY (
    echo [peer-memory] No working Python 3 interpreter found. 1>&2
    echo   Tried PEER_PYTHON, WorkBuddy managed Python, PATH, and common install dirs. 1>&2
    echo   Install Python 3, or run mem.py with an explicit interpreter: 1>&2
    echo   ^<python^> "%~dp0mem.py" tools 1>&2
    exit /b 127
)

%PY% "%SCRIPT%" %*
exit /b %ERRORLEVEL%

rem ---------------------------------------------------------------
rem  :try <path>   accept the candidate only if it really runs
rem ---------------------------------------------------------------
:try
if defined PY exit /b
set "CAND=%~1"
if not exist "%CAND%" exit /b
rem reject 0-byte stubs
for %%A in ("%CAND%") do if %%~zA EQU 0 exit /b
"%CAND%" --version >nul 2>nul
if errorlevel 1 exit /b
set "PY=%CAND%"
exit /b

rem ---------------------------------------------------------------
rem  PEER_PYTHON was set but is unusable: fail loudly instead of
rem  quietly running a different interpreter.
rem  !PEER_PYTHON! is expanded at execution time, so a path containing
rem  ")" or "&" cannot break parsing here.
rem ---------------------------------------------------------------
:peer_python_bad
echo [peer-memory] No working Python 3 interpreter. 1>&2
echo   PEER_PYTHON is set but is not a runnable Python 3: 1>&2
echo   !PEER_PYTHON! 1>&2
exit /b 127
