<!-- peer-memory:begin（跨工具记忆查询规则，可整块删除；重装时会被自动替换） -->
## 跨工具记忆查询（只读）

当用户询问"我在 WorkBuddy / Claude Code 里聊过什么""查一下其他工具的记忆"时，
用统一检索引擎 `~/.peer-memory/bin/mem.py`（纯 Python 标准库、只读，已封装各家的存储差异）：

```powershell
# Windows / PowerShell
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" tools                                    # 数据源自检
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" timeline --exclude codex --limit 20      # 最近会话全景
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" search "关键词" --exclude codex           # 搜标题 + 用户输入
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" search "关键词" --exclude codex --scope full
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" show workbuddy <会话ID>                    # 展开会话正文
& "$env:USERPROFILE\.peer-memory\bin\mem.ps1" memories --exclude codex --dump           # 长期记忆文件
```

macOS / Linux 下把上面的 `& "$env:USERPROFILE\..."` 换成 `sh ~/.peer-memory/bin/mem.sh`。

完整说明见 `~/.peer-memory/docs/memory-map.md`；Codex 内也可直接使用 `peer-memory` 技能。

纪律：严格只读，不写、不改、不删其他工具目录下的任何文件；回答注明来源工具和日期；
两家记忆有冲突时并列展示原文和时间，由用户裁决。
<!-- peer-memory:end -->
