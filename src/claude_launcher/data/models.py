"""Data models for repos and sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import humanize


def truncate(text: str, max_len: int, suffix: str = "..") -> str:
    """Truncate string to max_len with suffix if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def _clean_prompt(text: str, max_len: int = 60) -> str:
    """Clean up a prompt for display -- strip tags, noise, truncate."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text).strip()
    if text.startswith("Caveat:"):
        parts = text.split("\n", 2)
        text = parts[-1].strip() if len(parts) > 1 else text
    text = text.lstrip("\u276f\u25ba\u25b8 ")  # ❯►▸
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if s.startswith("/") and len(s.split()) <= 3:
            continue
        if re.match(r"^[\w-]+:[\w-]+$", s):
            continue
        if s:
            cleaned.append(s)
    text = " ".join(cleaned).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b[a-z0-9]{10,}_[a-zA-Z0-9]+\b", "", text).strip()
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return truncate(text, max_len, "...")


@dataclass
class Session:
    """Represents a Claude Code conversation session."""

    session_id: str
    summary: str
    first_prompt: str
    last_prompt: str
    message_count: int
    created: datetime
    modified: datetime
    git_branch: str
    project_path: str

    @property
    def age_display(self) -> str:
        return humanize.naturaltime(self.modified)

    @property
    def display_first(self) -> str:
        return _clean_prompt(self.first_prompt)

    @property
    def display_last(self) -> str:
        return _clean_prompt(self.last_prompt)

    @property
    def display_summary(self) -> str:
        s = self.summary or self.first_prompt or ""
        return _clean_prompt(s, max_len=70)

    @property
    def journey_display(self) -> str:
        first = self.display_first
        last = self.display_last
        if first and last and first != last:
            f = _clean_prompt(self.first_prompt, 30)
            l = _clean_prompt(self.last_prompt, 30)
            return f'"{f}"  ->  "{l}"'
        elif first:
            return f'"{first}"'
        elif last:
            return f'"{last}"'
        return "(no prompt recorded)"


@dataclass
class RepoInfo:
    """Represents a repository with its Claude sessions."""

    name: str
    path: str
    sessions: list[Session] = field(default_factory=list)
    current_branch: str = ""

    @property
    def branch_display(self) -> str:
        return truncate(self.current_branch or "--", 20)

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    @property
    def latest_session(self) -> Session | None:
        if not self.sessions:
            return None
        return max(self.sessions, key=lambda s: s.modified)

    @property
    def latest_activity(self) -> datetime | None:
        latest = self.latest_session
        return latest.modified if latest else None

    @property
    def latest_topic(self) -> str:
        latest = self.latest_session
        return latest.display_summary if latest else ""
