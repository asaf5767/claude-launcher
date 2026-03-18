"""Session picker -- boxed rows with rename, hide, and delete support."""

from __future__ import annotations

import shutil

from rich.panel import Panel
from rich.text import Text
from rich import box

from claude_launcher.config import (
    CLAUDE_PROJECTS_DIR,
    console,
    get_session_label,
    set_session_label,
    load_config,
    load_session_labels,
    save_session_labels,
    add_hidden_session,
    remove_hidden_session,
    load_hidden_sessions,
    normalize_path_for_claude,
)
from claude_launcher.data.models import RepoInfo, Session, truncate
from claude_launcher.keyboard import get_key
from claude_launcher.ui.repo_picker import _viewport

ROW_WIDTH = 62
NEW_CHAT_HEIGHT = 3
SESSION_ROW_HEIGHT = 4


def _make_new_chat_row(is_selected: bool) -> Panel:
    if is_selected:
        border, style, bx = "bold #a5d6a7", "bold #a5d6a7", box.HEAVY
        subtitle = "[bold #a5d6a7]> enter[/]"
    else:
        border, style, bx = "#555555", "#7a9a72", box.ROUNDED
        subtitle = None

    content = Text()
    content.append(" +  Start New Chat", style=style)
    return Panel(
        content, border_style=border, box=bx,
        width=ROW_WIDTH, height=NEW_CHAT_HEIGHT,
        padding=(0, 0), subtitle=subtitle, subtitle_align="right",
    )


def _make_session_row(session: Session, is_selected: bool, is_hidden: bool = False,
                      labels: dict | None = None) -> Panel:
    label = (labels or {}).get(session.session_id) or get_session_label(session.session_id)
    branch = truncate(session.git_branch or "--", 18)
    msgs = f"{session.message_count} msg{'s' if session.message_count != 1 else ''}"

    if is_selected:
        border, meta_style, summary_style = "bold #b388ff", "#e0e0e0", "bold white"
        bx = box.HEAVY
        subtitle = "[bold #b388ff]\\[r]ename \\[d]hide | > enter[/]" if not is_hidden else "[bold #b388ff]\\[d] unhide | > enter[/]"
    else:
        border, meta_style, summary_style = "#555555", "#777777", "#cccccc"
        bx, subtitle = box.ROUNDED, None

    content = Text()
    prefix = "[hidden] " if is_hidden else ""
    content.append(f" {prefix}{session.age_display}", style=meta_style)
    content.append(f"  |  {msgs}", style=meta_style)
    content.append(f"  |  {branch}", style="#6a8a82" if is_selected else "#555555")
    content.append("\n")

    if label:
        content.append(f' * "{label}"', style=summary_style)
    else:
        journey = truncate(session.journey_display, ROW_WIDTH - 6)
        content.append(f" {journey}", style=summary_style)

    return Panel(
        content, border_style=border, box=bx,
        width=ROW_WIDTH, height=SESSION_ROW_HEIGHT,
        padding=(0, 0), subtitle=subtitle, subtitle_align="right",
    )


def _build_display_list(
    all_sessions: list[Session], show_hidden: bool, hidden: set[str],
) -> list[tuple[Session, bool]]:
    """Build list of (session, is_hidden) for display."""
    result = []
    for s in all_sessions:
        s_hidden = s.session_id in hidden
        if s_hidden and not show_hidden:
            continue
        result.append((s, s_hidden))
    return result


def _render(
    repo: RepoInfo,
    display_list: list[tuple[Session, bool]],
    selected: int,
    show_hidden: bool,
    hidden: set[str],
    labels: dict[str, str],
):
    console.clear()
    total_sessions = len(display_list)
    term_height = shutil.get_terminal_size().lines
    reserved = 8 + NEW_CHAT_HEIGHT + 1
    available = term_height - reserved

    # Viewport for session rows
    if selected <= 0:
        scroll_top, visible = 0, max(1, available // (SESSION_ROW_HEIGHT + 1))
    else:
        scroll_top, visible = _viewport(
            selected - 1, total_sessions, SESSION_ROW_HEIGHT + 1,
            term_height, reserved,
        )

    console.print()
    console.print(
        f"  [bold #b388ff]{repo.name}[/]"
        f"  [#777777]|[/]  [#80cbc4]{repo.branch_display}[/]"
        f"  [#777777]|[/]  [#777777]{repo.path}[/]"
    )

    hints = "up/down navigate  |  Enter select  |  r rename  |  d hide  |  Esc back"
    if total_sessions > visible:
        end = min(scroll_top + visible, total_sessions)
        hints += f"    [{scroll_top + 1}-{end}/{total_sessions}]"
    console.print(f"  [#777777]{hints}[/]")
    console.print()

    console.print("  ", _make_new_chat_row(selected == 0))

    visible_end = min(scroll_top + visible, total_sessions)
    for i in range(scroll_top, visible_end):
        session, s_hidden = display_list[i]
        console.print("  ", _make_session_row(session, selected == i + 1, s_hidden, labels))

    console.print()
    hidden_count = sum(1 for s in repo.sessions if s.session_id in hidden)
    if hidden_count > 0:
        state = "showing hidden" if show_hidden else f"{hidden_count} hidden, h to show"
        console.print(f"  [#777777]{state}[/]")
        console.print()


def _prompt_rename(session: Session) -> str | None:
    import re as _re
    console.print()
    try:
        label = console.input("  [bold #b388ff]Label this session[/] [#777777](empty to clear)[/]: ").strip()
        # Strip control characters to prevent terminal injection
        label = _re.sub(r'[\x00-\x1f\x7f-\x9f]', '', label)
        return label[:200] if label else ""
    except (EOFError, KeyboardInterrupt):
        return None


def _delete_session_file(session: Session) -> bool:
    """Permanently delete a session's .jsonl file."""
    import re as _re
    # Validate session_id is a UUID-like string (no path traversal)
    if not _re.match(r'^[a-zA-Z0-9_-]{30,}$', session.session_id):
        return False
    normalized = normalize_path_for_claude(session.project_path)
    for d in CLAUDE_PROJECTS_DIR.iterdir():
        if d.name.lower() == normalized.lower():
            jsonl = d / f"{session.session_id}.jsonl"
            # Ensure resolved path stays inside Claude's projects dir
            try:
                if not jsonl.resolve().is_relative_to(CLAUDE_PROJECTS_DIR.resolve()):
                    return False
                jsonl.unlink()
                return True
            except OSError:
                pass
    return False


def pick_session(repo: RepoInfo) -> tuple[str, str | None] | None:
    """Interactive session picker. Returns (path, session_id|None) or None for back."""
    config = load_config()
    max_shown = config.get("max_sessions_shown", 15)
    all_sessions = repo.sessions[:max_shown]
    show_hidden = False
    selected = 0

    # Cache these to avoid repeated file I/O on each render
    hidden = load_hidden_sessions()
    labels = load_session_labels()

    display_list = _build_display_list(all_sessions, show_hidden, hidden)
    total_items = 1 + len(display_list)

    _render(repo, display_list, selected, show_hidden, hidden, labels)

    while True:
        key = get_key()
        if key in ("escape", "backspace", "q"):
            return None
        elif key == "down":
            selected = min(selected + 1, total_items - 1)
        elif key == "up":
            selected = max(selected - 1, 0)
        elif key == "h":
            show_hidden = not show_hidden
            display_list = _build_display_list(all_sessions, show_hidden, hidden)
            total_items = 1 + len(display_list)
            selected = min(selected, total_items - 1)
        elif key == "r" and selected > 0:
            session, _ = display_list[selected - 1]
            label = _prompt_rename(session)
            if label is not None:
                if label:
                    set_session_label(session.session_id, label)
                    labels[session.session_id] = label
                else:
                    labels.pop(session.session_id, None)
                    save_session_labels(labels)
        elif key == "d" and selected > 0:
            session, s_hidden = display_list[selected - 1]
            if s_hidden:
                remove_hidden_session(session.session_id)
                hidden.discard(session.session_id)
            else:
                add_hidden_session(session.session_id)
                hidden.add(session.session_id)
            display_list = _build_display_list(all_sessions, show_hidden, hidden)
            total_items = 1 + len(display_list)
            selected = min(selected, total_items - 1)
        elif key == "D" and selected > 0:
            session, _ = display_list[selected - 1]
            console.print()
            console.print("  [bold red]WARNING: This will permanently delete the session file.[/]")
            console.print(f"  [#777777]{session.journey_display}[/]")
            try:
                answer = console.input("  [bold red]Type DELETE to confirm:[/] ")
                if answer.strip() == "DELETE":
                    _delete_session_file(session)
                    all_sessions = [s for s in all_sessions if s.session_id != session.session_id]
                    display_list = _build_display_list(all_sessions, show_hidden, hidden)
                    total_items = 1 + len(display_list)
                    selected = min(selected, total_items - 1)
            except (EOFError, KeyboardInterrupt):
                pass
        elif key == "enter":
            if selected == 0:
                return (repo.path, None)
            session, _ = display_list[selected - 1]
            return (repo.path, session.session_id)
        else:
            continue

        _render(repo, display_list, selected, show_hidden, hidden, labels)
