#requires -version 5
<#
  peer-memory installer  (Windows PowerShell)

  Usage:
    .\install.ps1                  install (auto-detects which tools you have)
    .\install.ps1 -DryRun          show what would happen, change nothing
    .\install.ps1 -Force           overwrite a non-empty target directory
    .\install.ps1 -NoAgentsMd      do not touch ~/.codex/AGENTS.md
    .\install.ps1 -Uninstall       remove everything that was installed

  What it does:
    1. copies the engine to ~/.peer-memory/
    2. for each tool it finds (~/.workbuddy, ~/.claude, ~/.codex) it drops the
       matching thin skill into that tool's skills directory
    3. optionally appends a clearly-marked, removable block to
       ~/.codex/AGENTS.md so Codex knows how to call the engine

  If execution policy blocks this file, run:
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1

  MAINTENANCE NOTE — do not remove the UTF-8 BOM from this file:
    This script contains non-ASCII output. Windows PowerShell 5.1 decodes a
    script without a BOM using the system ANSI code page, which turns the
    Chinese text into mojibake and breaks parsing outright. The BOM at the very
    start of this file is what makes it load correctly on both 5.1 and 7.x.
    bin/mem.ps1 is deliberately ASCII-only, so it needs no BOM.
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$NoAgentsMd
)

$ErrorActionPreference = 'Stop'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$RepoDir = $PSScriptRoot
$HomeDir = $env:USERPROFILE
$Dest    = if ($env:PEER_MEMORY_HOME) { $env:PEER_MEMORY_HOME } else { Join-Path $HomeDir '.peer-memory' }

function Say  { param([string]$m) Write-Host $m }
function Step { param([string]$m) Write-Host ""; Write-Host ("==> " + $m) -ForegroundColor Cyan }
function Warn { param([string]$m) Write-Host ("[peer-memory] " + $m) -ForegroundColor Yellow }

$ToolSpecs = @(
    @{ Dir = (Join-Path $HomeDir '.workbuddy'); Key = 'workbuddy'; Label = 'WorkBuddy'   },
    @{ Dir = (Join-Path $HomeDir '.claude');    Key = 'claude';    Label = 'Claude Code' },
    @{ Dir = (Join-Path $HomeDir '.codex');     Key = 'codex';     Label = 'Codex'       }
)

$AgentsMd  = Join-Path $HomeDir '.codex\AGENTS.md'
$BlockFile = Join-Path $PSScriptRoot 'docs\agents-md-block.md'

# ---------------------------------------------------------------- 卸载
if ($Uninstall) {
    Step "卸载 peer-memory"

    foreach ($t in $ToolSpecs) {
        $d = Join-Path $t.Dir 'skills\peer-memory'
        if (Test-Path -LiteralPath $d) {
            Say ("  移除技能 " + $d)
            if (-not $DryRun) { Remove-Item -LiteralPath $d -Recurse -Force }
        }
    }

    if ((Test-Path -LiteralPath $AgentsMd) -and ((Get-Content -LiteralPath $AgentsMd -Raw) -match '<!-- peer-memory:begin')) {
        Say ("  从 " + $AgentsMd + " 移除 peer-memory 块")
        if (-not $DryRun) {
            $txt = Get-Content -LiteralPath $AgentsMd -Raw
            $txt = [regex]::Replace($txt, '(?s)<!-- peer-memory:begin.*?<!-- peer-memory:end -->\s*', '')
            Set-Content -LiteralPath $AgentsMd -Value $txt.TrimEnd() -Encoding UTF8
        }
    }

    if (Test-Path -LiteralPath $Dest) {
        Say ("  移除引擎目录 " + $Dest)
        if (-not $DryRun) { Remove-Item -LiteralPath $Dest -Recurse -Force }
    }

    Say ""
    Say "卸载完成。"
    exit 0
}

# ---------------------------------------------------------------- 安装
Step "peer-memory 安装"

$srcEngine = Join-Path $RepoDir 'bin\mem.py'
$srcSkills = Join-Path $RepoDir 'skills'
if ((-not (Test-Path -LiteralPath $srcEngine)) -or (-not (Test-Path -LiteralPath $srcSkills))) {
    Warn "仓库布局不完整：找不到 bin\mem.py 或 skills\。"
    Warn "请在克隆出来的仓库根目录运行本脚本。"
    exit 1
}

# 目标目录安全检查：非空且看起来不是我们装的，要求 -Force
if ((Test-Path -LiteralPath $Dest) -and (-not (Test-Path -LiteralPath (Join-Path $Dest 'bin\mem.py')))) {
    $items = @(Get-ChildItem -LiteralPath $Dest -Force -ErrorAction SilentlyContinue)
    if (($items.Count -gt 0) -and (-not $Force)) {
        Warn "$Dest 已存在且非本工具安装的目录。"
        Warn "为避免误删，已中止。确认无误后加 -Force 重跑。"
        exit 1
    }
}

Say ("  源目录   " + $RepoDir)
Say ("  安装到   " + $Dest)
if ($DryRun) { Say "  模式     试运行（不落盘）" }

# --- 1) 引擎 ---------------------------------------------------------
Step "1/3  安装检索引擎"
if (-not $DryRun) {
    $binDst  = Join-Path $Dest 'bin'
    $docsDst = Join-Path $Dest 'docs'
    foreach ($p in @($binDst, $docsDst)) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepoDir 'bin')   -Destination $Dest -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepoDir 'docs')  -Destination $Dest -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepoDir 'README.md') -Destination $Dest -Force
    foreach ($extra in @('README.en.md', 'LICENSE')) {
        $p = Join-Path $RepoDir $extra
        if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination $Dest -Force }
    }
} else {
    Say "  (dry-run) 复制 bin/ docs/ README.md LICENSE 到 $Dest"
}
Say ("  引擎   " + (Join-Path $Dest 'bin\mem.py'))
Say ("  文档   " + (Join-Path $Dest 'docs\'))

# --- 2) 各工具的技能 -------------------------------------------------
Step "2/3  安装各工具的 peer-memory 技能"

$found = 0
foreach ($t in $ToolSpecs) {
    if (-not (Test-Path -LiteralPath $t.Dir)) {
        Say ("  [跳过] " + $t.Label + " 未安装（" + $t.Dir + " 不存在）")
        continue
    }
    $found++
    $src = Join-Path $srcSkills $t.Key
    $srcSkill = Join-Path $src 'SKILL.md'
    if (-not (Test-Path -LiteralPath $srcSkill)) {
        Warn ("  源技能缺失：" + $srcSkill)
        continue
    }
    $dst = Join-Path $t.Dir 'skills\peer-memory'
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dst -Recurse -Force
    }
    Say ("  [完成] " + $t.Label + " -> " + $dst)
}

# --- 3) Codex AGENTS.md ---------------------------------------------
Step "3/3  Codex 全局说明块"

if ($NoAgentsMd) {
    Say "  已按 -NoAgentsMd 跳过。"
} elseif (-not (Test-Path -LiteralPath (Join-Path $HomeDir '.codex'))) {
    Say "  [跳过] 未检测到 Codex。"
} else {
    if (-not (Test-Path -LiteralPath $BlockFile)) {
        Warn ("  找不到说明块文件：" + $BlockFile + "，已跳过。")
    } else {
        $block = (Get-Content -LiteralPath $BlockFile -Raw -Encoding UTF8).TrimEnd()

        $existing = ''
        if (Test-Path -LiteralPath $AgentsMd) {
            $existing = Get-Content -LiteralPath $AgentsMd -Raw -Encoding UTF8
        }

        $nBegin = ([regex]::Matches($existing, '<!-- peer-memory:begin')).Count
        $nEnd   = ([regex]::Matches($existing, '<!-- peer-memory:end -->')).Count

        if ($nBegin -ne $nEnd) {
            Warn ("  " + $AgentsMd + " 里的 peer-memory 标记不配对（begin=$nBegin end=$nEnd），已跳过以免损坏文件。")
            Warn "  请手动清理后重跑。"
        } else {
            if ($DryRun) {
                Say ("  (dry-run) 将写入 " + $AgentsMd + " 的 peer-memory 块")
            } else {
                $stripped = [regex]::Replace($existing, '(?s)<!-- peer-memory:begin.*?<!-- peer-memory:end -->\s*', '')
                $stripped = $stripped.TrimEnd()
                $out = if ($stripped.Length -gt 0) { $stripped + "`r`n`r`n" + $block + "`r`n" } else { $block + "`r`n" }
                $dir = Split-Path -Parent $AgentsMd
                if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
                Set-Content -LiteralPath $AgentsMd -Value $out -Encoding UTF8 -NoNewline
                Say ("  [完成] 已写入 " + $AgentsMd)
                if ($nBegin -gt 0) { Say "         （替换了原有的 peer-memory 块）" }
            }
        }
    }
}

# --- 收尾 -----------------------------------------------------------
Step "验证"

if ($DryRun) {
    Say "  (dry-run) 跳过"
} else {
    $launcher = Join-Path $Dest 'bin\mem.ps1'
    try {
        $out = & $launcher tools 2>&1 | Out-String
        ($out.TrimEnd() -split "`r?`n") | ForEach-Object { Say ("  " + $_) }
        Say ""
        Say "  [OK] 引擎可正常运行。"
    } catch {
        Warn ("  引擎自检失败：" + $_.Exception.Message)
        Warn "  请确认已安装 Python 3，或设置 PEER_PYTHON 指向解释器。"
    }
}

Step "完成"

if ($found -eq 0) {
    Say "  没有检测到 WorkBuddy / Claude Code / Codex 的配置目录。"
    Say "  引擎已装好，但没有任何工具会去调用它——"
    Say "  先安装至少一个受支持的工具，再重跑本脚本。"
} else {
    Say ("  装好 " + $found + " 个工具的技能。")
}

Say ""
Say "生效时机："
Say "  WorkBuddy / Claude Code  新开一个会话即可"
Say "  Codex                    下一轮对话即可（技能按目录实时发现，无需注册）"
Say ""
Say "试一句："
Say "  `"查一下我在其他 AI 工具里之前有没有聊过 XX`""
Say ""
Say "手动调用："
Say ("  & `"$Dest\bin\mem.ps1`" timeline --limit 20")
Say ""
Say ("卸载：  powershell -ExecutionPolicy Bypass -File `"$RepoDir\install.ps1`" -Uninstall")
