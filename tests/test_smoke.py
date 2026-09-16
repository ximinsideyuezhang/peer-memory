#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
peer-memory smoke test — 零依赖，只需 Python 3.8+。

  用法:  python3 tests/test_smoke.py

在临时目录里造一份三家的假数据（WorkBuddy / Claude Code / Codex 各一个会话），
然后用 PEER_*_HOME 环境变量把引擎指过去，逐个验证子命令。

不依赖你本机真实的 AI 工具数据，因此在 CI 和陌生机器上都能跑。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENGINE = REPO / "bin" / "mem.py"

WB_UUID = "46e1d602-c5e0-4513-a506-06466ae69fc0"
CL_UUID = "3d009c22-a638-4503-b62f-e1ada7f0a1ff"
CX_UUID = "01a0a8a3-8aa3-7f02-b09a-e8d3fab526d9"


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class PeerMemorySmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENGINE.exists():
            raise unittest.SkipTest(f"engine not found: {ENGINE}")

        cls.tmp = Path(tempfile.mkdtemp(prefix="peer-memory-test-"))
        cls.home = cls.tmp / "home"
        cls.store = cls.tmp / "store"

        cls.wb = cls.home / ".workbuddy"
        cls.cl = cls.home / ".claude"
        cls.cx = cls.home / ".codex"

        cls._make_workbuddy()
        cls._make_claude()
        cls._make_codex()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 造数据

    @classmethod
    def _make_workbuddy(cls):
        proj = cls.wb / "projects" / "c-Users-test-proj-demo"
        write_jsonl(proj / f"{WB_UUID}.jsonl", [
            {"type": "ai-title", "aiTitle": "对码搜索平台架构评审"},
            {"type": "message", "role": "user", "cwd": "C:\\proj\\demo",
             "timestamp": 1758000000000,
             "content": [{"type": "input_text",
                          "text": "<system-reminder>ignore me</system-reminder>"
                                  "帮我看看布隆过滤器的方案"}]},
            {"type": "message", "role": "assistant", "cwd": "C:\\proj\\demo",
             "timestamp": 1758000010000,
             "content": [{"type": "output_text",
                          "text": "建议用 RedisBloom 承接商品 ID 存在性判断。"}]},
        ])
        # 无 ai-title 的会话：标题走回退逻辑，且首条 user 消息带注入前缀
        write_jsonl(proj / "aaaaaaaa-0000-0000-0000-000000000001.jsonl", [
            {"type": "message", "role": "user", "cwd": "C:\\proj\\demo",
             "timestamp": 1758001000000,
             "content": [{"type": "input_text",
                          "text": "<system-reminder>x</system-reminder>\n"
                                  "缓存分层的降级策略怎么设计"}]},
        ])
        (cls.wb / "memory").mkdir(parents=True, exist_ok=True)
        (cls.wb / "memory" / "abc_memory.md").write_text(
            "# 用户画像\n偏好先看架构再拆细节。\n", encoding="utf-8")
        (cls.wb / "USER.md").write_text("# USER\n", encoding="utf-8")

    @classmethod
    def _make_claude(cls):
        proj = cls.cl / "projects" / "D--proj-wm"
        write_jsonl(proj / f"{CL_UUID}.jsonl", [
            {"type": "ai-title", "aiTitle": "Java 21 集合接口升级"},
            {"type": "user", "cwd": "D:\\proj\\wm",
             "timestamp": "2026-09-16T10:00:00.000Z",
             "message": {"role": "user", "content": [
                 {"type": "text", "text": "Java 21 SequencedCollection getFirst 怎么用"}]}},
            {"type": "assistant", "cwd": "D:\\proj\\wm",
             "timestamp": "2026-09-16T10:00:05.000Z",
             "message": {"role": "assistant", "content": [
                 {"type": "text", "text": "用 getFirst() 替换 get(0)，语义更清晰。"}]}},
            # tool_result 不该进检索语料
            {"type": "user", "cwd": "D:\\proj\\wm",
             "timestamp": "2026-09-16T10:00:06.000Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "content": "SHOULD_NOT_APPEAR_TOOLRESULT"}]}},
            # 技能注入不该被当成用户说的话
            {"type": "user", "cwd": "D:\\proj\\wm",
             "timestamp": "2026-09-16T10:00:07.000Z",
             "message": {"role": "user",
                         "content": "Base directory for this skill: /tmp/skills"}},
        ])
        (cls.cl / "CLAUDE.md").write_text("# 全局记忆\n", encoding="utf-8")

    @classmethod
    def _make_codex(cls):
        day = cls.cx / "sessions" / "2026" / "09" / "16"
        write_jsonl(day / f"rollout-2026-09-16T10-27-33-{CX_UUID}.jsonl", [
            {"type": "session_meta", "payload": {"cwd": "C:\\proj\\codex-demo"}},
            # developer 角色是提示注入
            {"type": "response_item",
             "payload": {"type": "message", "role": "developer", "content": [
                 {"type": "input_text", "text": "SHOULD_NOT_APPEAR_DEVELOPER"}]}},
            {"type": "response_item",
             "payload": {"type": "message", "role": "user", "content": [
                 {"type": "input_text", "text": "Codex 这边怎么配置 Dubbo 消费者"}]},
             "timestamp": "2026-09-16T10:27:35.000Z"},
            {"type": "response_item",
             "payload": {"type": "message", "role": "assistant", "content": [
                 {"type": "output_text",
                  "text": "用 dubbo-spring-boot-starter，配好注册中心即可。"}]},
             "timestamp": "2026-09-16T10:27:40.000Z"},
        ])
        # 标题索引：注意纳秒精度
        write_jsonl(cls.cx / "session_index.jsonl", [
            {"id": CX_UUID, "thread_name": "Dubbo 微服务接入",
             "updated_at": "2026-09-16T10:28:00.1234567Z"},
        ])
        (cls.cx / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

    # ------------------------------------------------------------ 跑引擎

    def run_engine(self, *args):
        env = dict(os.environ)
        env.update({
            "PEER_MEMORY_HOME": str(self.store),
            "PEER_WORKBUDDY_HOME": str(self.wb),
            "PEER_CLAUDE_HOME": str(self.cl),
            "PEER_CODEX_HOME": str(self.cx),
            "PYTHONIOENCODING": "utf-8",
        })
        p = subprocess.run(
            [sys.executable, str(ENGINE), *args],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env,
        )
        return p.returncode, (p.stdout or ""), (p.stderr or "")

    # ------------------------------------------------------------ 用例

    def test_01_tools_detects_all_three(self):
        code, out, err = self.run_engine("tools")
        self.assertEqual(code, 0, err)
        for label in ("WorkBuddy", "Claude Code", "Codex"):
            self.assertIn(label, out)
        self.assertEqual(out.count("可读"), 3, out)

    def test_02_timeline_uses_real_titles(self):
        code, out, err = self.run_engine("timeline", "--limit", "20")
        self.assertEqual(code, 0, err)
        self.assertIn("对码搜索平台架构评审", out)
        self.assertIn("Java 21 集合接口升级", out)
        self.assertIn("Dubbo 微服务接入", out)
        # 无 ai-title 的会话应回退到清洗后的首条用户输入
        self.assertIn("缓存分层的降级策略", out)

    def test_03_search_titles_scope_is_clean(self):
        code, out, err = self.run_engine("search", "布隆过滤器", "--limit", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("布隆过滤器", out)
        # titles 模式不扫助手回复，所以助手那句里的 RedisBloom 不该出现
        self.assertNotIn("RedisBloom", out)
        # 注入块必须已被剥离
        self.assertNotIn("system-reminder", out)
        self.assertNotIn("ignore me", out)

    def test_04_search_full_scope_reaches_assistant_replies(self):
        code, out, err = self.run_engine(
            "search", "RedisBloom", "--scope", "full", "--limit", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("RedisBloom", out)

    def test_05_exclude_filters_a_tool(self):
        code, out, err = self.run_engine(
            "search", "e", "--exclude", "workbuddy", "--limit", "20")
        self.assertEqual(code, 0, err)
        self.assertNotIn("WorkBuddy", out)
        self.assertIn("Claude Code", out)

    def test_06_show_expands_session(self):
        code, out, err = self.run_engine("show", "claude", CL_UUID[:8])
        self.assertEqual(code, 0, err)
        self.assertIn("getFirst", out)
        self.assertIn("用 getFirst() 替换 get(0)", out)
        # tool_result 与技能注入都要被过滤
        self.assertNotIn("SHOULD_NOT_APPEAR_TOOLRESULT", out)
        self.assertNotIn("Base directory for this skill", out)

    def test_07_codex_skips_developer_role(self):
        code, out, err = self.run_engine(
            "search", "SHOULD_NOT_APPEAR_DEVELOPER", "--scope", "full")
        self.assertEqual(code, 0, err)
        self.assertIn("没查到", out)

    def test_08_memories_lists_files(self):
        code, out, err = self.run_engine("memories", "--dump")
        self.assertEqual(code, 0, err)
        self.assertIn("abc_memory.md", out)
        self.assertIn("CLAUDE.md", out)
        self.assertIn("AGENTS.md", out)
        self.assertIn("偏好先看架构再拆细节", out)

    def test_09_stats_runs(self):
        code, out, err = self.run_engine("stats")
        self.assertEqual(code, 0, err)
        self.assertIn("WorkBuddy", out)
        self.assertIn("Claude Code", out)

    def test_10_version_flag(self):
        code, out, err = self.run_engine("--version")
        self.assertEqual(code, 0, err)
        self.assertIn("peer-memory", out)

    def test_11_json_output_is_parseable(self):
        code, out, err = self.run_engine("search", "Dubbo", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertTrue(isinstance(data, list) and data, out)
        self.assertEqual(data[0]["tool"], "codex")

    def test_12_unknown_home_is_not_fatal(self):
        env = dict(os.environ)
        env["PEER_WORKBUDDY_HOME"] = str(self.tmp / "nope")
        env["PYTHONIOENCODING"] = "utf-8"
        p = subprocess.run(
            [sys.executable, str(ENGINE), "timeline"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_13_launcher_rejects_a_broken_interpreter(self):
        """启动器的核心逻辑：只接受真能跑通的解释器。

        回归测试——Windows 上 python.exe 可能是个 0 字节存根，
        任何"找到就用"的实现都会栽在这里。

        把 PATH 和 HOME 都隔离掉，确保除了那个假解释器之外
        启动器找不到任何别的候选，这样才测得到"拒绝"这条路径。
        """
        launcher = REPO / "bin" / "mem.sh"
        if not launcher.exists():
            self.skipTest("mem.sh not present")
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("sh not available")

        # 一个存在、可执行，但一跑就失败的假解释器
        fake = self.tmp / "fake-python"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(0o755)

        empty_path = self.tmp / "empty-path"
        empty_home = self.tmp / "empty-home"
        empty_path.mkdir(exist_ok=True)
        empty_home.mkdir(exist_ok=True)

        env = dict(os.environ)
        env["PEER_PYTHON"] = str(fake)
        env["PATH"] = str(empty_path)
        env["HOME"] = str(empty_home)
        env["PYTHONIOENCODING"] = "utf-8"

        # Run it the way a real user does — `sh bin/mem.sh` from the repo root,
        # so $0 is a POSIX relative path and nothing depends on the host PATH.
        p = subprocess.run(
            [sh, "bin/mem.sh", "tools"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=str(REPO))
        self.assertEqual(p.returncode, 127,
                         f"expected the launcher to reject it\n{p.stdout}\n{p.stderr}")
        self.assertIn("No working Python 3 interpreter", p.stderr)

    def test_14_launcher_accepts_a_working_interpreter(self):
        launcher = REPO / "bin" / "mem.sh"
        sh = shutil.which("sh")
        if not launcher.exists() or not sh:
            self.skipTest("requires sh and bin/mem.sh")

        env = dict(os.environ)
        env.update({
            "PEER_PYTHON": sys.executable,
            "PEER_MEMORY_HOME": str(self.store),
            "PEER_WORKBUDDY_HOME": str(self.wb),
            "PEER_CLAUDE_HOME": str(self.cl),
            "PEER_CODEX_HOME": str(self.cx),
            "PYTHONIOENCODING": "utf-8",
        })
        p = subprocess.run(
            [sh, "bin/mem.sh", "tools"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, cwd=str(REPO))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("WorkBuddy", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
