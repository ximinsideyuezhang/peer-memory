# 记忆地图 · 各工具原生存储结构详解

> 本文件面向「想搞清原理」和「想接入新工具」的人。
> 只想用的话看 [README](../README.md) 和 [速查卡](cheatsheet.md) 就够了。

以下结构基于 2026-09 在 Windows 上的实测。各家格式会随版本变动；
若某天检索不到内容，先用 `tools` 子命令自检，再对照本文件核对路径与字段。

---

## 总览

| | WorkBuddy | Claude Code | Codex |
|---|---|---|---|
| 根目录 | `~/.workbuddy/` | `~/.claude/` | `~/.codex/` |
| 会话正文 | `projects/<cwd编码>/<sessionId>.jsonl` | `projects/<路径编码>/<sessionId>.jsonl` | `sessions/YYYY/MM/DD/rollout-*.jsonl` |
| 兜底正文源 | — | — | `thread_history_1.sqlite` 表 `thread_items` |
| 会话标题 | 行内 `type=ai-title` → `aiTitle` | 行内 `type=ai-title` → `aiTitle` | `session_index.jsonl` → `thread_name` |
| 输入索引 | — | `history.jsonl` | `history.jsonl` |
| 长期记忆 | `memory/*.md`、`MEMORY.md`、`SOUL.md`、`USER.md`、`IDENTITY.md` | `CLAUDE.md` | `memories_1.sqlite`、`AGENTS.md` |
| 项目级记忆 | `<项目根>/.workbuddy/memory/*.md` | 项目根 `CLAUDE.md`、`projects/<编码>/memory/*.md` | 项目根 `AGENTS.md` |

---

## WorkBuddy → `~/.workbuddy/`

```
~/.workbuddy/
├── projects/
│   └── c-Users-admin-WorkBuddy-my-app/       # cwd 编码
│       └── 46e1d602-c5e0-4513-a506-06466ae69fc0.jsonl
├── memory/
│   └── <uuid>_memory.md                       # 自动沉淀的用户画像
├── MEMORY.md                                  # 用户级长期记忆（可能不存在）
├── SOUL.md / USER.md / IDENTITY.md            # 人格 / 用户档案 / 身份
└── skills/                                    # 技能目录
```

**行格式**（`projects/**/*.jsonl`）：

| `type` | 关键字段 |
|---|---|
| `message` | `role`（`user`/`assistant`）、`content[]`、`cwd`、`timestamp`（毫秒） |
| `ai-title` | `aiTitle` |

`content[]` 的元素类型为 `input_text` / `output_text`；`thinking` 与工具调用不进检索语料。

**坑**：用户消息里会混入大量系统注入（`<system-reminder>`、`<user_info>`、
`<identity_context>`、`<project_context>` 等），以及 `<cb_summary>` 会话压缩摘要。
不清洗的话，会话标题会退化成 `<environment_context>` 这类垃圾值。
`<cb_summary>` 例外——它是有价值的历史上下文，只去标签、保留正文。

---

## Claude Code → `~/.claude/`

```
~/.claude/
├── projects/
│   └── D--project-wm-wm-convert-service/      # 路径编码
│       ├── 3d009c22-a638-4503-b62f-e1ada7f0a1ff.jsonl
│       └── memory/*.md
├── history.jsonl                              # 输入索引
├── CLAUDE.md                                  # 用户级记忆（可能不存在）
└── skills/
```

**行格式**：

| `type` | 关键字段 |
|---|---|
| `user` / `assistant` | `message.content`（字符串或数组）、`message.role`、`cwd`、`timestamp` |
| `ai-title` | `aiTitle` |

**路径编码规则**：`D:\project_wm\wm-convert-service` → `D--project-wm-wm-convert-service`。
即盘符后接 `--`，路径分隔符与下划线都变成 `-`。这是**不可逆**的，`mem.py` 只把它当作
展示用的近似目录，真实 `cwd` 会从消息行里覆盖。

**坑**：`user` 行的 `content` 里常常裹着 `tool_result`，需要按元素类型过滤；
另有 `Base directory for this skill:` 开头的技能注入，不是用户说的话，必须剔除。

---

## Codex → `~/.codex/`

```
~/.codex/
├── sessions/
│   └── 2026/09/16/rollout-2026-09-16T10-27-33-<sessionId>.jsonl
├── thread_history_1.sqlite        # 表 thread_items，rollout 被清理后的兜底
├── memories_1.sqlite              # 表 stage1_outputs，结构化记忆库
├── session_index.jsonl            # 会话标题索引
├── history.jsonl                  # 输入索引
├── AGENTS.md                      # 全局指令，每次会话都注入
├── config.toml
└── skills/
```

**rollout 行格式**：

| `type` | 关键字段 |
|---|---|
| `session_meta` | `payload.cwd` |
| `response_item` | `payload.type=message`、`payload.role`、`payload.content[]`、`timestamp` |
| `event_msg` | 事件流，不用于检索 |

**坑**：

- `payload.role=developer` 是提示注入，检索时必须忽略，只取 `user` / `assistant`。
- `memories_1.sqlite` 在你机器上**可能是空的**（`stage1_outputs` 零行）——
  真正的正文在 `sessions/**/rollout-*.jsonl`，不要以为没有记忆库就等于没有历史。
- sqlite 必须**只读打开**（`file:...?mode=ro`），否则会干扰正在写入的 Codex 进程。
- 时间戳字段有纳秒精度（7 位小数），`datetime.fromisoformat` 需要先截断到 6 位。

---

## 为什么需要一个统一层

三家的差异集中在四个维度：

1. **目录布局**——项目编码方式、日期分片方式各不相同；
2. **行格式**——同一条消息，三家的 JSON 结构完全不一样；
3. **正文位置**——可能在 jsonl 里，也可能在 sqlite 表里；
4. **注入污染**——三家都会把系统提示混进用户消息，规则各不相同。

`mem.py` 用三个 Adapter 把上述差异全部收敛掉，对外只暴露两个概念：

- `Session`：`tool` / `sid` / `title` / `cwd` / `updated` / `path`
- `Item`：`role` / `text` / `ts`

所有子命令都建立在这两个概念上，因此新增工具只需再写一个 Adapter。

---

## 接入新工具

假设要接入一个名为 `newtool` 的工具，其数据在 `~/.newtool/`：

**1. 写 Adapter**（`bin/mem.py`）

```python
class NewToolAdapter(BaseAdapter):
    name = "newtool"

    def __init__(self):
        self.home = ROOT["newtool"]

    def sessions(self, limit=None):
        """返回 Session 列表，按 updated 倒序。"""
        ...

    def items(self, sess, limit=None):
        """返回该会话的 Item 列表。"""
        ...

    def hydrate(self, sess):
        """补全 title / cwd（懒加载，只在需要时才解析正文）。"""
        ...

    def memory_files(self):
        """返回 [(Path, 描述)] 形式的长期记忆文件。"""
        ...
```

**2. 注册**

```python
TOOLS = ("workbuddy", "claude", "codex", "newtool")

ROOT = {
    ...
    "newtool": Path(os.environ.get("PEER_NEWTOOL_HOME", HOME / ".newtool")),
}

LABEL = {..., "newtool": "NewTool"}

ADAPTERS = {..., "newtool": NewToolAdapter()}
```

**3. 加技能文件**

`skills/` 下新建 `newtool/SKILL.md`，照抄现有三份，把标题和 `--exclude` 默认值改掉。
然后在 `install.sh` / `install.ps1` 的 `ToolSpecs` 里加一行。

**4. 加测试样本**

`tests/test_smoke.py` 里按同样的方式造一份假数据，保证 CI 能覆盖。

原则：**只读**。Adapter 只允许打开文件读取，不得写入、迁移或修复任何数据。

---

## 行格式的稳定性风险

这三家的内部格式都不是公开契约，随版本可能变化。因此：

- 所有解析都做了容错——单行解析失败直接跳过，不中断整个检索；
- 单个数据源损坏不影响其他源；
- 检索结果为空时，先用 `tools` 自检，再用 `--scope full` 复验，
  最后才怀疑格式漂移。

若确认是格式漂移，欢迎提 Issue 并附上脱敏后的样本行。
