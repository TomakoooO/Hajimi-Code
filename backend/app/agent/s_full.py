#!/usr/bin/env python3
# Harness: all mechanisms combined -- the complete cockpit for the model.
"""
s_full.py - Full Reference Agent

Capstone implementation combining every mechanism from s01-s11.
Session s12 (task-aware worktree isolation) is taught separately.
NOT a teaching session -- this is the "put it all together" reference.

    +------------------------------------------------------------------+
    |                        FULL AGENT                                 |
    |                                                                   |
    |  System prompt (s05 skills, task-first + optional todo nag)      |
    |                                                                   |
    |  Before each LLM call:                                            |
    |  +--------------------+  +------------------+  +--------------+  |
    |  | Microcompact (s06) |  | Drain bg (s08)   |  | Check inbox  |  |
    |  | Auto-compact (s06) |  | notifications    |  | (s09)        |  |
    |  +--------------------+  +------------------+  +--------------+  |
    |                                                                   |
    |  Tool dispatch (s02 pattern):                                     |
    |  +--------+----------+----------+---------+-----------+          |
    |  | bash   | read     | write    | edit    | TodoWrite |          |
    |  | task   | load_sk  | compress | bg_run  | bg_check  |          |
    |  | t_crt  | t_get    | t_upd    | t_list  | spawn_tm  |          |
    |  | list_tm| send_msg | rd_inbox | bcast   | shutdown  |          |
    |  | plan   | idle     | claim    |         |           |          |
    |  +--------+----------+----------+---------+-----------+          |
    |                                                                   |
    |  Subagent (s04):  spawn -> work -> return summary                 |
    |  Teammate (s09):  spawn -> work -> idle -> auto-claim (s11)      |
    |  Shutdown (s10):  request_id handshake                            |
    |  Plan gate (s10): submit -> approve/reject                        |
    +------------------------------------------------------------------+

    REPL commands: /compact /tasks /team /inbox /remember <rule>
"""

import abc
import json
import logging
import os
import platform
import re
import shlex
import sqlite3
import subprocess
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue

from anthropic import Anthropic
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is in sys.path when running as a script
if __name__ == "__main__":
    backend_dir = str(Path(__file__).resolve().parents[2])
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.services.timeline_store import timeline_store

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path, override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path(settings.workspace_root).resolve()

def get_client():
    return Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))

def get_model():
    return os.getenv("MODEL_ID", "deepseek-chat")


def get_model_context_window() -> int:
    model = get_model().lower()
    # DeepSeek officially states that both deepseek-v4-flash and deepseek-v4-pro
    # support a 1M-token context window, and deepseek-chat is a compatibility alias
    # for deepseek-v4-flash non-thinking mode.
    if model in ("deepseek-chat", "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner"):
        return DEFAULT_CONTEXT_WINDOW
    return DEFAULT_CONTEXT_WINDOW


def get_compaction_trigger_threshold() -> int:
    return max(1, get_model_context_window() - CONTEXT_BUFFER_TOKENS)

AGENT_DIR = Path(__file__).resolve().parent
APP_DIR = Path(__file__).resolve().parents[1]
PROMPT_DIR = AGENT_DIR / "Prompt"

TEAM_DIR = WORKDIR / ".team"
INBOX_DIR = TEAM_DIR = WORKDIR / ".team"
TASKS_DIR = WORKDIR / ".tasks"
SKILLS_DIR = APP_DIR / "skills"
TRANSCRIPT_DIR = WORKDIR / ".transcripts"
SANDBOX_DIR = WORKDIR / ".sandbox"
DEFAULT_CONTEXT_WINDOW = 1_000_000
CONTEXT_BUFFER_TOKENS = 20_000
MICROCOMPACT_PLACEHOLDER = "[Old tool result content cleared]"
SUMMARY_AGENT_TYPE = "CompactSummary"
POLL_INTERVAL = 5
IDLE_TIMEOUT = 60

VALID_MSG_TYPES = {"message", "broadcast", "shutdown_request",
                   "shutdown_response", "plan_approval_response"}
ACTIVE_REQUEST_ID: ContextVar[str | None] = ContextVar("ACTIVE_REQUEST_ID", default=None)
DEFAULT_TEAMMATES = [
    {
        "name": "researcher",
        "role": "文件分析/研究专家",
        "status": "idle",
        "responsibility": "宏观代码分析：结构、模块边界、数据流、整体设计总结",
        "when_to_spawn": "当任务需要快速理解大文件、系统架构或功能分层时",
        "prompt_template": "阅读相关文件，重点总结结构、模块职责、调用链和研究价值点，只返回精炼结论给 lead。",
    },
    {
        "name": "backend-analyst",
        "role": "后端代码分析师",
        "status": "idle",
        "responsibility": "微观代码审查：代码质量、安全性、性能、架构评估与优化建议",
        "when_to_spawn": "当任务需要后端实现细节、风险评估、安全或性能审查时",
        "prompt_template": "聚焦实现细节、潜在 bug、安全与性能问题，给出针对性的技术结论和改进建议。",
    },
    {
        "name": "tester",
        "role": "QA Engineer",
        "status": "idle",
        "responsibility": "测试分析：边界条件、异常路径、输入校验、单元测试覆盖",
        "when_to_spawn": "当任务需要补测试、做回归检查、验证边界或异常路径时",
        "prompt_template": "从测试视角审视代码，识别边界条件、失败场景和可补充的测试用例。",
    },
]


def publish_timeline(request_id: str | None, actor: str, event: str, payload: dict | None = None) -> None:
    if request_id:
        timeline_store.publish(request_id, actor, event, payload)


def _clone_default_teammates() -> list[dict]:
    return [dict(item) for item in DEFAULT_TEAMMATES]


def read_workspace_doc(name: str, fallback: str = "(empty)") -> str:
    path = WORKDIR / name
    if not path.exists():
        return fallback
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as e:
        return f"[{name} load error: {e}]"
    return text[:12000] if text else fallback


def load_prompt_template(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template missing: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def append_agent_rule(rule: str) -> str:
    text = rule.strip()
    if not text:
        return "Error: /remember requires non-empty rule text."
    path = WORKDIR / "AGENT.MD"
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace").rstrip()
        if current:
            updated = f"{current}\n- {text}\n"
        else:
            updated = f"# AGENT Rules\n\n- {text}\n"
    else:
        updated = f"# AGENT Rules\n\n- {text}\n"
    path.write_text(updated, encoding="utf-8")
    return f"Remembered rule in {path.name}: {text}"


def remember_user_rule(rule: str) -> str:
    return append_agent_rule(rule)


def render_teammate_roster(members: list[dict]) -> str:
    if not members:
        return "No preconfigured teammates."
    lines = []
    for member in members:
        name = member.get("name", "unknown")
        role = member.get("role", "unknown")
        responsibility = member.get("responsibility", "")
        when_to_spawn = member.get("when_to_spawn", "")
        lines.append(f"- {name} ({role})")
        if responsibility:
            lines.append(f"  responsibility: {responsibility}")
        if when_to_spawn:
            lines.append(f"  when_to_spawn: {when_to_spawn}")
    return "\n".join(lines)


def _render_prompt_layer(name: str, values: dict[str, str]) -> str:
    return load_prompt_template(name).format_map(values)


def build_system_prompt(
    skills_desc: str,
    team_config: dict | None = None,
    *,
    agent_kind: str = "lead",
    role_name: str = "",
    role_desc: str = "",
    tool_names: list[str] | None = None,
    role_mode_notes: str = "",
) -> str:
    team_config = team_config or {"team_name": "default", "members": _clone_default_teammates()}
    tool_names = tool_names or []
    team_name = team_config.get("team_name", "default")
    teammate_text = render_teammate_roster(team_config.get("members", []))
    if agent_kind == "lead":
        role_mode = (
            "You are the main agent. Understand the user's request, decide whether to solve it directly, "
            "delegate to a subagent, or spawn a teammate, then integrate the final result.\n"
            f"Team name: {team_name}\nPreconfigured teammates:\n{teammate_text}"
        )
    elif agent_kind == "subagent":
        role_mode = (
            "You are a subagent working in isolated context. Focus only on the assigned subtask, "
            "return a concise summary to the main agent, and do not expand scope on your own."
        )
    else:
        role_mode = (
            f"You are teammate '{role_name}'. Your responsibility is '{role_desc}'. "
            "Coordinate with the main agent via messages, work in the background, and report progress or findings back."
        )
    if role_mode_notes:
        role_mode = f"{role_mode}\n{role_mode_notes}"

    values = {
        "identity_name": "hajime-code",
        "identity_summary": "a code agent that reads code, reasons about tasks, uses tools, edits files, and collaborates with subagents or teammates when needed.",
        "workspace_root": str(WORKDIR),
        "current_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "project_language": "python",
        "hajimi_md": read_workspace_doc("Hajimi.MD"),
        "agent_md": read_workspace_doc("AGENT.MD"),
        "agent_kind": agent_kind,
        "role_mode": role_mode,
        "tool_names": ", ".join(tool_names) if tool_names else "(no tools)",
        "skills_desc": skills_desc or "(no skills loaded)",
    }
    layers = [
        _render_prompt_layer("01_base_identity.md", values),
        _render_prompt_layer("02_runtime_injection.md", values),
        _render_prompt_layer("03_user_rules.md", values),
        _render_prompt_layer("04_role_mode.md", values),
        _render_prompt_layer("05_tools_backend.md", values),
    ]
    return "\n\n".join(layer.strip() for layer in layers if layer.strip())

def switch_workspace_root(path: str) -> str:
    global WORKDIR, TEAM_DIR, INBOX_DIR, TASKS_DIR, SKILLS_DIR, TRANSCRIPT_DIR, SANDBOX_DIR, SYSTEM
    global TODO, SKILLS, TASK_MGR, BG, BUS, TEAM, SANDBOX
    global shutdown_requests, plan_requests

    next_root = Path(path).resolve()
    if not next_root.exists() or not next_root.is_dir():
        raise ValueError(f"workspace path invalid: {next_root}")

    WORKDIR = next_root
    TEAM_DIR = WORKDIR / ".team"
    INBOX_DIR = TEAM_DIR = WORKDIR / ".team"
    TASKS_DIR = WORKDIR / ".tasks"
    SKILLS_DIR = APP_DIR / "skills"
    TRANSCRIPT_DIR = WORKDIR / ".transcripts"
    SANDBOX_DIR = WORKDIR / ".sandbox"

    global TodoManager, SkillLoader, TaskManager, BackgroundManager, MessageBus, TeammateManager
    
    TODO = TodoManager()
    SKILLS = SkillLoader(SKILLS_DIR)
    TASK_MGR = TaskManager()
    SANDBOX = create_sandbox_runner()
    BG = BackgroundManager()
    BUS = MessageBus()
    TEAM = TeammateManager(BUS, TASK_MGR)
    shutdown_requests = {}
    plan_requests = {}
    lead_tools = [tool["name"] for tool in TOOLS] if "TOOLS" in globals() else []
    SYSTEM = build_system_prompt(
        SKILLS.descriptions(),
        TEAM.config,
        agent_kind="lead",
        tool_names=lead_tools,
    )
    return str(WORKDIR)


# === SECTION: base_tools ===
# 路径安全校验（防止逃逸工作空间）
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _decode_process_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# === SECTION: sandbox runner interface + implementations (2.9 Phase 3) ===

class ISandboxRunner(abc.ABC):
    """Abstract sandbox runner interface — supports multiple backends."""
    @abc.abstractmethod
    def run(self, command: str, timeout: int = 120) -> str:
        ...

    @abc.abstractmethod
    def classify(self, argv: list[str]) -> str:
        ...


@dataclass
class NetworkPolicy:
    """Network allowlist / proxy policy layer (Phase 3 reserved)."""
    allow_hosts: tuple[str, ...] = ()
    deny_hosts: tuple[str, ...] = ()
    proxy_url: str = ""
    enforce: bool = False  # set True to actually block non-allowlisted hosts


class SandboxRunner(ISandboxRunner):
    BLOCKED_PATTERNS = [
        r"&&", r"\|\|", r"\|", r">", r"<",
        r"\bsudo\b", r"\bshutdown\b", r"\breboot\b",
        r"\bRemove-Item\b", r"\bInvoke-Expression\b", r"\biex\b",
        r"\bcurl\b", r"\bwget\b",
    ]
    COMMAND_RULES = {
        "python": "workspace_write",
        "pytest": "workspace_write",
        "py": "workspace_write",
        "pip": "read_only",
        "uv": "workspace_write",
        "git": "read_only",
        "node": "workspace_write",
        "npm": "workspace_write",
        "pnpm": "workspace_write",
        "yarn": "workspace_write",
        "where": "read_only",
    }
    GIT_READ_ONLY_SUBCOMMANDS = {"status", "diff", "log", "show", "grep", "ls-files", "rev-parse"}
    PYTHON_BLOCKED_FLAGS = {"-c", "-m", "-"}
    PACKAGE_INSTALL_SUBCOMMANDS = {"install", "add", "create", "dlx", "remove", "uninstall"}

    def __init__(self):
        self.restricted_user = os.getenv("HAJIMI_SANDBOX_USER", "").strip()
        self.network_policy = NetworkPolicy()

    def classify(self, argv: list[str]) -> str:
        """Public classify — delegates to _classify."""
        return self._classify(argv)

    def _classify(self, argv: list[str]) -> str:
        if not argv:
            raise ValueError("Empty command")
        command = argv[0]
        risk = self.COMMAND_RULES.get(command)
        if not risk:
            raise ValueError(f"Command not allowed in sandbox: {command}")
        if command == "git":
            if len(argv) < 2 or argv[1] not in self.GIT_READ_ONLY_SUBCOMMANDS:
                raise ValueError("Only read-only git subcommands are allowed in sandbox")
        if command in {"python", "py"}:
            if len(argv) >= 2 and argv[1] in self.PYTHON_BLOCKED_FLAGS:
                raise ValueError("Inline python execution is blocked in sandbox")
        if command in {"npm", "pnpm", "yarn"}:
            if len(argv) >= 2 and argv[1] in self.PACKAGE_INSTALL_SUBCOMMANDS:
                raise ValueError("Package installation commands are blocked in sandbox")
        if command == "pip":
            if len(argv) < 2 or argv[1] not in {"list", "show"}:
                raise ValueError("Only read-only pip commands are allowed in sandbox")
        if command == "uv":
            if len(argv) >= 2 and argv[1] in {"pip", "tool", "venv", "sync", "add", "remove"}:
                raise ValueError("Environment-mutating uv commands are blocked in sandbox")
        return risk

    def _run_restricted(self, argv: list[str], timeout: int) -> subprocess.CompletedProcess:
        """
        Execute a command under the restricted user account.

        Implementation per platform:
        - Windows: uses ctypes + advapi32.LogonUserW / CreateProcessAsUserW
                  (requires the restricted user's token).
        - POSIX:   uses preexec_fn with os.setuid / os.setgid.
        """
        user = self.restricted_user
        if not user:
            return subprocess.run(
                argv,
                cwd=WORKDIR,
                env=self._build_env(),
                capture_output=True,
                timeout=timeout,
                shell=False,
            )

        system = platform.system()
        if system == "Windows":
            return self._run_restricted_windows(argv, user, timeout)
        else:
            return self._run_restricted_posix(argv, user, timeout)

    def _run_restricted_windows(
        self, argv: list[str], user: str, timeout: int
    ) -> subprocess.CompletedProcess:
        """
        Windows restricted execution via LogonUserW + CreateProcessAsUserW.

        Uses LOGON32_LOGON_NEW_CREDENTIALS so the target user does NOT
        need an interactive session.  Falls back to normal execution with
        a warning if the API call fails (e.g. user does not exist).
        """
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            logger.warning("ctypes not available — falling back to normal execution")
            return subprocess.run(
                argv, cwd=WORKDIR, env=self._build_env(),
                capture_output=True, timeout=timeout, shell=False,
            )

        try:
            advapi32 = ctypes.windll.advapi32
        except AttributeError:
            logger.warning("Not on Windows — falling back to normal execution")
            return subprocess.run(
                argv, cwd=WORKDIR, env=self._build_env(),
                capture_output=True, timeout=timeout, shell=False,
            )

        LOGON32_LOGON_NEW_CREDENTIALS = 9
        LOGON32_PROVIDER_DEFAULT = 0
        TOKEN_ALL_ACCESS = 0xF01FF
        CREATE_NO_WINDOW = 0x08000000
        NORMAL_PRIORITY_CLASS = 0x0020

        token = wintypes.HANDLE()
        parts = user.split("\\", 1)
        if len(parts) == 2:
            domain, name = parts
        elif "." in user:
            domain, name = ".", user
        else:
            domain, name = None, user

        success = advapi32.LogonUserW(
            name,
            domain,
            "",  # empty password — relies on the account being password-less / managed
            LOGON32_LOGON_NEW_CREDENTIALS,
            LOGON32_PROVIDER_DEFAULT,
            ctypes.byref(token),
        )
        if not success:
            err = ctypes.GetLastError()
            logger.warning(
                "LogonUserW(%s) failed (GLE=%d) — falling back to normal execution", user, err
            )
            return subprocess.run(
                argv, cwd=WORKDIR, env=self._build_env(),
                capture_output=True, timeout=timeout, shell=False,
            )

        try:
            # Duplicate token as primary
            primary_token = wintypes.HANDLE()
            success = advapi32.DuplicateTokenEx(
                token,
                TOKEN_ALL_ACCESS,
                None,
                2,  # SecurityImpersonation
                1,  # TokenPrimary
                ctypes.byref(primary_token),
            )
            if not success:
                err = ctypes.GetLastError()
                raise OSError(f"DuplicateTokenEx failed: GLE={err}")

            cmdline = subprocess.list2cmdline(argv)
            si = subprocess.STARTUPINFO()
            si.cb = ctypes.sizeof(si)
            si.dwFlags = 1  # STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE

            proc_info = (wintypes.HANDLE * 4)()

            success = advapi32.CreateProcessAsUserW(
                primary_token,
                None,  # use command line
                ctypes.create_unicode_buffer(cmdline),
                None,  # process attributes
                None,  # thread attributes
                False,  # inherit handles
                NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW,
                None,  # environment
                str(WORKDIR),
                ctypes.byref(si),
                proc_info,
            )
            if not success:
                err = ctypes.GetLastError()
                raise OSError(f"CreateProcessAsUserW failed: GLE={err}")

            proc_handle, thread_handle = proc_info[0], proc_info[1]
            kernel32 = ctypes.windll.kernel32
            ms = (timeout or 120) * 1000
            ret = kernel32.WaitForSingleObject(proc_handle, ms)
            if ret != 0:  # WAIT_OBJECT_0
                kernel32.TerminateProcess(proc_handle, 1)
                raise subprocess.TimeoutExpired(argv, timeout)

            exit_code = wintypes.DWORD()
            kernel32.GetExitCodeProcess(proc_handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(proc_handle)
            kernel32.CloseHandle(thread_handle)

            # Build a CompletedProcess-like dataclass
            result = subprocess.CompletedProcess(argv, exit_code.value, b"(restricted)", b"")
            return result
        except Exception as e:
            logger.warning("Restricted Windows execution failed: %s — falling back", e)
            return subprocess.run(
                argv, cwd=WORKDIR, env=self._build_env(),
                capture_output=True, timeout=timeout, shell=False,
            )
        finally:
            kernel32 = ctypes.windll.kernel32
            if token:
                kernel32.CloseHandle(token)

    def _run_restricted_posix(
        self, argv: list[str], user: str, timeout: int
    ) -> subprocess.CompletedProcess:
        """POSIX restricted execution via preexec_fn + setuid/setgid."""
        try:
            import pwd
            import grp
            pw = pwd.getpwnam(user)
            uid = pw.pw_uid
            gid = pw.pw_gid
            groups = [g.gr_gid for g in grp.getgrall() if user in g.gr_mem]
        except (ImportError, KeyError) as e:
            logger.warning("Cannot resolve user %s — %s — falling back", user, e)
            return subprocess.run(
                argv, cwd=WORKDIR, env=self._build_env(),
                capture_output=True, timeout=timeout, shell=False,
            )

        def _drop_privs():
            os.setgid(gid)
            if groups:
                os.setgroups(groups)
            os.setuid(uid)

        return subprocess.run(
            argv,
            cwd=WORKDIR,
            env=self._build_env(),
            capture_output=True,
            timeout=timeout,
            shell=False,
            preexec_fn=_drop_privs,
        )

    def _validate_command(self, command: str) -> list[str]:
        text = command.strip()
        if not text:
            raise ValueError("Empty command")
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                raise ValueError("Blocked shell syntax or dangerous command pattern")
        try:
            argv = shlex.split(text, posix=False)
        except ValueError as e:
            raise ValueError(f"Command parse error: {e}") from e
        self._classify(argv)
        return argv

    def _build_env(self) -> dict[str, str]:
        sandbox_home = SANDBOX_DIR / "home"
        sandbox_tmp = SANDBOX_DIR / "tmp"
        sandbox_cache = SANDBOX_DIR / "cache"
        for path in (SANDBOX_DIR, sandbox_home, sandbox_tmp, sandbox_cache):
            path.mkdir(parents=True, exist_ok=True)
        keep_keys = [
            "PATH", "SystemRoot", "ComSpec", "PATHEXT",
            "PYTHONIOENCODING", "PYTHONUTF8",
        ]
        env = {k: v for k, v in os.environ.items() if k in keep_keys and v}
        env["HAJIMI_WORKDIR"] = str(WORKDIR)
        env["HOME"] = str(sandbox_home)
        env["USERPROFILE"] = str(sandbox_home)
        env["TMP"] = str(sandbox_tmp)
        env["TEMP"] = str(sandbox_tmp)
        env["PIP_CACHE_DIR"] = str(sandbox_cache / "pip")
        env["npm_config_cache"] = str(sandbox_cache / "npm")
        env["YARN_CACHE_FOLDER"] = str(sandbox_cache / "yarn")
        return env

    def _append_audit(self, command: str, status: str, detail: str, risk: str = "unknown") -> None:
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "command": command,
            "status": status,
            "risk": risk,
            "detail": detail[:500],
        }
        with (SANDBOX_DIR / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def run(self, command: str, timeout: int = 120) -> str:
        try:
            argv = self._validate_command(command)
            risk = self._classify(argv)
            if self.restricted_user:
                r = self._run_restricted(argv, timeout)
            else:
                r = subprocess.run(
                    argv,
                    cwd=WORKDIR,
                    env=self._build_env(),
                    capture_output=True,
                    timeout=timeout,
                    shell=False,
                )
            stdout = _decode_process_output(r.stdout)
            stderr = _decode_process_output(r.stderr)
            out = (stdout + stderr).strip()
            prefix = f"[sandbox risk={risk}]"
            if self.restricted_user:
                prefix += f"[restricted_user={self.restricted_user}]"
            result = f"{prefix}\n{out[:50000]}" if out else f"{prefix}\n(no output)"
            self._append_audit(command, "completed", out or "(no output)", risk)
            return result
        except subprocess.TimeoutExpired:
            self._append_audit(command, "timeout", f"Timeout after {timeout}s")
            return f"Error: Sandbox timeout ({timeout}s)"
        except Exception as e:
            self._append_audit(command, "blocked", str(e))
            return f"Error: Sandbox execution failed: {e}"


class ContainerSandboxRunner(ISandboxRunner):
    """
    Placeholder / stub for containerized sandbox execution (Phase 3).

    When implemented, this runner will:
    - Launch commands inside a Docker / Podman / OCI container
    - Enforce filesystem & network boundaries outside the Python process
    - Support configurable images, mounts, and network policies
    """
    def __init__(self, image: str = "python:3.12-slim",
                 network_policy: NetworkPolicy | None = None):
        self.image = image
        self.network_policy = network_policy or NetworkPolicy()

    def run(self, command: str, timeout: int = 120) -> str:
        raise NotImplementedError(
            "ContainerSandboxRunner is not yet implemented. "
            "Set HAJIMI_SANDBOX_MODE=local or implement the runner."
        )

    def classify(self, argv: list[str]) -> str:
        return "blocked"  # safest default for an unimplemented backend


def create_sandbox_runner() -> ISandboxRunner:
    """Factory: returns the appropriate sandbox runner based on env config."""
    mode = os.getenv("HAJIMI_SANDBOX_MODE", "local").strip().lower()
    if mode == "container":
        image = os.getenv("HAJIMI_SANDBOX_IMAGE", "python:3.12-slim")
        network_policy = NetworkPolicy(
            allow_hosts=tuple(os.getenv("HAJIMI_NETWORK_ALLOW", "").split(",")) if os.getenv("HAJIMI_NETWORK_ALLOW") else (),
            deny_hosts=tuple(os.getenv("HAJIMI_NETWORK_DENY", "").split(",")) if os.getenv("HAJIMI_NETWORK_DENY") else (),
            proxy_url=os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", "")),
            enforce=os.getenv("HAJIMI_NETWORK_ENFORCE", "").lower() in ("1", "true", "yes"),
        )
        return ContainerSandboxRunner(image=image, network_policy=network_policy)
    # Default: local sandbox runner with all Phase 1+2 hardening
    runner = SandboxRunner()
    policy = NetworkPolicy(
        allow_hosts=tuple(os.getenv("HAJIMI_NETWORK_ALLOW", "").split(",")) if os.getenv("HAJIMI_NETWORK_ALLOW") else (),
        deny_hosts=tuple(os.getenv("HAJIMI_NETWORK_DENY", "").split(",")) if os.getenv("HAJIMI_NETWORK_DENY") else (),
        proxy_url=os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", "")),
        enforce=os.getenv("HAJIMI_NETWORK_ENFORCE", "").lower() in ("1", "true", "yes"),
    )
    runner.network_policy = policy
    return runner


SANDBOX = create_sandbox_runner()


def run_bash(command: str) -> str:
    return SANDBOX.run(command, timeout=120)
# run_read/run_write：读写文件（支持行数限制）
def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"
#run_edit：精准替换文件内容（需匹配旧文本）
def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# todo列表 一个对话期间的短期人物列表
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        validated, ip = [], 0
        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            af = str(item.get("activeForm", "")).strip()
            if not content: raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not af: raise ValueError(f"Item {i}: activeForm required")
            if status == "in_progress": ip += 1
            validated.append({"content": content, "status": status, "activeForm": af})
        if len(validated) > 20: raise ValueError("Max 20 todos")
        if ip > 1: raise ValueError("Only one in_progress allowed")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items: return "No todos."
        lines = []
        for item in self.items:
            m = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(item["status"], "[?]")
            suffix = f" <- {item['activeForm']}" if item["status"] == "in_progress" else ""
            lines.append(f"{m} {item['content']}{suffix}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        return any(item.get("status") != "completed" for item in self.items)


# === SECTION: subagent (s04) ===
# 子agent的可调用工具有限 不能递归生成子agent
def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    sub_tools = [
        {"name": "bash", "description": "Run command.",
         "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
        {"name": "read_file", "description": "Read file.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    if agent_type != "Explore":
        sub_tools += [
            {"name": "write_file", "description": "Write file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
        ]
    sub_handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    }
    sub_msgs = [{"role": "user", "content": prompt}]
    sub_system = build_system_prompt(
        SKILLS.descriptions(),
        TEAM.config,
        agent_kind="subagent",
        role_mode_notes=f"Subagent mode: {agent_type}",
        tool_names=[tool["name"] for tool in sub_tools],
    )
    resp = None
    for _ in range(30):
        resp = get_client().messages.create(
            model=get_model(),
            system=sub_system,
            messages=sub_msgs,
            tools=sub_tools,
            max_tokens=8000,
        )
        sub_msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                h = sub_handlers.get(b.name, lambda **kw: "Unknown tool")
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(h(**b.input))[:50000]})
        sub_msgs.append({"role": "user", "content": results})
    if resp:
        return "".join(b.text for b in resp.content if hasattr(b, "text")) or "(no summary)"
    return "(subagent failed)"


# === SECTION: skills (s05) ===
class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}
        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("SKILL.md")):
                text = f.read_text(encoding="utf-8")
                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
                meta, body = {}, text
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = match.group(2).strip()
                name = meta.get("name", f.parent.name)
                self.skills[name] = {"meta": meta, "body": body, "path": str(f)}

    def descriptions(self) -> str:
        if not self.skills: return "(no skills)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}" for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s: return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"


# === SECTION: compression (s06) ===

# 估算对话 Token 数（JSON 长度 / 4）
def estimate_tokens(messages: list) -> int:
    return len(json.dumps(messages, default=str)) // 4

# 轻量压缩（保留最近 3 个工具结果，其余替换为占位符）
# 每轮交互前都检查一次；一旦历史工具结果超过 3 个，就清理更早的长输出。
def microcompact(messages: list) -> int:
    indices = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    indices.append(part)
    if len(indices) <= 3:
        return 0
    cleared = 0
    for part in indices[:-3]:
        if isinstance(part.get("content"), str) and len(part["content"]) > 100:
            if part["content"] != MICROCOMPACT_PLACEHOLDER:
                part["content"] = MICROCOMPACT_PLACEHOLDER
                cleared += 1
    return cleared

# 当上下文逼近“模型上下文窗口 - 20k 缓冲区”时，触发重度压缩：
# 1. 将完整历史写入 transcript 文件留痕
# 2. 启动一个专门的摘要子 agent 生成连续性摘要
# 3. 用摘要整体替换旧历史
def run_summary_subagent(transcript_text: str, transcript_path: Path) -> str:
    written_summary = {"value": ""}
    summary_tools = [
        {"name": "write_summary", "description": "Write the final continuity summary that will replace the old history.",
         "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
    ]
    summary_handlers = {
        "write_summary": lambda **kw: written_summary.__setitem__("value", kw["summary"]) or "Summary saved.",
    }
    summary_system = build_system_prompt(
        SKILLS.descriptions(),
        TEAM.config,
        agent_kind="subagent",
        role_mode_notes=(
            "Subagent mode: CompactSummary. "
            "You are a dedicated summarizer subagent. "
            "You must preserve the user's goals, hard constraints, unfinished work, key file paths, "
            "important tool findings, and the latest execution state. "
            "You only have one tool: write_summary."
        ),
        tool_names=[tool["name"] for tool in summary_tools],
    )
    summary_prompt = (
        "Summarize the full conversation history for continuity.\n"
        "Requirements:\n"
        "1. Preserve user goals, hard constraints, current implementation state, unfinished tasks, and key file paths.\n"
        "2. Preserve important conclusions from tool outputs, but omit bulky raw output.\n"
        "3. Produce a concise summary suitable to replace the old history.\n"
        "4. Call write_summary exactly once with the final summary.\n\n"
        f"Transcript path: {transcript_path}\n"
        f"Transcript content:\n{transcript_text}"
    )
    sub_msgs = [{"role": "user", "content": summary_prompt}]
    resp = None
    for _ in range(8):
        resp = get_client().messages.create(
            model=get_model(),
            system=summary_system,
            messages=sub_msgs,
            tools=summary_tools,
            max_tokens=4000,
        )
        sub_msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                h = summary_handlers.get(b.name, lambda **kw: "Unknown tool")
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(h(**b.input))[:50000]})
        sub_msgs.append({"role": "user", "content": results})
        if written_summary["value"]:
            break
    if written_summary["value"]:
        return written_summary["value"]
    if resp:
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        if text:
            return text
    return "(summary unavailable)"


def auto_compact(messages: list) -> list:
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    conv_text = json.dumps(messages, default=str)
    summary = run_summary_subagent(conv_text, path)
    return [
        {"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"},
    ]


# === SECTION: file_tasks (s07) ===
class TaskManager:
    def __init__(self):
        TASKS_DIR.mkdir(exist_ok=True)
        self.db_path = TASKS_DIR / "tasks.db"
        self._init_db()
        self._migrate_legacy_json()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=3, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    owner TEXT,
                    blocked_by_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_status_owner
                ON tasks(status, owner, id)
                """
            )

    def _migrate_legacy_json(self) -> None:
        legacy_files = sorted(TASKS_DIR.glob("task_*.json"))
        if not legacy_files:
            return
        with self._connect() as conn:
            existing = {row["id"] for row in conn.execute("SELECT id FROM tasks").fetchall()}
            for f in legacy_files:
                try:
                    task = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    continue
                tid = int(task.get("id", 0) or 0)
                if not tid or tid in existing:
                    continue
                now = time.time()
                conn.execute(
                    """
                    INSERT INTO tasks (id, subject, description, status, owner, blocked_by_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tid,
                        str(task.get("subject", f"task-{tid}")),
                        str(task.get("description", "")),
                        str(task.get("status", "pending")),
                        task.get("owner"),
                        json.dumps(task.get("blockedBy", []), ensure_ascii=False),
                        now,
                        now,
                    ),
                )

    def _row_to_task(self, row: sqlite3.Row) -> dict:
        blocked_raw = row["blocked_by_json"] or "[]"
        try:
            blocked = json.loads(blocked_raw)
            if not isinstance(blocked, list):
                blocked = []
        except json.JSONDecodeError:
            blocked = []
        return {
            "id": row["id"],
            "subject": row["subject"],
            "description": row["description"],
            "status": row["status"],
            "owner": row["owner"],
            "blockedBy": blocked,
        }

    def _load(self, tid: int, conn: sqlite3.Connection | None = None) -> dict:
        owns_conn = conn is None
        conn = conn or self._connect()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                raise ValueError(f"Task {tid} not found")
            return self._row_to_task(row)
        finally:
            if owns_conn:
                conn.close()

    def _update_task_row(self, conn: sqlite3.Connection, task: dict) -> None:
        conn.execute(
            """
            UPDATE tasks
            SET subject=?, description=?, status=?, owner=?, blocked_by_json=?, updated_at=?
            WHERE id=?
            """,
            (
                task["subject"],
                task.get("description", ""),
                task["status"],
                task.get("owner"),
                json.dumps(task.get("blockedBy", []), ensure_ascii=False),
                time.time(),
                task["id"],
            ),
        )

    def create(self, subject: str, description: str = "") -> str:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks (subject, description, status, owner, blocked_by_json, created_at, updated_at)
                VALUES (?, ?, 'pending', NULL, '[]', ?, ?)
                """,
                (subject, description, now, now),
            )
            task = self._load(cur.lastrowid, conn)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, tid: int) -> str:
        return json.dumps(self._load(tid), indent=2, ensure_ascii=False)

    def update(self, tid: int, status: str = None,
               add_blocked_by: list = None, remove_blocked_by: list = None) -> str:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._load(tid, conn)
            if status:
                task["status"] = status
                if status == "completed":
                    rows = conn.execute("SELECT * FROM tasks").fetchall()
                    for row in rows:
                        other = self._row_to_task(row)
                        if tid in other.get("blockedBy", []):
                            other["blockedBy"] = [x for x in other["blockedBy"] if x != tid]
                            self._update_task_row(conn, other)
                if status == "deleted":
                    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
                    conn.commit()
                    return f"Task {tid} deleted"
            if add_blocked_by:
                task["blockedBy"] = sorted(set(task["blockedBy"] + add_blocked_by))
            if remove_blocked_by:
                task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]
            self._update_task_row(conn, task)
            conn.commit()
        return json.dumps(task, indent=2, ensure_ascii=False)

    def list_all(self) -> str:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        tasks = [self._row_to_task(row) for row in rows]
        if not tasks: return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{m} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, tid: int, owner: str) -> str:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self._load(tid, conn)
            if task.get("owner") and task["owner"] != owner:
                conn.commit()
                return f"Error: Task #{tid} already claimed by {task['owner']}"
            task["owner"] = owner
            task["status"] = "in_progress"
            self._update_task_row(conn, task)
            conn.commit()
        return f"Claimed task #{tid} for {owner}"

    def list_ready_unclaimed(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status='pending' AND owner IS NULL
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        tasks = [self._row_to_task(row) for row in rows]
        return [task for task in tasks if not task.get("blockedBy")]


# === SECTION: background (s08) ===
class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(target=self._exec, args=(tid, command, timeout), daemon=True).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int):
        try:
            output = SANDBOX.run(command, timeout=timeout)
            status = "error" if output.startswith("Error:") else "completed"
            self.tasks[tid].update({"status": status, "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({"task_id": tid, "status": self.tasks[tid]["status"],
                                "result": self.tasks[tid]["result"][:500]})

    def check(self, tid: str = None) -> str:
        if tid:
            t = self.tasks.get(tid)
            return f"[{t['status']}] {t.get('result') or '(running)'}" if t else f"Unknown: {tid}"
        return "\n".join(f"{k}: [{v['status']}] {v['command'][:60]}" for k, v in self.tasks.items()) or "No bg tasks."

    def drain(self) -> list:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs


# === SECTION: messaging (s09) ===
class MessageBus:
    def __init__(self):
        TEAM_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = TEAM_DIR / "bus.db"
        self.max_retry = 3
        self.stale_processing_seconds = max(IDLE_TIMEOUT * 2, 120)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=3, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_type TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    content TEXT NOT NULL,
                    extra_json TEXT,
                    request_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    claimed_at REAL,
                    processed_at REAL,
                    consumer TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_text TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_receiver_status_created
                ON messages(receiver, status, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_request_id
                ON messages(request_id)
                """
            )

    def _row_to_message(self, row: sqlite3.Row) -> dict:
        msg = {
            "id": row["id"],
            "type": row["msg_type"],
            "from": row["sender"],
            "to": row["receiver"],
            "content": row["content"],
            "timestamp": row["created_at"],
            "status": row["status"],
            "retry_count": row["retry_count"],
        }
        if row["request_id"]:
            msg["request_id"] = row["request_id"]
        if row["extra_json"]:
            try:
                extra = json.loads(row["extra_json"])
                if isinstance(extra, dict):
                    msg.update(extra)
            except json.JSONDecodeError:
                msg["extra_json_error"] = row["extra_json"]
        if row["error_text"]:
            msg["error_text"] = row["error_text"]
        return msg

    def _ids_sql(self, ids: list[int]) -> str:
        return ",".join("?" for _ in ids)

    def recover_stale_processing(self, receiver: str | None = None) -> int:
        cutoff = time.time() - self.stale_processing_seconds
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if receiver:
                cur = conn.execute(
                    """
                    UPDATE messages
                    SET status='pending', consumer=NULL, claimed_at=NULL,
                        error_text=COALESCE(error_text, 'recovered after stale processing timeout')
                    WHERE status='processing' AND claimed_at IS NOT NULL AND claimed_at < ? AND receiver=?
                    """,
                    (cutoff, receiver),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE messages
                    SET status='pending', consumer=NULL, claimed_at=NULL,
                        error_text=COALESCE(error_text, 'recovered after stale processing timeout')
                    WHERE status='processing' AND claimed_at IS NOT NULL AND claimed_at < ?
                    """,
                    (cutoff,),
                )
            conn.commit()
            return cur.rowcount or 0

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        payload_extra = dict(extra or {})
        request_id = payload_extra.get("request_id")
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    msg_type, sender, receiver, content, extra_json, request_id,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    msg_type,
                    sender,
                    to,
                    content,
                    json.dumps(payload_extra, ensure_ascii=False) if payload_extra else None,
                    request_id,
                    now,
                ),
            )
        return f"Sent {msg_type} to {to}"

    def claim_inbox(self, name: str, limit: int = 50, consumer: str | None = None) -> list[dict]:
        consumer = consumer or name
        self.recover_stale_processing(name)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE receiver=? AND status='pending'
                ORDER BY id
                LIMIT ?
                """,
                (name, limit),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                now = time.time()
                conn.execute(
                    f"""
                    UPDATE messages
                    SET status='processing', consumer=?, claimed_at=?, error_text=NULL
                    WHERE id IN ({self._ids_sql(ids)}) AND status='pending'
                    """,
                    [consumer, now, *ids],
                )
                rows = conn.execute(
                    f"SELECT * FROM messages WHERE id IN ({self._ids_sql(ids)}) ORDER BY id",
                    ids,
                ).fetchall()
            conn.commit()
        return [self._row_to_message(row) for row in rows]

    def ack_messages(self, message_ids: list[int], consumer: str) -> int:
        if not message_ids:
            return 0
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE messages
                SET status='done', processed_at=?, error_text=NULL
                WHERE id IN ({self._ids_sql(message_ids)}) AND status='processing' AND consumer=?
                """,
                [time.time(), *message_ids, consumer],
            )
            return cur.rowcount or 0

    def fail_messages(self, message_ids: list[int], consumer: str, error_text: str) -> int:
        if not message_ids:
            return 0
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                f"""
                SELECT id, retry_count FROM messages
                WHERE id IN ({self._ids_sql(message_ids)}) AND status='processing' AND consumer=?
                """,
                [*message_ids, consumer],
            ).fetchall()
            affected = 0
            for row in rows:
                retry_count = row["retry_count"] + 1
                next_status = "dead" if retry_count >= self.max_retry else "pending"
                conn.execute(
                    """
                    UPDATE messages
                    SET status=?, retry_count=?, error_text=?, processed_at=?,
                        consumer=NULL, claimed_at=NULL
                    WHERE id=?
                    """,
                    (next_status, retry_count, error_text[:1000], now, row["id"]),
                )
                affected += 1
            conn.commit()
        return affected

    def peek_inbox(self, name: str, include_processing: bool = False, limit: int = 50) -> list[dict]:
        statuses = ["pending", "processing", "done", "dead"] if include_processing else ["pending"]
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM messages
                WHERE receiver=? AND status IN ({placeholders})
                ORDER BY id
                LIMIT ?
                """,
                [name, *statuses, limit],
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def read_inbox(self, name: str) -> list:
        return self.peek_inbox(name)

    def broadcast(self, sender: str, content: str, names: list) -> str:
        count = 0
        for n in names:
            if n != sender:
                self.send(sender, n, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"


# === SECTION: shutdown + plan tracking (s10) ===
shutdown_requests = {}
plan_requests = {}


# === SECTION: team (s09/s11) ===
class TeammateManager:
    def __init__(self, bus: MessageBus, task_mgr: TaskManager):
        TEAM_DIR.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self.config_path = TEAM_DIR / "config.json"
        self.config = self._load()
        self.threads = {}

    def _load(self) -> dict:
        if self.config_path.exists():
            raw = json.loads(self.config_path.read_text(encoding="utf-8", errors="replace"))
            members = raw.get("members", [])
            if not isinstance(members, list):
                members = []
            normalized = []
            known = {item["name"]: item for item in _clone_default_teammates()}
            for member in members:
                if not isinstance(member, dict) or not member.get("name"):
                    continue
                name = member["name"]
                default = known.get(name, {})
                normalized.append(
                    {
                        "name": name,
                        "role": member.get("role", default.get("role", "assistant")),
                        "status": member.get("status", default.get("status", "idle")),
                        "responsibility": member.get("responsibility", default.get("responsibility", "")),
                        "when_to_spawn": member.get("when_to_spawn", default.get("when_to_spawn", "")),
                        "prompt_template": member.get("prompt_template", default.get("prompt_template", "")),
                    }
                )
            for name, default in known.items():
                if not any(member["name"] == name for member in normalized):
                    normalized.append(default)
            team_name = raw.get("team_name") or raw.get("team", {}).get("name") or "default"
            return {"team_name": team_name, "members": normalized}
        return {"team_name": "default", "members": _clone_default_teammates()}

    def _save(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name: return m
        return None

    def spawn(self, name: str, role: str, prompt: str, request_id: str | None = None) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
            if prompt:
                member["prompt_template"] = prompt
        else:
            member = {"name": name, "role": role, "status": "working", "responsibility": "", "when_to_spawn": "", "prompt_template": prompt}
            self.config["members"].append(member)
        self._save()
        thread_name = f"teammate-{name}-{uuid.uuid4().hex[:6]}"
        publish_timeline(
            request_id,
            f"teammate:{name}",
            "thread.spawned",
            {"role": role, "thread_name": thread_name, "mode": "background-daemon"},
        )
        print(f"[teammate:{name}] spawned background thread '{thread_name}'")
        threading.Thread(
            target=self._loop,
            args=(name, role, prompt, request_id, thread_name),
            daemon=True,
            name=thread_name,
        ).start()
        return (
            f"Spawned teammate '{name}' (role: {role}) in background thread '{thread_name}'. "
            "It will work asynchronously, switch between working/idle states, and shut down after idle timeout."
        )

    def _set_status(self, name: str, status: str, request_id: str | None = None, reason: str | None = None):
        member = self._find(name)
        if member:
            member["status"] = status
            self._save()
            payload = {"status": status}
            if reason:
                payload["reason"] = reason
            publish_timeline(request_id, f"teammate:{name}", "status.changed", payload)
            print(f"[teammate:{name}] status -> {status}" + (f" ({reason})" if reason else ""))

    def _loop(self, name: str, role: str, prompt: str, request_id: str | None = None, thread_name: str | None = None):
        team_name = self.config["team_name"]
        member = self._find(name) or {}
        messages = [{"role": "user", "content": prompt}]
        publish_timeline(
            request_id,
            f"teammate:{name}",
            "thread.running",
            {"thread_name": thread_name or threading.current_thread().name, "prompt_preview": prompt[:120]},
        )
        tools = [
            {"name": "bash", "description": "Run command.", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message.", "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
            {"name": "idle", "description": "Signal no more work.", "input_schema": {"type": "object", "properties": {}}},
            {"name": "claim_task", "description": "Claim task by ID.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
            {"name": "task_update", "description": "Update claimed task status.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}}, "required": ["task_id"]}},
        ]
        sys_prompt = build_system_prompt(
            SKILLS.descriptions(),
            self.config,
            agent_kind="teammate",
            role_name=name,
            role_desc=role,
            tool_names=[tool["name"] for tool in tools],
            role_mode_notes=(
                f"Team name: {team_name}\n"
                f"Responsibility: {member.get('responsibility', '')}\n"
                f"When to spawn: {member.get('when_to_spawn', '')}\n"
                f"Initial prompt template: {member.get('prompt_template', prompt)}\n"
                "Use idle when done with current work. You may auto-claim pending tasks."
            ),
        )
        while True:
            # -- WORK PHASE --
            for _ in range(50):
                inbox = self.bus.claim_inbox(name, consumer=name)
                inbox_ids = [msg["id"] for msg in inbox]
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        if inbox_ids:
                            self.bus.ack_messages(inbox_ids, name)
                        publish_timeline(request_id, f"teammate:{name}", "message.received", {"type": "shutdown_request"})
                        self._set_status(name, "shutdown", request_id, "shutdown_request")
                        return
                    publish_timeline(
                        request_id,
                        f"teammate:{name}",
                        "message.received",
                        {"type": msg.get("type", "message"), "from": msg.get("from"), "content_preview": str(msg.get("content", ""))[:120]},
                    )
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    response = get_client().messages.create(
                        model=get_model(), system=sys_prompt, messages=messages,
                        tools=tools, max_tokens=8000)
                    if inbox_ids:
                        self.bus.ack_messages(inbox_ids, name)
                except Exception as e:
                    if inbox_ids:
                        self.bus.fail_messages(inbox_ids, name, f"llm_error: {e}")
                    self._set_status(name, "shutdown", request_id, "llm_error")
                    return
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason != "tool_use":
                    break
                results = []
                idle_requested = False
                for block in response.content:
                    if block.type == "tool_use":
                        try:
                            if block.name == "idle":
                                idle_requested = True
                                output = "Entering idle phase."
                            elif block.name == "claim_task":
                                output = self.task_mgr.claim(block.input["task_id"], name)
                                publish_timeline(
                                    request_id,
                                    f"teammate:{name}",
                                    "task.claimed",
                                    {"task_id": block.input["task_id"], "mode": "explicit"},
                                )
                            elif block.name == "send_message":
                                output = self.bus.send(name, block.input["to"], block.input["content"])
                                publish_timeline(
                                    request_id,
                                    f"teammate:{name}",
                                    "message.sent",
                                    {"to": block.input["to"], "content_preview": block.input["content"][:120]},
                                )
                            elif block.name == "task_update":
                                output = self.task_mgr.update(block.input["task_id"], block.input.get("status"))
                                publish_timeline(
                                    request_id,
                                    f"teammate:{name}",
                                    "task.updated",
                                    {"task_id": block.input["task_id"], "status": block.input.get("status")},
                                )
                            else:
                                dispatch = {"bash": lambda **kw: run_bash(kw["command"]),
                                            "read_file": lambda **kw: run_read(kw["path"]),
                                            "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
                                            "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"])}
                                output = dispatch.get(block.name, lambda **kw: "Unknown")(**block.input)
                        except Exception as e:
                            output = f"Error: {e}"
                        print(f"  [{name}] {block.name}: {str(output)[:120]}")
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                messages.append({"role": "user", "content": results})
                if idle_requested:
                    break
            # -- IDLE PHASE: poll for messages and unclaimed tasks --
            self._set_status(name, "idle", request_id, "work_phase_complete")
            resume = False
            for _ in range(IDLE_TIMEOUT // max(POLL_INTERVAL, 1)):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.claim_inbox(name, consumer=name)
                if inbox:
                    self.bus.ack_messages([msg["id"] for msg in inbox], name)
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            publish_timeline(request_id, f"teammate:{name}", "message.received", {"type": "shutdown_request"})
                            self._set_status(name, "shutdown", request_id, "shutdown_request")
                            return
                        publish_timeline(
                            request_id,
                            f"teammate:{name}",
                            "message.received",
                            {"type": msg.get("type", "message"), "from": msg.get("from"), "content_preview": str(msg.get("content", ""))[:120]},
                        )
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
                unclaimed = self.task_mgr.list_ready_unclaimed(limit=10)
                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)
                    publish_timeline(
                        request_id,
                        f"teammate:{name}",
                        "task.claimed",
                        {"task_id": task["id"], "subject": task["subject"], "mode": "auto"},
                    )
                    # Identity re-injection for compressed contexts
                    if len(messages) <= 3:
                        messages.insert(0, {"role": "user", "content":
                            f"<identity>You are '{name}', role: {role}, team: {team_name}.</identity>"})
                        messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
                    messages.append({"role": "user", "content":
                        f"<auto-claimed>Task #{task['id']}: {task['subject']}\n{task.get('description', '')}</auto-claimed>"})
                    messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown", request_id, "idle_timeout")
                return
            self._set_status(name, "working", request_id, "resumed_from_idle")

    def list_all(self) -> str:
        if not self.config["members"]: return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]


# === SECTION: global_instances ===
TODO = TodoManager()
SKILLS = SkillLoader(SKILLS_DIR)
TASK_MGR = TaskManager()
BG = BackgroundManager()
BUS = MessageBus()
TEAM = TeammateManager(BUS, TASK_MGR)

# === SECTION: shutdown_protocol (s10) ===
shutdown_requests = {}
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down.", "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent to '{teammate}'"

# === SECTION: plan_approval (s10) ===
plan_requests = {}
def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    req = plan_requests.get(request_id)
    if not req: return f"Error: Unknown plan request_id '{request_id}'"
    req["status"] = "approved" if approve else "rejected"
    BUS.send("lead", req["from"], feedback, "plan_approval_response",
             {"request_id": request_id, "approve": approve, "feedback": feedback})
    return f"Plan {req['status']} for '{req['from']}'"


# === SECTION: tool_dispatch (s02) ===
TOOL_HANDLERS = {
    "bash":             lambda **kw: run_bash(kw["command"]),
    "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "TodoWrite":        lambda **kw: TODO.update(kw["items"]),
    "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
    "load_skill":       lambda **kw: SKILLS.load(kw["name"]),
    "compress":         lambda **kw: "Compressing...",
    "background_run":   lambda **kw: BG.run(kw["command"], kw.get("timeout", 120)),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
    "task_create":      lambda **kw: TASK_MGR.create(kw["subject"], kw.get("description", "")),
    "task_get":         lambda **kw: TASK_MGR.get(kw["task_id"]),
    "task_update":      lambda **kw: TASK_MGR.update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("remove_blocked_by")),
    "task_list":        lambda **kw: TASK_MGR.list_all(),
    "spawn_teammate":   lambda **kw: TEAM.spawn(kw["name"], kw["role"], kw["prompt"], ACTIVE_REQUEST_ID.get()),
    "list_teammates":   lambda **kw: TEAM.list_all(),
    "send_message":     lambda **kw: BUS.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
    "read_inbox":       lambda **kw: json.dumps(BUS.peek_inbox("lead"), indent=2),
    "broadcast":        lambda **kw: BUS.broadcast("lead", kw["content"], TEAM.member_names()),
    "shutdown_request": lambda **kw: handle_shutdown_request(kw["teammate"]),
    "plan_approval":    lambda **kw: handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
    "idle":             lambda **kw: "Lead does not idle.",
    "claim_task":       lambda **kw: TASK_MGR.claim(kw["task_id"], "lead"),
}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "TodoWrite", "description": "Update task tracking list.",
     "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}, "activeForm": {"type": "string"}}, "required": ["content", "status", "activeForm"]}}}, "required": ["items"]}},
    {"name": "task", "description": "Spawn a subagent for isolated exploration or work.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "agent_type": {"type": "string", "enum": ["Explore", "general-purpose"]}}, "required": ["prompt"]}},
    {"name": "load_skill", "description": "Load specialized knowledge by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "compress", "description": "Manually compress conversation context.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "background_run", "description": "Run command in background thread.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "check_background", "description": "Check background task status.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
    {"name": "task_create", "description": "Create a persistent file task.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}},
    {"name": "task_get", "description": "Get task details by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "task_update", "description": "Update task status or dependencies.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}, "add_blocked_by": {"type": "array", "items": {"type": "integer"}}, "remove_blocked_by": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}},
    {"name": "task_list", "description": "List all tasks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spawn_teammate", "description": "Spawn a persistent autonomous teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Peek at the lead's inbox without consuming.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
    {"name": "idle", "description": "Enter idle state.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_task", "description": "Claim a task from the board.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
]


# === SECTION: system_prompt ===
SYSTEM = build_system_prompt(
    SKILLS.descriptions(),
    TEAM.config,
    agent_kind="lead",
    tool_names=[tool["name"] for tool in TOOLS],
)


# === SECTION: agent_loop ===
def agent_loop(messages: list, request_id: str = None):
    rounds_without_todo = 0
    while True:
        # s06: compression pipeline
        cleared = microcompact(messages)
        if cleared:
            print(f"[micro-compact triggered] cleared={cleared}")
        threshold = get_compaction_trigger_threshold()
        estimated = estimate_tokens(messages)
        if estimated >= threshold:
            print(f"[auto-compact triggered] estimated={estimated} threshold={threshold}")
            messages[:] = auto_compact(messages)
        # s08: drain background notifications
        notifs = BG.drain()
        if notifs:
            txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
            messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})
        # s10: check lead inbox
        inbox = BUS.claim_inbox("lead", consumer="lead")
        inbox_ids = [msg["id"] for msg in inbox]
        if inbox:
            messages.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})
        # LLM call
        if request_id:
            timeline_store.publish(request_id, "llm", "request", {"model": get_model(), "messages_count": len(messages)})
        
        try:
            with get_client().messages.stream(
                model=get_model(), system=SYSTEM, messages=messages,
                tools=TOOLS, max_tokens=8000,
            ) as stream:
                for text in stream.text_stream:
                    yield text
                response = stream.get_final_message()
            if inbox_ids:
                BUS.ack_messages(inbox_ids, "lead")
        except Exception as e:
            if inbox_ids:
                BUS.fail_messages(inbox_ids, "lead", f"llm_error: {e}")
            raise
        
        if request_id:
            timeline_store.publish(request_id, "llm", "response", {"stop_reason": response.stop_reason})
            
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return
        # Tool execution
        results = []
        used_todo = False
        manual_compress = False
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "compress":
                    manual_compress = True
                handler = TOOL_HANDLERS.get(block.name)
                try:
                    token = ACTIVE_REQUEST_ID.set(request_id)
                    if request_id:
                        timeline_store.publish(request_id, "tool", block.name, block.input)
                    output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                except Exception as e:
                    output = f"Error: {e}"
                finally:
                    ACTIVE_REQUEST_ID.reset(token)
                if request_id:
                    timeline_store.publish(request_id, "tool_result", block.name, {"output": str(output)[:500]})
                print(f"> {block.name}:")
                print(str(output)[:200])
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                if block.name == "TodoWrite":
                    used_todo = True
        # s03: nag reminder (only when todo workflow is active)
        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
        if TODO.has_open_items() and rounds_without_todo >= 3:
            results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})
        messages.append({"role": "user", "content": results})
        # s06: manual compress
        if manual_compress:
            print("[manual compact]")
            messages[:] = auto_compact(messages)
            yield "Context manually compressed."
            return


# === SECTION: repl ===
if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms_full >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/compact":
            if history:
                print("[manual compact via /compact]")
                history[:] = auto_compact(history)
            continue
        if query.strip() == "/tasks":
            print(TASK_MGR.list_all())
            continue
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        if query.strip().startswith("/remember"):
            rule = query.strip()[len("/remember"):].strip()
            print(append_agent_rule(rule))
            lead_tools = [tool["name"] for tool in TOOLS]
            SYSTEM = build_system_prompt(
                SKILLS.descriptions(),
                TEAM.config,
                agent_kind="lead",
                tool_names=lead_tools,
            )
            continue
        history.append({"role": "user", "content": query})
        for chunk in agent_loop(history):
            print(chunk, end="", flush=True)
        print()
