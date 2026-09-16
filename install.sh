#!/usr/bin/env sh
# ============================================================
#  peer-memory installer  (macOS / Linux / Git Bash / WSL)
#
#  Usage:
#     sh install.sh                 install (auto-detects which tools you have)
#     sh install.sh --dry-run       show what would happen, change nothing
#     sh install.sh --force         overwrite a non-empty target directory
#     sh install.sh --no-agents-md  do not touch ~/.codex/AGENTS.md
#     sh install.sh --uninstall     remove everything that was installed
#
#  What it does:
#     1. copies the engine to ~/.peer-memory/
#     2. for each tool it finds (~/.workbuddy, ~/.claude, ~/.codex) it drops
#        the matching thin skill into that tool's skills directory
#     3. optionally appends a clearly-marked, removable block to
#        ~/.codex/AGENTS.md so Codex knows how to call the engine
#
#  It never writes to anything else, and --uninstall reverses it exactly.
# ============================================================
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEST="${PEER_MEMORY_HOME:-$HOME/.peer-memory}"

MODE=install
DRY=0
FORCE=0
WITH_AGENTS_MD=1

while [ $# -gt 0 ]; do
    case "$1" in
        --uninstall)      MODE=uninstall ;;
        --dry-run|-n)     DRY=1 ;;
        --force|-f)       FORCE=1 ;;
        --no-agents-md)   WITH_AGENTS_MD=0 ;;
        -h|--help)        sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)
            echo "[peer-memory] unknown option: $1 (try --help)" >&2
            exit 2
            ;;
    esac
    shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*" 2>/dev/null || printf '\n== %s\n' "$*"; }
warn() { printf '[peer-memory] %s\n' "$*" >&2; }

run() {
    if [ "$DRY" -eq 1 ]; then
        say "  (dry-run) $*"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------- 卸载
if [ "$MODE" = uninstall ]; then
    step "卸载 peer-memory"

    for t in "$HOME/.workbuddy" "$HOME/.claude" "$HOME/.codex"; do
        d="$t/skills/peer-memory"
        if [ -d "$d" ]; then
            say "  移除技能 $d"
            run rm -rf "$d"
        fi
    done

    agents="$HOME/.codex/AGENTS.md"
    if [ -f "$agents" ] && grep -q '<!-- peer-memory:begin' "$agents" 2>/dev/null; then
        say "  从 $agents 移除 peer-memory 块"
        if [ "$DRY" -eq 0 ]; then
            tmp="$agents.peer-memory.bak"
            awk '
                /<!-- peer-memory:begin/ { skip=1; next }
                /<!-- peer-memory:end -->/ { skip=0; next }
                skip==1 { next }
                { print }
            ' "$agents" \
            | awk '{ a[NR]=$0 } END { n=NR; while (n>0 && a[n] ~ /^[[:space:]]*$/) n--; for (i=1;i<=n;i++) print a[i] }' \
            > "$tmp"
            cat "$tmp" > "$agents"
            rm -f "$tmp"
        fi
    fi

    if [ -d "$DEST" ]; then
        say "  移除引擎目录 $DEST"
        run rm -rf "$DEST"
    fi

    say ""
    say "卸载完成。（若你曾把 ~/.workbuddy/USER.md 等文件交给本工具读取，它们未被改动。）"
    exit 0
fi

# ---------------------------------------------------------------- 安装
step "peer-memory 安装"

if [ ! -f "$REPO_DIR/bin/mem.py" ] || [ ! -d "$REPO_DIR/skills" ]; then
    warn "仓库布局不完整：找不到 bin/mem.py 或 skills/。"
    warn "请在克隆出来的仓库根目录运行本脚本。"
    exit 1
fi

# 目标目录安全检查：非空且看起来不是我们装的，要求 --force
if [ -d "$DEST" ] && [ ! -f "$DEST/bin/mem.py" ]; then
    if [ -n "$(ls -A "$DEST" 2>/dev/null || true)" ] && [ "$FORCE" -ne 1 ]; then
        warn "$DEST 已存在且非本工具安装的目录。"
        warn "为避免误删，已中止。确认无误后加 --force 重跑。"
        exit 1
    fi
fi

say "  源目录   $REPO_DIR"
say "  安装到   $DEST"
[ "$DRY" -eq 1 ] && say "  模式     试运行（不落盘）"

# --- 1) 引擎 ---------------------------------------------------------
step "1/3  安装检索引擎"
run mkdir -p "$DEST"
if [ "$DRY" -eq 0 ]; then
    rm -rf "$DEST/bin" "$DEST/docs"
fi
run cp -R "$REPO_DIR/bin" "$DEST/bin"
run cp -R "$REPO_DIR/docs" "$DEST/docs"
run cp "$REPO_DIR/README.md" "$DEST/README.md"
if [ -f "$REPO_DIR/README.en.md" ]; then
    run cp "$REPO_DIR/README.en.md" "$DEST/README.en.md"
fi
if [ -f "$REPO_DIR/LICENSE" ]; then
    run cp "$REPO_DIR/LICENSE" "$DEST/LICENSE"
fi
if [ "$DRY" -eq 0 ]; then
    chmod +x "$DEST/bin/mem.sh" "$DEST/bin/mem.py" 2>/dev/null || true
fi
say "  引擎   $DEST/bin/mem.py"
say "  文档   $DEST/docs/"

# --- 2) 各工具的技能 -------------------------------------------------
step "2/3  安装各工具的 peer-memory 技能"

install_skill() {
    tool_dir=$1
    skill_name=$2
    label=$3
    src="$REPO_DIR/skills/$skill_name"
    dst="$tool_dir/skills/peer-memory"

    if [ ! -d "$tool_dir" ]; then
        say "  [跳过] $label 未安装（$tool_dir 不存在）"
        return 0
    fi
    if [ ! -f "$src/SKILL.md" ]; then
        warn "  源技能缺失：$src/SKILL.md"
        return 1
    fi
    run mkdir -p "$dst"
    run cp -R "$src/." "$dst/"
    say "  [完成] $label → $dst"
}

FOUND=0
for spec in "$HOME/.workbuddy:workbuddy:WorkBuddy" \
            "$HOME/.claude:claude:Claude Code" \
            "$HOME/.codex:codex:Codex"; do
    tdir=$(printf '%s' "$spec" | cut -d: -f1)
    tname=$(printf '%s' "$spec" | cut -d: -f2)
    tlabel=$(printf '%s' "$spec" | cut -d: -f3)
    [ -d "$tdir" ] && FOUND=$((FOUND + 1))
    install_skill "$tdir" "$tname" "$tlabel"
done

# --- 3) Codex AGENTS.md ---------------------------------------------
step "3/3  Codex 全局说明块"

CODEX_AGENTS="$HOME/.codex/AGENTS.md"
BLOCK_FILE="$REPO_DIR/docs/agents-md-block.md"

if [ "$WITH_AGENTS_MD" -eq 0 ]; then
    say "  已按 --no-agents-md 跳过。"
elif [ ! -f "$BLOCK_FILE" ]; then
    warn "  找不到说明块文件 $BLOCK_FILE，已跳过。"
elif [ ! -d "$HOME/.codex" ]; then
    say "  [跳过] 未检测到 Codex。"
else
    BEGIN='<!-- peer-memory:begin'
    END='<!-- peer-memory:end -->'

    n_begin=0
    n_end=0
    if [ -f "$CODEX_AGENTS" ]; then
        n_begin=$(grep -c '<!-- peer-memory:begin' "$CODEX_AGENTS" 2>/dev/null || true)
        n_end=$(grep -c '<!-- peer-memory:end -->' "$CODEX_AGENTS" 2>/dev/null || true)
    fi

    if [ "$n_begin" != "$n_end" ]; then
        warn "  $CODEX_AGENTS 里的 peer-memory 标记不配对（begin=$n_begin end=$n_end），已跳过以免损坏文件。"
        warn "  请手动清理后重跑。"
    else
        if [ "$DRY" -eq 0 ]; then
            tmp="$CODEX_AGENTS.peer-memory.tmp"
            if [ -f "$CODEX_AGENTS" ]; then
                # 先摘掉旧块，再去掉尾部空行
                awk '
                    /<!-- peer-memory:begin/ { skip=1; next }
                    /<!-- peer-memory:end -->/ { skip=0; next }
                    skip==1 { next }
                    { print }
                ' "$CODEX_AGENTS" \
                | awk '{ a[NR]=$0 } END { n=NR; while (n>0 && a[n] ~ /^[[:space:]]*$/) n--; for (i=1;i<=n;i++) print a[i] }' \
                > "$tmp"
                cat "$tmp" > "$CODEX_AGENTS"
                rm -f "$tmp"
            else
                mkdir -p "$(dirname "$CODEX_AGENTS")"
                : > "$CODEX_AGENTS"
            fi

            if [ -s "$CODEX_AGENTS" ]; then
                printf '\n' >> "$CODEX_AGENTS"
            fi

            cat "$BLOCK_FILE" >> "$CODEX_AGENTS"

            say "  [完成] 已写入 $CODEX_AGENTS"
            if [ "$n_begin" -gt 0 ]; then
                say "         （替换了原有的 peer-memory 块）"
            fi
        else
            say "  (dry-run) 将写入 $CODEX_AGENTS 的 peer-memory 块"
        fi
    fi
fi

# --- 收尾 -----------------------------------------------------------
step "验证"

if [ "$DRY" -eq 1 ]; then
    say "  (dry-run) 跳过"
else
    if out=$(sh "$DEST/bin/mem.sh" tools 2>&1); then
        printf '%s\n' "$out" | sed 's/^/  /'
        say ""
        say "  [OK] 引擎可正常运行。"
    else
        warn "  引擎自检失败，输出如下："
        printf '%s\n' "$out" >&2
        warn "  请确认已安装 Python 3，或设置 PEER_PYTHON 指向解释器。"
    fi
fi

step "完成"

if [ "$FOUND" -eq 0 ]; then
    say "  没有检测到 WorkBuddy / Claude Code / Codex 的配置目录。"
    say "  引擎已装好，但没有任何工具会去调用它——"
    say "  先安装至少一个受支持的工具，再重跑本脚本。"
else
    say "  装好 $FOUND 个工具的技能。"
fi

say ""
say "生效时机："
say "  WorkBuddy / Claude Code  新开一个会话即可"
say "  Codex                    下一轮对话即可（技能按目录实时发现，无需注册）"
say ""
say "试一句："
say "  \"查一下我在其他 AI 工具里之前有没有聊过 XX\""
say ""
say "手动调用："
say "  sh $DEST/bin/mem.sh timeline --limit 20"
say ""
say "卸载：  sh $REPO_DIR/install.sh --uninstall"
