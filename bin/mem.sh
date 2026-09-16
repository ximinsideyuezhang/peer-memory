#!/usr/bin/env sh
# ============================================================
#  peer-memory launcher (bash / zsh / sh / macOS / Linux / Git Bash)
#
#  Usage:  sh mem.sh <subcommand> [options]
#
#  Locates a WORKING Python 3 interpreter, then hands off to mem.py
#  in the same directory.
#
#  Why "working" and not just "found on PATH": on Windows a 0-byte
#  App Execution Alias stub sits at
#  %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe
#  It IS on PATH and `command -v python` finds it, but running it
#  fails with exit code 9009. So every candidate is actually
#  executed once; only exit code 0 is accepted.
#
#  Override with:  PEER_PYTHON=/path/to/python sh mem.sh ...
# ============================================================

# --- resolve our own directory -----------------------------------------
# Prefer shell builtins only: `dirname` is an external command and may be
# missing in stripped-down or sandboxed shells. If this launcher cannot even
# locate itself, every call fails with a confusing "mem.py not found".
_self=$0
case "$_self" in
    */*)  _dir=${_self%/*} ;;
    *\\*) _dir=${_self%\\*} ;;   # called with a native Windows path
    *)    _dir=. ;;
esac

# Git Bash / MSYS / Cygwin may hand us a native path (C:\...\bin) — convert it,
# otherwise `cd` cannot reach it.
case "$_dir" in
    *\\*|*:*)
        if command -v cygpath >/dev/null 2>&1; then
            _conv=$(cygpath -u "$_dir" 2>/dev/null) && [ -n "$_conv" ] && _dir=$_conv
        fi
        ;;
esac

DIR=$(CDPATH= cd -- "$_dir" 2>/dev/null && pwd) || DIR=.

# Last resort: the external dirname, present in every normal environment.
if [ ! -f "$DIR/mem.py" ] && command -v dirname >/dev/null 2>&1; then
    _d=$(dirname -- "$_self" 2>/dev/null) || _d=""
    if [ -n "$_d" ]; then
        _c=$(CDPATH= cd -- "$_d" 2>/dev/null && pwd) || _c=""
        [ -n "$_c" ] && DIR=$_c
    fi
fi

SCRIPT="$DIR/mem.py"

if [ ! -f "$SCRIPT" ]; then
    echo "[peer-memory] mem.py not found next to this launcher:" >&2
    echo "  $SCRIPT" >&2
    exit 1
fi

PY=""

# accept a candidate only if it actually runs
try() {
    [ -n "$PY" ] && return 0
    _c=$1
    [ -n "$_c" ] || return 0
    case "$_c" in
        # explicit path: must exist as a file
        */*|*\\*) [ -f "$_c" ] || return 0 ;;
        # bare name: must resolve on PATH
        *) command -v "$_c" >/dev/null 2>&1 || return 0 ;;
    esac
    # skip the WindowsApps stub outright
    case "$_c" in *WindowsApps*) return 0 ;; esac
    # 0-byte files are never real interpreters
    [ -s "$_c" ] || return 0
    "$_c" --version >/dev/null 2>&1 || return 0
    PY=$_c
}

# 1) explicit override
[ -n "$PEER_PYTHON" ] && try "$PEER_PYTHON"

# 2) the usual names
try python3
try python

# 3) well-known absolute locations
if [ -z "$PY" ]; then
    for _p in \
        "$HOME"/.workbuddy/binaries/python/versions/*/python.exe \
        "$HOME"/.workbuddy/binaries/python/versions/*/bin/python3 \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        /usr/bin/python3 \
        /usr/bin/python
    do
        try "$_p"
    done
fi

if [ -z "$PY" ]; then
    echo "[peer-memory] No working Python 3 interpreter found." >&2
    echo "  Install Python 3, set PEER_PYTHON, or call mem.py directly:" >&2
    echo "  <python> \"$SCRIPT\" tools" >&2
    exit 127
fi

# Under Git Bash / MSYS / Cygwin a Windows python.exe cannot parse a
# POSIX path like /c/Users/... — it resolves it to c:\c\Users\...
# Translate to a native path before handing it over.
case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
        if command -v cygpath >/dev/null 2>&1; then
            SCRIPT=$(cygpath -w "$SCRIPT")
        fi
        ;;
esac

exec "$PY" "$SCRIPT" "$@"
