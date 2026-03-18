"""Repo picker -- Rich card grid with arrow-key navigation and viewport scrolling."""

from __future__ import annotations

import shutil

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from claude_launcher.config import console
from claude_launcher.data.models import RepoInfo, truncate
from claude_launcher.keyboard import get_key

COLS = 3
CARD_WIDTH = 30

# Card heights per density (panel height, row height including gap)
_HEIGHTS = {"compact": (5, 6), "detailed": (7, 8), "standard": (6, 7)}


def _viewport(selected_idx: int, total: int, item_height: int, term_height: int, reserved: int) -> tuple[int, int]:
    """Calculate (scroll_top, visible_count) for a scrollable list."""
    visible = max(1, (term_height - reserved) // item_height)
    half = visible // 2
    top = max(0, selected_idx - half)
    top = min(top, max(0, total - visible))
    return top, visible


def make_card(repo: RepoInfo, is_selected: bool, density: str = "standard") -> Panel:
    """Build a Rich Panel card for a repo."""
    chat_count = repo.session_count
    chat_str = f"{chat_count} chat{'s' if chat_count != 1 else ''}"
    branch = repo.branch_display

    if is_selected:
        border, name_style, branch_style = "bold #b388ff", "bold white", "#80cbc4"
        chat_style = "bold #a5d6a7" if chat_count > 0 else "dim"
        topic_style, bx, subtitle = "#e0e0e0", box.HEAVY, "[bold #b388ff]> enter[/]"
    else:
        border, name_style, branch_style = "#555555", "#cccccc", "#6a8a82"
        chat_style = "#7a9a72" if chat_count > 0 else "#555555"
        topic_style, bx, subtitle = "#777777", box.ROUNDED, None

    name = truncate(repo.name, CARD_WIDTH - 4)

    content = Text()
    content.append(f" {name}\n", style=name_style)
    content.append(f" ~ {branch}\n", style=branch_style)

    panel_height, _ = _HEIGHTS.get(density, _HEIGHTS["standard"])

    content.append(f" [{chat_str}]", style=chat_style)
    if density != "compact":
        age = repo.latest_session.age_display if repo.latest_session else ""
        if age:
            content.append(f"  {age}", style="#777777")
        content.append("\n")
        topic = truncate(repo.latest_topic, CARD_WIDTH - 4) if repo.latest_topic else ""
        if topic:
            content.append(f" {topic}", style=topic_style)
        elif density == "detailed":
            content.append(" --", style="#555555")

    return Panel(
        content, border_style=border, box=bx,
        width=CARD_WIDTH, height=panel_height,
        padding=(0, 0), subtitle=subtitle, subtitle_align="right",
    )


def render_grid(repos: list[RepoInfo], selected: int, density: str = "standard", tool_name: str = "claude"):
    """Render a viewport of the repo grid that fits the terminal."""
    console.clear()
    _, row_height = _HEIGHTS.get(density, _HEIGHTS["standard"])

    total_rows = (len(repos) + COLS - 1) // COLS
    selected_row = selected // COLS
    scroll_top, visible_rows = _viewport(
        selected_row, total_rows, row_height,
        shutil.get_terminal_size().lines, 7,
    )

    console.print()
    console.print(f"  [bold #b388ff]{tool_name} Workspace Launcher[/]")

    if total_rows > visible_rows:
        end = min(scroll_top + visible_rows, total_rows)
        console.print(
            f"  [#777777]arrows navigate  |  Enter select  |  Esc quit[/]"
            f"    [#555555][{scroll_top + 1}-{end}/{total_rows} rows][/]"
        )
    else:
        console.print("  [#777777]arrows navigate  |  Enter select  |  Esc quit[/]")
    console.print()

    for row_idx in range(scroll_top, min(scroll_top + visible_rows, total_rows)):
        row_start = row_idx * COLS
        chunk = repos[row_start: row_start + COLS]

        table = Table(
            show_header=False, show_edge=False, show_lines=False,
            box=None, padding=0, pad_edge=False,
        )
        for _ in range(COLS):
            table.add_column(width=CARD_WIDTH + 2, no_wrap=True)

        cards = [make_card(repo, row_start + i == selected, density) for i, repo in enumerate(chunk)]
        while len(cards) < COLS:
            cards.append("")
        table.add_row(*cards)
        console.print("  ", table)

    console.print()
    if repos and 0 <= selected < len(repos):
        r = repos[selected]
        branch = r.current_branch or "--"
        age = r.latest_session.age_display if r.latest_session else "never"
        console.print(
            f"  [#777777]repo:[/]  [bold white]{r.name}[/]"
            f"  [#777777]|[/]  [#80cbc4]{branch}[/]"
            f"  [#777777]|[/]  [#a5d6a7]{r.session_count} chats[/]"
            f"  [#777777]|[/]  [#777777]last active: {age}[/]"
        )
    console.print()


def pick_repo(repos: list[RepoInfo], density: str = "standard", tool_name: str = "claude") -> RepoInfo | None:
    """Interactive repo picker. Returns selected repo or None if cancelled."""
    if not repos:
        console.print("  [dim]No repos found.[/]\n")
        return None

    selected = 0
    num = len(repos)
    render_grid(repos, selected, density, tool_name)

    while True:
        key = get_key()
        if key == "escape":
            console.clear()
            console.print("\n  [dim]Cancelled.[/]\n")
            return None
        elif key == "right":
            selected = min(selected + 1, num - 1)
        elif key == "left":
            selected = max(selected - 1, 0)
        elif key == "down":
            selected = min(selected + COLS, num - 1)
        elif key == "up":
            selected = max(selected - COLS, 0)
        elif key == "enter":
            return repos[selected]
        else:
            continue
        render_grid(repos, selected, density, tool_name)
