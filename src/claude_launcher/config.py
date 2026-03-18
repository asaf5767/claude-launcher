"""Configuration, paths, session labels, and hidden sessions."""

import json
import sys
from pathlib import Path

from rich.console import Console

# -- Shared console --
console = Console(highlight=False)


# -- Platform-aware defaults --

def _detect_default_repos_dir() -> Path:
    if sys.platform == "win32":
        p = Path("C:/repos")
        if p.exists():
            return p
    else:
        # WSL: check /mnt/c/repos (Windows drive mounted in WSL)
        wsl_mount = Path("/mnt/c/repos")
        if wsl_mount.exists():
            return wsl_mount
    for name in ("repos", "code", "projects", "dev", "src"):
        p = Path.home() / name
        if p.exists():
            return p
    return Path.home() / "repos"


DEFAULT_REPOS_DIR = _detect_default_repos_dir()


def _detect_claude_dir() -> Path:
    """Find Claude Code's data directory, with WSL fallback."""
    native = Path.home() / ".claude"
    if native.exists() and any(native.iterdir()):
        return native
    # WSL: check Windows user's .claude dir
    if sys.platform != "win32":
        import os
        win_user = os.environ.get("WSLENV") or os.environ.get("WSL_DISTRO_NAME")
        if win_user is not None:
            # Try common Windows home paths under /mnt/c/Users/
            for win_home in Path("/mnt/c/Users").iterdir():
                candidate = win_home / ".claude"
                if candidate.exists() and (candidate / "projects").exists():
                    return candidate
    return native


CLAUDE_DIR = _detect_claude_dir()
CLAUDE_PROJECTS_DIR = CLAUDE_DIR / "projects"

CONFIG_DIR = Path.home() / ".claude-launcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
LABELS_FILE = CONFIG_DIR / "session-labels.json"
HIDDEN_FILE = CONFIG_DIR / "hidden-sessions.json"

DEFAULT_CONFIG = {
    "repos_dirs": [str(DEFAULT_REPOS_DIR)],
    "max_sessions_shown": 15,
    "show_empty_repos": False,
    "session_grouping": "chronological",  # TODO: not yet implemented
    "session_sort": "recent_first",       # TODO: not yet implemented
    "card_density": "standard",
    "ai_tool": "claude",        # claude | custom
    "custom_command": "",        # e.g. "proxy-claude --yolo", "copilot"
    "setup_complete": False,
}


# -- Generic JSON helpers --

def _load_json(path: Path, default=None):
    """Load JSON from file with error handling. Returns default on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return default


def _save_json(path: Path, data):
    """Save data as JSON, creating parent directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# -- Path normalization --

def normalize_path_for_claude(path: str) -> str:
    """Convert a filesystem path to Claude's project directory naming scheme."""
    return str(path).replace("\\", "-").replace("/", "-").replace(":", "-")


# -- Config --

def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    saved = _load_json(CONFIG_FILE)
    if saved:
        # Backward compat: old "repos_dir" (string) -> "repos_dirs" (list)
        if "repos_dir" in saved and "repos_dirs" not in saved:
            saved["repos_dirs"] = [saved.pop("repos_dir")]
        config.update(saved)
    return config


def save_config(config: dict):
    _save_json(CONFIG_FILE, config)


def get_repos_dirs() -> list[Path]:
    config = load_config()
    dirs = config.get("repos_dirs", [str(DEFAULT_REPOS_DIR)])
    if isinstance(dirs, str):
        dirs = [dirs]
    return [Path(d).expanduser() for d in dirs]


def get_ai_command(config: dict, override: str | None = None) -> str:
    """Get the AI tool command string (may include flags)."""
    if override:
        return override
    tool = config.get("ai_tool", "claude")
    if tool == "custom":
        return config.get("custom_command", "claude") or "claude"
    if tool == "copilot":
        # Backward compat: old config had copilot as separate option
        return "copilot"
    return "claude"


def get_ai_launch_args(config: dict, session_id: str | None, override: str | None = None) -> list[str]:
    """Build the full command list. Splits command string so flags are separate args."""
    parts = get_ai_command(config, override).split()
    if session_id:
        return parts + ["--resume", session_id]
    return parts


# -- Session labels --

def load_session_labels() -> dict[str, str]:
    return _load_json(LABELS_FILE) or {}


def save_session_labels(labels: dict[str, str]):
    _save_json(LABELS_FILE, labels)


def set_session_label(session_id: str, label: str):
    labels = load_session_labels()
    labels[session_id] = label
    save_session_labels(labels)


def get_session_label(session_id: str) -> str | None:
    return load_session_labels().get(session_id)


# -- Hidden sessions --

def load_hidden_sessions() -> set[str]:
    data = _load_json(HIDDEN_FILE)
    return set(data) if isinstance(data, list) else set()


def save_hidden_sessions(hidden: set[str]):
    _save_json(HIDDEN_FILE, sorted(hidden))


def add_hidden_session(session_id: str):
    hidden = load_hidden_sessions()
    hidden.add(session_id)
    save_hidden_sessions(hidden)


def remove_hidden_session(session_id: str):
    hidden = load_hidden_sessions()
    hidden.discard(session_id)
    save_hidden_sessions(hidden)
