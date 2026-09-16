# peer-memory 速查卡

## 命令

```bash
# 三选一，行为一致，都会自动定位可用的 Python
M="sh ~/.peer-memory/bin/mem.sh"                        # macOS / Linux / Git Bash
# PowerShell:  & "$env:USERPROFILE\.peer-memory\bin\mem.ps1"
# cmd:         %USERPROFILE%\.peer-memory\bin\mem.cmd

$M tools                               # 数据源自检
$M timeline --days 14 --limit 25       # 最近会话
$M search "关键词" --scope titles      # 搜标题 + 用户输入（快）
$M search "关键词" --scope full        # 连助手回复一起搜（全）
$M show claude <会话ID>                # 展开会话正文
$M memories --dump                     # 长期记忆文件
$M stats                               # 体量统计
```

在某个工具里用时，加 `--exclude <自己>` 只查另外两家。

## 选项

| 选项 | 说明 |
|---|---|
| `--in A,B` | 只查指定工具 |
| `--exclude X` | 排除指定工具 |
| `--scope titles\|full` | 检索深度 |
| `--since` / `--until` `YYYY-MM-DD` | 时间范围 |
| `--limit N` | 结果条数上限 |
| `--max-sessions N` | 每个工具最多扫描的会话数（默认 300） |
| `--json` | JSON 输出 |

## 环境变量

| 变量 | 作用 |
|---|---|
| `PEER_PYTHON` | 指定 Python 解释器。**权威**：设了就必须真能跑，否则启动器报错退出（127），不会悄悄换一个 |
| `PEER_MEMORY_HOME` | 共享目录位置（默认 `~/.peer-memory`） |
| `PEER_WORKBUDDY_HOME` | WorkBuddy 数据目录（默认 `~/.workbuddy`） |
| `PEER_CLAUDE_HOME` | Claude Code 数据目录（默认 `~/.claude`） |
| `PEER_CODEX_HOME` | Codex 数据目录（默认 `~/.codex`） |

## 存储路径

| | WorkBuddy | Claude Code | Codex |
|---|---|---|---|
| 根目录 | `~/.workbuddy/` | `~/.claude/` | `~/.codex/` |
| 会话 | `projects/<cwd编码>/*.jsonl` | `projects/<路径编码>/*.jsonl` | `sessions/Y/M/D/rollout-*.jsonl` |
| 标题 | 行内 `type=ai-title` → `aiTitle` | 行内 `type=ai-title` → `aiTitle` | `session_index.jsonl` → `thread_name` |
| 输入索引 | — | `history.jsonl` | `history.jsonl` |
| 长期记忆 | `memory/*.md`、`MEMORY.md`、`SOUL/USER.md` | `CLAUDE.md`、`projects/<编码>/memory/*.md` | `memories_1.sqlite`、`AGENTS.md` |
| 项目记忆 | `<项目根>/.workbuddy/memory/*.md` | 项目根 `CLAUDE.md` | 项目根 `AGENTS.md` |

## 三家行格式要点

**WorkBuddy** — `type=message`（`role` + `content[]`，元素 `type=input_text/output_text`）；
时间戳毫秒；用户消息里混有 `<system-reminder>` `<cb_summary>` 等注入块。

**Claude Code** — `type=user|assistant`，正文在 `message.content`（字符串或数组）；
路径编码 `D:\a\b` → `D--a-b`。

**Codex** — `session_meta`（含 `cwd`）、`response_item`（`payload.role` + `payload.content[]`）；
`role=developer` 是注入，忽略；兜底源 `thread_history_1.sqlite` 表 `thread_items`。

## 安装位置

| 组件 | 位置 |
|---|---|
| 引擎 | `~/.peer-memory/bin/mem.py` |
| WorkBuddy 技能 | `~/.workbuddy/skills/peer-memory/SKILL.md` |
| Claude Code 技能 | `~/.claude/skills/peer-memory/SKILL.md` |
| Codex 技能 | `~/.codex/skills/peer-memory/SKILL.md` + `agents/openai.yaml` |
| Codex 全局块 | `~/.codex/AGENTS.md` 内 `<!-- peer-memory:begin/end -->` 之间 |

## 排查

| 现象 | 处理 |
|---|---|
| `No working Python 3 interpreter found` | 装 Python 3，或 `export PEER_PYTHON=/path/to/python3` |
| 报错带 **exit 9009** | 命中了 Windows 的 0 字节 `WindowsApps\python.exe` 存根，改用启动器调用 |
| PowerShell 下中文乱码 | 用 `mem.ps1`；或先执行 `[Console]::OutputEncoding=[Text.Encoding]::UTF8` |
| `.ps1` 无法运行 | 换成 `mem.cmd`（ExecutionPolicy 只约束 .ps1） |
| 某家显示"未找到" | 该工具未安装，或用 `PEER_*_HOME` 指向自定义目录 |
| 搜不到但确信聊过 | 换更短的关键词；加 `--scope full`；加 `--max-sessions` |
| 沙箱拦截读取主目录 | 请求 escalation 后重跑同一命令 |
