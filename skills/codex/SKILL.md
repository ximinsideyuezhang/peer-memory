---
name: peer-memory
description: |
  Cross-tool read-only memory lookup. Use when the user wants to recall what was discussed in
  the other AI tools on this machine (WorkBuddy / Claude Code), or asks what their saved
  preferences and earlier conclusions were elsewhere. Typical asks:
  (1) "Did I ask about XX in WorkBuddy / Claude Code before?"
  (2) "Check the other two tools' memory for anything about XX."
  (3) "How did I handle XX last time in Claude Code / WorkBuddy?"
  跨工具只读记忆查询：当用户想调取另外两个 AI 工具（WorkBuddy / Claude Code）里聊过的内容、
  记住的偏好、之前的结论时使用。触发关键词：跨工具记忆、查 Claude、查 WorkBuddy、其他工具的记忆、
  之前的对话记录、上次聊过。
  Strictly read-only: only reads files under the other tools' directories. Never writes,
  modifies, or deletes anything there.
metadata:
  short-description: Query the other AI tools' local memory (read-only)
---

# peer-memory（在 Codex 中查询 WorkBuddy / Claude Code 的记忆）

同一台机器上的多个 AI 工具（WorkBuddy / Claude Code / Codex）各写各的记忆目录、互不可见。
`~/.peer-memory/bin/mem.py` 是各家共用的只读检索引擎，把各家的原生存储统一成同一套
「会话 / 条目」模型。**本技能在 Codex 中默认排除 codex 自身，只查另外两家。**

## 怎么调用

Windows 下 Codex 通过 PowerShell 执行命令，用 `.ps1` 启动器（自动处理中文编码与解释器定位）：

```powershell
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" <子命令> ...
```

若 ExecutionPolicy 挡住 `.ps1`，改用 `.cmd`（执行策略只约束 .ps1，不约束 .cmd）：

```powershell
& "$env:USERPROFILE\.peer-memory\bin\mem.cmd" <子命令> ...
```

再不行就显式指定解释器：

```powershell
& python "$env:USERPROFILE\.peer-memory\bin\mem.py" <子命令> ...
```

macOS / Linux / Git Bash 下用：

```bash
sh ~/.peer-memory/bin/mem.sh <子命令> ...
```

三个启动器行为一致，都会自动定位一个**真的能跑**的 Python 解释器
（Windows 上 `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` 是个 0 字节存根，
会以 9009 失败，启动器已过滤）。也可用环境变量 `PEER_PYTHON` 指定解释器。

> 沙箱提示：本技能只读文件。若沙箱拦截了对主目录（`~/.workbuddy`、`~/.claude`）的读取，
> 请求 escalation 后重跑同一条命令即可，不要因此改用别的手段。

## 子命令

```powershell
# 1) 环境自检，确认数据源可读（只有查不到东西时才需要）
mem.ps1 tools

# 2) 最近会话时间线——不知道关键词时先看这个，快速建立"聊过什么"的全景
mem.ps1 timeline --days 14 --limit 25 --exclude codex

# 3) 关键词检索（默认只搜会话标题 + 用户输入，毫秒级）
mem.ps1 search "对码搜索" --exclude codex

# 4) 连助手回复一起搜（慢一些，但能捞到结论和方案）
mem.ps1 search "布隆过滤器" --scope full --exclude codex

# 5) 展开某个会话的完整对话
mem.ps1 show claude 3d009c22

# 6) 看两家沉淀的"长期记忆"文件（区别于会话流水）
mem.ps1 memories --exclude codex --dump

# 7) 体量统计
mem.ps1 stats
```

通用选项：`--since YYYY-MM-DD` `--until YYYY-MM-DD` `--limit N` `--json`
`--in workbuddy,claude`（只查指定）`--exclude X`（排除指定）。

## 检索策略

1. 用户问得比较模糊（"我之前在别的工具里聊过什么"）→ 先 `timeline`。
2. 有明确关键词 → 直接 `search`；无结果就换更短的词，或加 `--scope full`。
3. 命中后按输出里的提示，用 `show <工具> <会话ID>` 取上下文。
4. 用户问的是"偏好 / 结论 / 约定"这类沉淀信息 → 用 `memories --dump`，别只搜会话流水。

## 记忆地图（两家数据源）

| 工具 | 根目录 | 会话正文 | 长期记忆 |
|---|---|---|---|
| WorkBuddy | `~/.workbuddy/` | `projects/<cwd编码>/<sessionId>.jsonl` | `memory/*.md`、`MEMORY.md`、`SOUL.md`/`USER.md`，项目级 `<项目根>/.workbuddy/memory/*.md` |
| Claude Code | `~/.claude/` | `projects/<路径编码>/<sessionId>.jsonl` | `CLAUDE.md`、`projects/<编码>/memory/*.md` |

完整地图（含行格式、路径编码规则）见 `~/.peer-memory/docs/memory-map.md`。

## 纪律

1. **严格只读。** 不写、不改、不删任何其他工具目录下的文件。这是硬约束。
2. **注明出处。** 回答时必须说明内容来自哪个工具、哪一天。不要含糊成"你之前说过"。
3. **冲突如实呈现。** 两家记忆有出入时并列展示两边原文和时间，由用户裁决，不自行取舍。
4. **查不到就说查不到。** 索引里有痕迹但正文已归档/删除时，如实说明"只在索引中留有痕迹"。
5. **别越界。** 只读记忆，顺带修改其他工具的配置也不行。
