#requires -version 5
<#
  peer-memory launcher (PowerShell)

  Usage:  mem.ps1 <subcommand> [options]
  e.g.    mem.ps1 timeline --exclude codex --limit 20
          mem.ps1 search "redis" --exclude codex --scope full

  Why a separate launcher:
    - PowerShell 5.1 decodes child-process output with the system ANSI code
      page, which garbles the engine's UTF-8 output. Set explicitly here.
    - Windows ships a 0-byte App Execution Alias stub at
      %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe that sits on PATH but
      fails with exit code 9009. Every candidate is actually executed to
      verify it before use.

  If ExecutionPolicy blocks this file, use mem.cmd instead (execution policy
  applies to .ps1 files only, not .cmd/.bat), or run:
    powershell -NoProfile -ExecutionPolicy Bypass -File <this file> <args>

  Override the interpreter with the PEER_PYTHON environment variable.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

# Make the engine's UTF-8 output decode correctly on PowerShell 5.1
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Script = Join-Path $PSScriptRoot 'mem.py'
if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    [Console]::Error.WriteLine("[peer-memory] mem.py not found next to this launcher:")
    [Console]::Error.WriteLine("  $Script")
    exit 1
}

function Test-PythonCandidate {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        # reject the 0-byte App Execution Alias stub
        if ((Get-Item -LiteralPath $Path -Force).Length -eq 0) { return $false }
    } catch { return $false }
    try {
        $null = & $Path --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

$candidates = New-Object 'System.Collections.Generic.List[string]'

# 0) explicit override
if ($env:PEER_PYTHON) { $candidates.Add($env:PEER_PYTHON) }

# 1) WorkBuddy bundled managed Python, newest version first
$managedRoot = Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions'
if (Test-Path -LiteralPath $managedRoot) {
    Get-ChildItem -LiteralPath $managedRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object -Property Name -Descending |
        ForEach-Object { $candidates.Add((Join-Path $_.FullName 'python.exe')) }
}

# 2) python on PATH, skipping the WindowsApps stub
foreach ($name in @('python.exe', 'python3.exe')) {
    Get-Command $name -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Source -and ($_.Source -notlike '*WindowsApps*')) {
            $candidates.Add($_.Source)
        }
    }
}

# 3) common per-user / system install locations
@(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
    'C:\Python313\python.exe',
    'C:\Python312\python.exe',
    'C:\Python311\python.exe'
) | ForEach-Object { $candidates.Add($_) }

$py = $null
foreach ($c in $candidates) {
    if (Test-PythonCandidate -Path $c) { $py = $c; break }
}

if (-not $py) {
    [Console]::Error.WriteLine('[peer-memory] No working Python 3 interpreter found.')
    [Console]::Error.WriteLine('  Install Python 3, set PEER_PYTHON, or call mem.py directly:')
    [Console]::Error.WriteLine("  <python> `"$Script`" tools")
    exit 127
}

& $py $Script @Rest
exit $LASTEXITCODE
