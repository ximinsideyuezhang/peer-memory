---
name: peer-memory
description: |
  跨工具只读记忆查询。当用户想调取"其他 AI 工具（WorkBuddy / Codex）里聊过的内容、
  记住的偏好、之前的结论"时使用。典型问法：
  (1) "我在 WorkBuddy / Codex 里之前问过 XX 吗"
  (2) "查一下另外两个工具的记忆里有没有关于 XX 的内容"
  (3) "我上次在 Codex / WorkBuddy 里是怎么处理 XX 的"
  (4) "那个方案之前讨论过吗，别的工具里有没有记"
  触发关键词：跨工具记忆、查 WorkBuddy、查 Codex、其他工具的记忆、之前的对话记录、上次聊过。
  Strictly read-only: only reads files under the other tools' directories.
---

# peer-memory（在 Claude Code 中查询 WorkBuddy / Codex 的记忆）

同一台机器上的多个 AI 工具（WorkBuddy / Claude Code / Codex）各写各的记忆目录、互不可见。
`~/.peer-memory/bin/mem.py` 是各家共用的只读检索引擎，把各家的原生存储统一成同一套
「会话 / 条目」模型。**本技能在 Claude Code 中默认排除 claude 自身，只查另外两家。**

## 怎么调用

引擎是纯 Python 标准库脚本，零依赖。按环境挑一条：

```bash
# macOS / Linux / Git Bash
sh ~/.peer-memory/bin/mem.sh <子命令> ...
```

```powershell
# Windows PowerShell
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" <子命令> ...
```

```bat
rem Windows cmd
%USERPROFILE%\.peer-memory\bin\mem.cmd <子命令> ...
```

启动器会自动定位可用的 Python 解释器。若启动器不可用，用解释器直接调脚本：

```bash
python3 ~/.peer-memory/bin/mem.py <子命令> ...
```

> **PATH 被裁剪的环境**：`sh mem.sh ...` 可能以 exit 127 静默失败（报错只在 stderr），
> 容易被误判成"查不到内容"。此时直接用解释器绝对路径调 `mem.py`。

## 子命令

```bash
# 1) 环境自检，确认数据源可读（只有查不到东西时才需要）
mem.sh tools

# 2) 最近会话时间线——不知道关键词时先看这个，快速建立"聊过什么"的全景
mem.sh timeline --days 14 --limit 25 --exclude claude

# 3) 关键词检索（默认只搜会话标题 + 用户输入，毫秒级）
mem.sh search "对码搜索" --exclude claude

# 4) 连助手回复一起搜（慢一些，但能捞到结论和方案）
mem.sh search "布隆过滤器" --scope full --exclude claude

# 5) 展开某个会话的完整对话
mem.sh show workbuddy 46e1d602

# 6) 看两家沉淀的"长期记忆"文件（区别于会话流水）
mem.sh memories --exclude claude --dump

# 7) 体量统计
mem.sh stats
```

通用选项：`--since YYYY-MM-DD` `--until YYYY-MM-DD` `--limit N` `--json`
`--in workbuddy,codex`（只查指定）`--exclude X`（排除指定）。

## 检索策略

1. 用户问得比较模糊（"我之前在别的工具里聊过什么"）→ 先 `timeline`。
2. 有明确关键词 → 直接 `search`；无结果就换更短的词，或加 `--scope full`。
3. 命中后按输出里的提示，用 `show <工具> <会话ID>` 取上下文。
4. 用户问的是"偏好 / 结论 / 约定"这类沉淀信息 → 用 `memories --dump`，别只搜会话流水。

## 记忆地图（两家数据源）

| 工具 | 根目录 | 会话正文 | 长期记忆 |
|---|---|---|---|
| WorkBuddy | `~/.workbuddy/` | `projects/<cwd编码>/<sessionId>.jsonl` | `memory/*.md`、`MEMORY.md`、`SOUL.md`/`USER.md`，项目级 `<项目根>/.workbuddy/memory/*.md` |
| Codex | `~/.codex/` | `sessions/YYYY/MM/DD/rollout-*.jsonl`（兜底 `thread_history_1.sqlite`） | `memories_1.sqlite`、`AGENTS.md` |

完整地图（含行格式、路径编码规则）见 `~/.peer-memory/docs/memory-map.md`。

## 纪律

1. **严格只读。** 不写、不改、不删任何其他工具目录下的文件。这是硬约束。
2. **注明出处。** 回答时必须说明内容来自哪个工具、哪一天。不要含糊成"你之前说过"。
3. **冲突如实呈现。** 两家记忆有出入时并列展示两边原文和时间，由用户裁决，不自行取舍。
4. **查不到就说查不到。** 索引里有痕迹但正文已归档/删除时，如实说明"只在索引中留有痕迹"。
5. **别越界。** 只读记忆，顺带修改其他工具的配置也不行。
