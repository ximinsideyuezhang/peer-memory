#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
peer-memory — 跨 AI 工具记忆统一检索引擎（严格只读）

同一台机器上并存 WorkBuddy / Claude Code / Codex 时，三家各写各的记忆，
互相看不见。本脚本把三家的原生存储抽象成同一套「会话 / 条目」模型，
使任一工具都能检索另外两家的历史。

用法：
    mem.py tools                                环境自检，看三家数据源是否可读
    mem.py timeline [--days N] [--limit N]      最近会话时间线
    mem.py search <关键词> [选项]                跨工具关键词检索
    mem.py show <工具> <会话ID> [--limit N]      展开某个会话的对话正文
    mem.py memories [--tool X]                  列出各家的长期记忆文件
    mem.py stats                                各家记忆体量统计

search 常用选项：
    --in workbuddy,claude,codex     只查指定工具（默认全部）
    --exclude codex                 排除指定工具（技能里用来实现"查别人不查自己"）
    --scope titles|full             titles=标题+用户输入（默认，快）；full=连助手回复一起搜
    --since YYYY-MM-DD              起始日期
    --until YYYY-MM-DD              截止日期
    --limit N                       最多返回 N 条命中
    --json                          输出 JSON

严格只读：本脚本不写、不改、不删任何工具目录下的文件。
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows 控制台默认非 UTF-8，强制一下，否则中文输出乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION = "1.0.0"

HOME = Path.home()
TOOLS = ("workbuddy", "claude", "codex")

# 数据源根目录（各家可能自定义位置，这里按默认约定，可被环境变量覆盖）
ROOT = {
    "workbuddy": Path(os.environ.get("PEER_WORKBUDDY_HOME", HOME / ".workbuddy")),
    "claude": Path(os.environ.get("PEER_CLAUDE_HOME", HOME / ".claude")),
    "codex": Path(os.environ.get("PEER_CODEX_HOME", HOME / ".codex")),
}

LABEL = {"workbuddy": "WorkBuddy", "claude": "Claude Code", "codex": "Codex"}

# 共享目录（技能文件、启动器都住在这里）
STORE = Path(os.environ.get("PEER_MEMORY_HOME", HOME / ".peer-memory"))

# ---------------------------------------------------------------- 基础工具

def parse_ts(v):
    """把各家五花八门的时间戳归一成 aware datetime(UTC)。失败返回 None。"""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            n = float(v)
            # > 1e11 认为是毫秒，否则是秒
            if n > 1e11:
                n /= 1000.0
            return datetime.fromtimestamp(n, tz=timezone.utc)
        s = str(v).strip()
        if not s:
            return None
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return parse_ts(float(s))
        s = s.replace("Z", "+00:00")
        # 处理纳秒精度（Codex 的 updated_at 有 7 位小数）
        m = re.match(r"^(.*\.\d{6})\d+(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_dt(dt):
    if not dt:
        return "?"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def fmt_day(dt):
    if not dt:
        return "?"
    return dt.astimezone().strftime("%Y-%m-%d")


# 各家会把系统提示、上下文注入塞进用户消息里，检索时要剥掉
_NOISE = [
    re.compile(r"<system-reminder\b[^>]*>[\s\S]*?</system-reminder>", re.I),
    re.compile(r"<app-context>[\s\S]*?</app-context>", re.I),
    re.compile(r"<environment_context>[\s\S]*?</environment_context>", re.I),
    re.compile(r"<user_info>[\s\S]*?</user_info>", re.I),
    re.compile(r"<identity_context>[\s\S]*?</identity_context>", re.I),
    re.compile(r"<project_context>[\s\S]*?</project_context>", re.I),
    re.compile(r"<project_layout>[\s\S]*?</project_layout>", re.I),
    re.compile(r"<additional_data>[\s\S]*?</additional_data>", re.I),
    re.compile(r"<memory_system>[\s\S]*?</memory_system>", re.I),
    re.compile(r"<connector-status>[\s\S]*?</connector-status>", re.I),
    re.compile(r"<wecom_forwarded_chat[\s\S]*?</wecom_forwarded_chat[^>]*>", re.I),
    re.compile(r"<available_skills>[\s\S]*?</available_skills>", re.I),
    re.compile(r"^<memory>\n[\s\S]*?\n</memory>", re.I | re.M),
    # 只去标签、保留内容：会话压缩摘要是高价值的历史上下文
    re.compile(r"</?cb_summary>", re.I),
    re.compile(r"</?user_query>", re.I),
]


def is_noise_text(s):
    """判断一段用户消息是否只是系统/技能注入，而非人真正说的话。"""
    if not s or not s.strip():
        return True
    t = s.strip()
    if t.startswith("<") or t.startswith("Caveat:") or t.startswith("Base directory for this skill"):
        return True
    if t.startswith("Summary of the conversation so far"):
        return True
    if t.startswith("[Request interrupted"):
        return True
    # 纯符号/极短，多半不是有效标题
    if len(re.sub(r"\W", "", t, flags=re.U)) < 2:
        return True
    return False


def clean(text, limit=0):
    """剥离注入块、压平空白。limit>0 时截断。"""
    if not text:
        return ""
    if not isinstance(text, str):
        return ""
    for pat in _NOISE:
        text = pat.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return text


def read_jsonl(path, max_bytes=200 * 1024 * 1024):
    """流式读 jsonl，坏行直接跳过。"""
    try:
        if not path.exists() or path.stat().st_size > max_bytes:
            return
    except Exception:
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def open_sqlite_ro(path):
    """只读打开 sqlite，不干扰正在写入的工具。"""
    try:
        if not path.exists():
            return None
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
        return con
    except Exception:
        return None


def extract_text(content):
    """从各家形态各异的 content 字段里抽纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for part in content:
        if isinstance(part, str):
            out.append(part)
            continue
        if not isinstance(part, dict):
            continue
        t = part.get("type", "")
        # 只要正文，thinking / tool_use / tool_result 一律不进检索语料
        if t in ("text", "input_text", "output_text"):
            out.append(part.get("text", "") or part.get("content", "") or "")
    return "\n".join(x for x in out if x)


class Session:
    __slots__ = ("tool", "sid", "title", "cwd", "updated", "path", "kind")

    def __init__(self, tool, sid, title="", cwd="", updated=None, path=None, kind="transcript"):
        self.tool = tool
        self.sid = sid
        self.title = title or ""
        self.cwd = cwd or ""
        self.updated = updated
        self.path = path
        self.kind = kind

    def key(self):
        return (self.tool, self.sid)


class Item:
    __slots__ = ("role", "text", "ts")

    def __init__(self, role, text, ts=None):
        self.role = role
        self.text = text
        self.ts = ts


# ---------------------------------------------------------------- 适配器

class BaseAdapter:
    name = ""
    home = None

    def available(self):
        return self.home is not None and self.home.exists()

    def sessions(self, limit=None):
        return []

    def items(self, sess, limit=None):
        return []

    def memory_files(self):
        return []

    # 从若干条消息里推断会话标题（没有 ai-title 时兜底用第一句用户输入）
    @staticmethod
    def _fallback_title(items, n=48):
        for it in items:
            if it.role != "user" or not it.text:
                continue
            if is_noise_text(it.text):
                continue
            first = it.text.strip().split("\n")[0].strip()
            if not first or is_noise_text(first):
                continue
            return first[:n] + ("…" if len(first) > n else "")
        return ""


class WorkBuddyAdapter(BaseAdapter):
    """~/.workbuddy/projects/<cwd编码>/<sessionId>.jsonl"""
    name = "workbuddy"

    def __init__(self):
        self.home = ROOT["workbuddy"]

    def _proj_dir(self):
        return self.home / "projects"

    def sessions(self, limit=None):
        d = self._proj_dir()
        if not d.is_dir():
            return []
        out = []
        for proj in d.iterdir():
            if not proj.is_dir():
                continue
            for f in proj.glob("*.jsonl"):
                if f.name.endswith(".file-rollback.ndjson"):
                    continue
                st = f.stat()
                out.append(Session(
                    self.name, f.stem, "",
                    cwd=self._guess_cwd(proj.name),
                    updated=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                    path=f,
                ))
        out.sort(key=lambda s: s.updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out[:limit] if limit else out

    @staticmethod
    def _guess_cwd(encoded):
        # c-Users-admin-WorkBuddy-2026-09-16-15-00-19 -> C:\Users\admin\WorkBuddy\...
        # 只是展示用，真实 cwd 会从消息行里覆盖
        parts = encoded.split("-")
        if not parts:
            return ""
        return parts[0].upper() + ":\\" + "\\".join(parts[1:])

    def _load(self, path, want_items=False, max_items=None):
        title, cwd, items = "", "", []
        for o in read_jsonl(path):
            t = o.get("type")
            if t == "ai-title" and not title:
                title = o.get("aiTitle", "") or ""
            elif t == "message":
                if not cwd:
                    cwd = o.get("cwd", "") or ""
                role = o.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                txt = clean(extract_text(o.get("content")))
                if not txt:
                    continue
                if role == "user" and (txt.startswith("[Request interrupted") or txt.startswith("Caveat:")):
                    continue
                items.append(Item(role, txt, parse_ts(o.get("timestamp"))))
                if max_items and len(items) >= max_items and not want_items:
                    break
        return title, cwd, items

    def items(self, sess, limit=None):
        _, _, items = self._load(sess.path, want_items=True)
        return items[:limit] if limit else items

    def hydrate(self, sess):
        title, cwd, items = self._load(sess.path, max_items=6)
        sess.title = title or self._fallback_title(items)
        if cwd:
            sess.cwd = cwd
        return sess

    def memory_files(self):
        out = []
        mdir = self.home / "memory"
        if mdir.is_dir():
            for f in sorted(mdir.glob("*.md")):
                out.append((f, "全局用户画像"))
        for n, desc in (("MEMORY.md", "用户级长期记忆"), ("USER.md", "用户画像"),
                        ("SOUL.md", "助手人格"), ("IDENTITY.md", "助手身份")):
            f = self.home / n
            if f.exists():
                out.append((f, desc))
        return out


class ClaudeAdapter(BaseAdapter):
    """~/.claude/projects/<路径编码>/<sessionId>.jsonl"""
    name = "claude"

    def __init__(self):
        self.home = ROOT["claude"]

    def sessions(self, limit=None):
        d = self.home / "projects"
        if not d.is_dir():
            return []
        out = []
        for proj in d.iterdir():
            if not proj.is_dir():
                continue
            for f in proj.glob("*.jsonl"):
                st = f.stat()
                # 0 字节文件是残留，跳过
                if st.st_size == 0:
                    continue
                out.append(Session(
                    self.name, f.stem, "",
                    cwd=self._guess_cwd(proj.name),
                    updated=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                    path=f,
                ))
        out.sort(key=lambda s: s.updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out[:limit] if limit else out

    @staticmethod
    def _guess_cwd(encoded):
        # D--project-wm-wm-convert-service -> D:\project_wm\wm-convert-service
        parts = encoded.split("-")
        if not parts:
            return ""
        return parts[0].upper() + ":\\" + "\\".join(parts[1:])

    def _load(self, path, max_items=None):
        title, cwd, items = "", "", []
        for o in read_jsonl(path):
            t = o.get("type")
            if t == "ai-title" and not title:
                title = o.get("aiTitle", "") or ""
            elif t in ("user", "assistant"):
                if not cwd:
                    cwd = o.get("cwd", "") or ""
                msg = o.get("message") or {}
                role = msg.get("role") or t
                content = msg.get("content")
                # user 行的 content 可能裹着 tool_result，extract_text 已过滤
                txt = clean(extract_text(content))
                if not txt:
                    continue
                if (txt.startswith("<local-command") or txt.startswith("Caveat:")
                        or txt.startswith("Base directory for this skill")):
                    continue
                items.append(Item(role, txt, parse_ts(o.get("timestamp"))))
                if max_items and len(items) >= max_items:
                    break
        return title, cwd, items

    def items(self, sess, limit=None):
        _, _, items = self._load(sess.path)
        return items[:limit] if limit else items

    def hydrate(self, sess):
        title, cwd, items = self._load(sess.path, max_items=6)
        sess.title = title or self._fallback_title(items)
        if cwd:
            sess.cwd = cwd
        return sess

    def memory_files(self):
        out = []
        f = self.home / "CLAUDE.md"
        if f.exists():
            out.append((f, "用户级长期记忆"))
        d = self.home / "projects"
        if d.is_dir():
            for proj in d.iterdir():
                if not proj.is_dir():
                    continue
                md = proj / "memory"
                if md.is_dir():
                    for f2 in sorted(md.glob("*.md")):
                        out.append((f2, f"项目记忆 · {proj.name}"))
        return out


class CodexAdapter(BaseAdapter):
    """~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl，兜底 thread_history_1.sqlite"""
    name = "codex"

    def __init__(self):
        self.home = ROOT["codex"]
        self._titles = None

    def _title_index(self):
        """session_id -> (thread_name, updated_at)"""
        if self._titles is not None:
            return self._titles
        idx = {}
        for o in read_jsonl(self.home / "session_index.jsonl"):
            sid = o.get("id")
            if sid:
                idx[sid] = (o.get("thread_name", "") or "", parse_ts(o.get("updated_at")))
        self._titles = idx
        return idx

    def sessions(self, limit=None):
        out = []
        seen = set()
        d = self.home / "sessions"
        if d.is_dir():
            for f in d.rglob("rollout-*.jsonl"):
                m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", f.name)
                sid = m.group(1) if m else f.stem
                if sid in seen:
                    continue
                seen.add(sid)
                st = f.stat()
                name, up = self._title_index().get(sid, ("", None))
                out.append(Session(
                    self.name, sid, name, "",
                    updated=up or datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                    path=f,
                ))
        # 兜底：sqlite 里存在但 rollout 被清理的会话
        con = open_sqlite_ro(self.home / "thread_history_1.sqlite")
        if con:
            try:
                for (sid,) in con.execute("SELECT DISTINCT thread_id FROM thread_items"):
                    if sid in seen:
                        continue
                    seen.add(sid)
                    name, up = self._title_index().get(sid, ("", None))
                    out.append(Session(self.name, sid, name, "", updated=up, path=None, kind="sqlite"))
            except Exception:
                pass
            finally:
                con.close()
        out.sort(key=lambda s: s.updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return out[:limit] if limit else out

    def _load_jsonl(self, path, max_items=None):
        cwd, items = "", []
        for o in read_jsonl(path):
            payload = o.get("payload") or {}
            t = o.get("type")
            if t == "session_meta":
                cwd = payload.get("cwd", "") or cwd
            elif t == "response_item" and payload.get("type") == "message":
                role = payload.get("role", "")
                if role not in ("user", "assistant"):
                    continue  # developer / system 是提示注入
                txt = clean(extract_text(payload.get("content")))
                if not txt:
                    continue
                items.append(Item(role, txt, parse_ts(o.get("timestamp"))))
                if max_items and len(items) >= max_items:
                    break
        return cwd, items

    def _load_sqlite(self, sid, max_items=None):
        con = open_sqlite_ro(self.home / "thread_history_1.sqlite")
        if not con:
            return "", []
        items = []
        try:
            rows = con.execute(
                "SELECT item_type, item_json, created_at_ms FROM thread_items "
                "WHERE thread_id=? ORDER BY rollout_ordinal", (sid,)
            )
            for itype, ijson, ts_ms in rows:
                if itype not in ("userMessage", "agentMessage"):
                    continue
                try:
                    obj = json.loads(ijson)
                except Exception:
                    continue
                if itype == "userMessage":
                    txt = clean(extract_text(obj.get("content")))
                    role = "user"
                else:
                    txt = clean(obj.get("text", ""))
                    role = "assistant"
                if not txt:
                    continue
                items.append(Item(role, txt, parse_ts(ts_ms)))
                if max_items and len(items) >= max_items:
                    break
        except Exception:
            pass
        finally:
            con.close()
        return "", items

    def _load(self, path, sid, max_items=None):
        if path is not None:
            return self._load_jsonl(path, max_items)
        return self._load_sqlite(sid, max_items)

    def items(self, sess, limit=None):
        _, items = self._load(sess.path, sess.sid)
        return items[:limit] if limit else items

    def hydrate(self, sess):
        cwd, items = self._load(sess.path, sess.sid, max_items=6)
        sess.title = sess.title or self._fallback_title(items)
        if cwd:
            sess.cwd = cwd
        return sess

    def memory_files(self):
        out = []
        con = open_sqlite_ro(self.home / "memories_1.sqlite")
        if con:
            try:
                n = con.execute("SELECT COUNT(*) FROM stage1_outputs").fetchone()[0]
                out.append((self.home / "memories_1.sqlite", f"结构化记忆库（{n} 条）"))
            except Exception:
                pass
            finally:
                con.close()
        for n, desc in (("AGENTS.md", "全局指令"), ("config.toml", "配置")):
            f = self.home / n
            if f.exists():
                out.append((f, desc))
        return out


ADAPTERS = {
    "workbuddy": WorkBuddyAdapter(),
    "claude": ClaudeAdapter(),
    "codex": CodexAdapter(),
}


def resolve_tools(args):
    names = list(TOOLS)
    if getattr(args, "in_tools", None):
        names = [x.strip() for x in args.in_tools.split(",") if x.strip() in TOOLS]
    if getattr(args, "exclude", None):
        drop = {x.strip() for x in args.exclude.split(",")}
        names = [n for n in names if n not in drop]
    return names


# ---------------------------------------------------------------- 命令

def cmd_tools(args):
    print(f"peer-memory {VERSION} 环境自检")
    print("共享目录:", STORE)
    print()
    for n in TOOLS:
        a = ADAPTERS[n]
        ok = a.available()
        n_sess = len(a.sessions()) if ok else 0
        n_mem = len(a.memory_files()) if ok else 0
        print(f"  [{n:9s}] {LABEL[n]:12s} {'可读' if ok else '未找到'}  "
              f"会话 {n_sess:3d}  记忆文件 {n_mem}")
        print(f"              {a.home}")
    return 0


def cmd_timeline(args):
    names = resolve_tools(args)
    days = args.days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    rows = []
    for n in names:
        a = ADAPTERS[n]
        if not a.available():
            continue
        for s in a.sessions(limit=args.limit or 40):
            if cutoff and s.updated and s.updated < cutoff:
                continue
            rows.append(a.hydrate(s))
    rows.sort(key=lambda s: s.updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    rows = rows[: args.limit or 40]
    if args.json:
        print(json.dumps([{
            "tool": s.tool, "session": s.sid, "title": s.title,
            "cwd": s.cwd, "updated": s.updated.isoformat() if s.updated else None,
        } for s in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("没有查到会话。")
        return 0
    cur_day = None
    for s in rows:
        day = fmt_day(s.updated)
        if day != cur_day:
            print(f"\n── {day} " + "─" * 46)
            cur_day = day
        print(f"  [{LABEL[s.tool]:11s}] {fmt_dt(s.updated)}  {s.title or '(无标题)'}")
        print(f"      会话 {s.sid}   {s.cwd}")
    print(f"\n共 {len(rows)} 个会话。展开正文：mem.py show <工具> <会话ID>")
    return 0


def cmd_search(args):
    names = resolve_tools(args)
    kw = args.keyword
    try:
        pat = re.compile(kw, re.I)
    except re.error:
        pat = re.compile(re.escape(kw), re.I)
    full = args.scope == "full"
    hits = []

    for n in names:
        a = ADAPTERS[n]
        if not a.available():
            continue
        for s in a.sessions(limit=args.max_sessions):
            if args.since and s.updated and s.updated.date() < args.since:
                continue
            if args.until and s.updated and s.updated.date() > args.until:
                continue
            try:
                a.hydrate(s)
            except Exception:
                continue
            # 标题命中
            title_hit = bool(s.title and pat.search(s.title))
            matched = []
            if title_hit:
                matched.append(("标题", s.title, s.updated))
            # 正文命中（titles 模式只看用户输入，full 模式看全部）
            try:
                items = a.items(s)
            except Exception:
                items = []
            for it in items:
                if not full and it.role != "user":
                    continue
                if pat.search(it.text):
                    matched.append((("用户" if it.role == "user" else "助手"), it.text, it.ts))
                    if len(matched) >= 4:
                        break
            if matched:
                hits.append((s, matched))

    hits.sort(key=lambda x: x[0].updated or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    hits = hits[: args.limit]

    if args.json:
        print(json.dumps([{
            "tool": s.tool, "session": s.sid, "title": s.title, "cwd": s.cwd,
            "updated": s.updated.isoformat() if s.updated else None,
            "matches": [{"where": w, "text": t, "ts": ts.isoformat() if ts else None}
                        for w, t, ts in m],
        } for s, m in hits], ensure_ascii=False, indent=2))
        return 0

    if not hits:
        print(f'没查到含「{kw}」的记录。')
        print("提示：换更短的关键词，或加 --scope full 连助手回复一起搜。")
        return 0

    total = sum(len(m) for _, m in hits)
    print(f'关键词「{kw}」命中 {len(hits)} 个会话 / {total} 处'
          f'（范围：{"标题+正文" if full else "标题+用户输入"}）\n')
    for s, m in hits:
        print("━" * 62)
        print(f"[{LABEL[s.tool]}] {s.title or '(无标题)'}")
        print(f"  {fmt_day(s.updated)} · 会话 {s.sid}")
        if s.cwd:
            print(f"  目录 {s.cwd}")
        for where, text, ts in m:
            body = text if len(text) <= 400 else text[:400].rstrip() + " …"
            body = body.replace("\n", "\n      ")
            print(f"  · {where}{' ' + fmt_dt(ts) if ts else ''}: {body}")
        print(f"  展开全文：mem.py show {s.tool} {s.sid}")
    return 0


def cmd_show(args):
    tool = args.tool
    if tool not in ADAPTERS:
        print(f"未知工具 {tool}，可选：{', '.join(TOOLS)}", file=sys.stderr)
        return 2
    a = ADAPTERS[tool]
    sess = None
    for s in a.sessions():
        if s.sid == args.session or s.sid.startswith(args.session):
            sess = s
            break
    if not sess:
        print(f"没找到会话 {args.session}", file=sys.stderr)
        return 1
    a.hydrate(sess)
    items = a.items(sess)
    print("━" * 62)
    print(f"[{LABEL[tool]}] {sess.title or '(无标题)'}")
    print(f"  会话 {sess.sid}   {fmt_dt(sess.updated)}   {sess.cwd}")
    print("━" * 62)
    shown = 0
    for it in items:
        if args.limit and shown >= args.limit:
            print(f"  …（已截断，共 {len(items)} 条）")
            break
        who = "用户" if it.role == "user" else "助手"
        text = it.text if len(it.text) <= args.max_chars else it.text[: args.max_chars].rstrip() + " …"
        text = text.replace("\n", "\n    ")
        print(f"\n[{who} {fmt_dt(it.ts)}]")
        print(f"    {text}")
        shown += 1
    return 0


def cmd_memories(args):
    names = resolve_tools(args)
    any_found = False
    for n in names:
        a = ADAPTERS[n]
        if not a.available():
            continue
        files = a.memory_files()
        print(f"\n[{LABEL[n]}]  {a.home}")
        if not files:
            print("  （没有长期记忆文件）")
            continue
        any_found = True
        for f, desc in files:
            try:
                size = f.stat().st_size
            except Exception:
                size = 0
            print(f"  · {desc:16s} {f}  ({size} B)")
            if args.dump and f.suffix == ".md":
                txt = f.read_text(encoding="utf-8", errors="replace")
                print("    " + txt[: args.max_chars].replace("\n", "\n    ") + "\n    …")
    if not any_found:
        print("三家都没有长期记忆文件。")
    print("\n（长期记忆是各家主动沉淀的结论；会话流水用 search / timeline 查）")
    return 0


def cmd_stats(args):
    print(f"{'工具':<12}{'会话数':>7}{'条目数':>9}{'用户输入':>9}{'最早':>13}{'最新':>13}")
    print("-" * 64)
    for n in TOOLS:
        a = ADAPTERS[n]
        if not a.available():
            print(f"{LABEL[n]:<12}{'—':>7}")
            continue
        ss = a.sessions()
        n_item = n_user = 0
        times = []
        for s in ss:
            try:
                its = a.items(s)
            except Exception:
                its = []
            n_item += len(its)
            n_user += sum(1 for i in its if i.role == "user")
            if s.updated:
                times.append(s.updated)
        lo = fmt_day(min(times)) if times else "—"
        hi = fmt_day(max(times)) if times else "—"
        print(f"{LABEL[n]:<12}{len(ss):>7}{n_item:>9}{n_user:>9}{lo:>13}{hi:>13}")
    return 0


# ---------------------------------------------------------------- 入口


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="mem.py",
        description="peer-memory — 跨 AI 工具记忆统一检索引擎（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"peer-memory {VERSION}")
    sub = p.add_subparsers(dest="cmd")

    def add_common(sp):
        sp.add_argument("--in", dest="in_tools", metavar="A,B",
                        help="只查这些工具（workbuddy,claude,codex）")
        sp.add_argument("--exclude", metavar="A,B", help="排除这些工具")
        sp.add_argument("--json", action="store_true", help="输出 JSON")

    sp = sub.add_parser("tools", help="环境自检")
    sp.set_defaults(func=cmd_tools)

    sp = sub.add_parser("timeline", help="最近会话时间线")
    add_common(sp)
    sp.add_argument("--days", type=int, default=None, help="只看最近 N 天")
    sp.add_argument("--limit", type=int, default=40)
    sp.set_defaults(func=cmd_timeline)

    sp = sub.add_parser("search", help="跨工具关键词检索")
    add_common(sp)
    sp.add_argument("keyword")
    sp.add_argument("--scope", choices=("titles", "full"), default="titles",
                    help="titles=标题+用户输入（默认）；full=连助手回复一起搜")
    sp.add_argument("--since", metavar="YYYY-MM-DD")
    sp.add_argument("--until", metavar="YYYY-MM-DD")
    sp.add_argument("--limit", type=int, default=20, help="最多返回 N 个会话")
    sp.add_argument("--max-sessions", type=int, default=300, help="每个工具最多扫描的会话数")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("show", help="展开某个会话的对话正文")
    sp.add_argument("tool", choices=TOOLS)
    sp.add_argument("session")
    sp.add_argument("--limit", type=int, default=60, help="最多显示 N 条消息")
    sp.add_argument("--max-chars", type=int, default=1200, help="单条消息截断长度")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("memories", help="列出各家长期记忆文件")
    add_common(sp)
    sp.add_argument("--dump", action="store_true", help="顺带打印内容开头")
    sp.add_argument("--max-chars", type=int, default=800)
    sp.set_defaults(func=cmd_memories)

    sp = sub.add_parser("stats", help="各家记忆体量统计")
    sp.set_defaults(func=cmd_stats)

    args = p.parse_args(argv)

    # --since/--until 转成 date
    for k in ("since", "until"):
        v = getattr(args, k, None)
        if isinstance(v, str):
            try:
                setattr(args, k, datetime.strptime(v, "%Y-%m-%d").date())
            except Exception:
                setattr(args, k, None)

    if not getattr(args, "func", None):
        p.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
