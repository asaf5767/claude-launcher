"""Discover repos and sessions from the filesystem."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from claude_launcher.config import (
    CLAUDE_PROJECTS_DIR,
    get_repos_dirs,
    load_hidden_sessions,
    normalize_path_for_claude,
)
from claude_launcher.data.models import RepoInfo, Session

# Tail read size for extracting last prompt from .jsonl files
_TAIL_READ_BYTES = 8_000
_MAX_LINE_SIZE = 100_000      # Skip JSON lines larger than 100KB
_MAX_INDEX_SIZE = 10_000_000  # Skip sessions-index.json larger than 10MB
_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{30,}$')


def discover_repos() -> list[RepoInfo]:
    """Discover all repos across all configured directories."""
    repos_dirs = get_repos_dirs()
    entries: list[Path] = []

    for repos_dir in repos_dirs:
        if not repos_dir.exists():
            continue
        try:
            for entry in sorted(repos_dir.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name.lower() in ("new folder", "nul"):
                    continue
                entries.append(entry)
        except OSError:
            continue

    # Deduplicate by resolved path
    seen_paths: set[str] = set()
    unique_entries: list[Path] = []
    for e in entries:
        resolved = str(e.resolve()).lower()
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            unique_entries.append(e)

    # Load hidden sessions once, pass to all workers
    hidden = load_hidden_sessions()

    def _process(entry: Path) -> RepoInfo:
        branch = _get_git_branch(entry)
        sessions = _find_sessions(entry, hidden)
        return RepoInfo(
            name=entry.name,
            path=str(entry),
            sessions=sessions,
            current_branch=branch,
        )

    repos: list[RepoInfo] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_process, e): e for e in unique_entries}
        for fut in as_completed(futures):
            try:
                repos.append(fut.result())
            except Exception:
                pass

    # Sort: repos with sessions first (by recency), then alphabetical
    with_sessions = sorted(
        [r for r in repos if r.sessions],
        key=lambda r: -(r.latest_activity.timestamp() if r.latest_activity else 0),
    )
    without_sessions = sorted(
        [r for r in repos if not r.sessions],
        key=lambda r: r.name.lower(),
    )
    return with_sessions + without_sessions


def _get_git_branch(repo_path: Path) -> str:
    """Get current git branch by reading .git/HEAD directly (fast)."""
    try:
        content = (repo_path / ".git" / "HEAD").read_text().strip()
        if content.startswith("ref: refs/heads/"):
            return content[16:]
        return ""
    except (OSError, ValueError):
        return ""


def _find_sessions(repo_path: Path, hidden: set[str]) -> list[Session]:
    """Find all Claude sessions for a repo."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return []

    # Build all possible normalized forms of this path.
    # On WSL, /mnt/c/repos/foo normalizes to "-mnt-c-repos-foo" but Claude
    # stored it as "C--repos-foo" (Windows path). Try both.
    candidates = set()
    repo_str = str(repo_path)
    candidates.add(normalize_path_for_claude(repo_str).lower())

    # WSL: convert /mnt/X/... to X:\... style for matching
    if repo_str.startswith("/mnt/") and len(repo_str) > 5:
        drive_letter = repo_str[5].upper()
        win_path = f"{drive_letter}:{repo_str[6:]}"
        candidates.add(normalize_path_for_claude(win_path).lower())

    matching_dirs: list[Path] = []
    try:
        for proj_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            name_lower = proj_dir.name.lower()
            for candidate in candidates:
                if name_lower == candidate:
                    matching_dirs.append(proj_dir)
                    break
                if (
                    name_lower.startswith(candidate + "-")
                    and "--claude-worktrees-" in proj_dir.name
                ):
                    matching_dirs.append(proj_dir)
                    break
    except OSError:
        return []

    sessions: list[Session] = []
    for proj_dir in matching_dirs:
        index_file = proj_dir / "sessions-index.json"
        try:
            sessions.extend(_parse_sessions_index(index_file, proj_dir))
        except (json.JSONDecodeError, OSError, KeyError):
            sessions.extend(_scan_jsonl_sessions(proj_dir, str(repo_path)))

    # Sort, deduplicate, filter hidden
    sessions.sort(key=lambda s: s.modified, reverse=True)
    seen: set[str] = set()
    unique = []
    for s in sessions:
        if s.session_id not in seen and s.session_id not in hidden:
            seen.add(s.session_id)
            unique.append(s)
    return unique


def _parse_sessions_index(index_file: Path, proj_dir: Path) -> list[Session]:
    """Parse sessions-index.json. Raises on file error (caller catches)."""
    if index_file.stat().st_size > _MAX_INDEX_SIZE:
        return []
    data = json.loads(index_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    sessions = []
    for entry in data.get("entries", [])[:500]:
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        session = _entry_to_session(entry)
        if session and _SESSION_ID_RE.match(session.session_id):
            jsonl = proj_dir / f"{session.session_id}.jsonl"
            session.last_prompt = _extract_last_prompt(jsonl)
            sessions.append(session)
    return sessions


def _entry_to_session(entry: dict) -> Session | None:
    try:
        return Session(
            session_id=entry["sessionId"],
            summary=entry.get("summary", ""),
            first_prompt=entry.get("firstPrompt", ""),
            last_prompt="",
            message_count=entry.get("messageCount", 0),
            created=_parse_dt(entry.get("created", "")),
            modified=_parse_dt(entry.get("modified", "")),
            git_branch=entry.get("gitBranch", ""),
            project_path=entry.get("projectPath", ""),
        )
    except (KeyError, ValueError):
        return None


def _extract_last_prompt(jsonl_path: Path) -> str:
    """Read the last user prompt from a .jsonl session file (from tail)."""
    try:
        size = jsonl_path.stat().st_size
        read_size = min(size, _TAIL_READ_BYTES)
        with open(jsonl_path, "rb") as f:
            if size > read_size:
                f.seek(size - read_size)
            raw = f.read().decode("utf-8", errors="replace")
        for line in reversed(raw.strip().split("\n")):
            line = line.strip()
            if not line or len(line) > _MAX_LINE_SIZE:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "user":
                    content = _extract_content(obj)
                    if content:
                        return content
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return ""


def _scan_jsonl_sessions(proj_dir: Path, repo_path: str) -> list[Session]:
    """Scan .jsonl files when no sessions-index.json exists."""
    sessions = []
    for jsonl_file in proj_dir.glob("*.jsonl"):
        session_id = jsonl_file.stem
        if not _SESSION_ID_RE.match(session_id):
            continue
        try:
            stat = jsonl_file.stat()
            if stat.st_size < 50:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)

            first_prompt = ""
            summary = ""
            git_branch = ""
            message_count = 0
            first_timestamp = None

            # Read first ~100 lines for metadata
            with open(jsonl_file, "r", encoding="utf-8", errors="replace") as f:
                for i in range(100):
                    line = f.readline(_MAX_LINE_SIZE)
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        msg_type = obj.get("type", "")
                        if not git_branch and obj.get("gitBranch"):
                            gb = obj["gitBranch"]
                            if gb != "HEAD":
                                git_branch = gb
                        if not first_timestamp and obj.get("timestamp"):
                            first_timestamp = obj["timestamp"]
                        if msg_type in ("user", "assistant"):
                            message_count += 1
                        if msg_type == "summary":
                            summary = obj.get("summary", "")
                        if msg_type == "user" and not first_prompt:
                            first_prompt = _extract_content(obj)
                    except json.JSONDecodeError:
                        continue

            # Get last prompt from tail
            last_prompt = _extract_last_prompt(jsonl_file)

            if first_timestamp:
                try:
                    created = _parse_dt(first_timestamp)
                except Exception:
                    pass

            sessions.append(Session(
                session_id=session_id,
                summary=summary or first_prompt or "",
                first_prompt=first_prompt,
                last_prompt=last_prompt,
                message_count=message_count,
                created=created,
                modified=modified,
                git_branch=git_branch,
                project_path=repo_path,
            ))
        except OSError:
            continue
    return sessions


def _extract_content(obj: dict) -> str:
    msg = obj.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        clean = content.strip()
        if clean and not clean.startswith("<system-reminder>"):
            return clean[:200]
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                if text and not text.startswith("<system-reminder>"):
                    return text[:200]
    return ""


def _parse_dt(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
