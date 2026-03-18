"""Entry point for claude-launcher."""

import argparse
import os
import shutil
import subprocess
import sys

from claude_launcher.config import console


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cl",
        description=(
            "Claude Launcher -- pick a repo, resume a session, get to work.\n"
            "A terminal UI for quickly launching Claude Code (or custom tools)\n"
            "in any of your repos with session resume support."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  cl                    Launch the interactive picker\n"
            "  cl --setup            Run the configuration wizard\n"
            "  cl --repo video       Jump to sessions for a repo matching 'video'\n"
            "  cl --dry-run          Show the command without executing\n"
            "  cl --command proxy-claude   Use a custom command instead of claude\n"
        ),
    )
    parser.add_argument("--setup", action="store_true", help="Run the configuration wizard")
    parser.add_argument("--dry-run", "--no-launch", action="store_true", help="Print the launch command without executing it")
    parser.add_argument("--repo", type=str, default=None, help="Skip repo picker -- jump to sessions for a repo (partial match)")
    parser.add_argument("--command", type=str, default=None, help="Override the AI tool command (e.g. proxy-claude)")
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    try:
        _run(args)
    except KeyboardInterrupt:
        console.print("\n  [dim]Interrupted.[/]\n")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n  [bold red]Error:[/] {e}\n")
        sys.exit(1)


def _run(args, repos=None):
    from claude_launcher.config import load_config, get_ai_launch_args, get_ai_command

    if args.setup:
        from claude_launcher.ui.wizard import run_wizard
        run_wizard(force=True)
        return

    config = load_config()
    if not config.get("setup_complete"):
        from claude_launcher.ui.wizard import run_wizard
        config = run_wizard()

    # Discover repos (or reuse from previous back-navigation)
    if repos is None:
        from claude_launcher.data.discovery import discover_repos
        repos = discover_repos()

    if not repos:
        dirs = config.get("repos_dirs", [])
        console.print(f"\n  [dim]No repos found in {dirs}[/]")
        console.print("  [dim]Run 'cl --setup' to configure your repos directory.[/]\n")
        return

    # Filter empty repos if configured
    if not config.get("show_empty_repos", False):
        filtered = [r for r in repos if r.sessions]
        if filtered:
            repos = filtered

    # Determine display name for the title (binary name only, no flags)
    tool_name = get_ai_command(config, override=args.command).split()[0]

    # --repo: skip picker
    if args.repo:
        query = args.repo.lower()
        matches = [r for r in repos if query in r.name.lower()]
        if not matches:
            console.print(f"\n  [bold red]No repo matching '{args.repo}' found.[/]\n")
            console.print("  Available repos:")
            for r in repos[:10]:
                console.print(f"    {r.name}")
            if len(repos) > 10:
                console.print(f"    ... and {len(repos) - 10} more")
            console.print()
            return
        elif len(matches) == 1:
            repo = matches[0]
        else:
            from claude_launcher.ui.repo_picker import pick_repo
            console.print(f"\n  [#777777]Multiple repos match '{args.repo}':[/]\n")
            repo = pick_repo(matches, density=config.get("card_density", "standard"), tool_name=tool_name)
            if repo is None:
                return
    else:
        from claude_launcher.ui.repo_picker import pick_repo
        repo = pick_repo(repos, density=config.get("card_density", "standard"), tool_name=tool_name)
        if repo is None:
            return

    # Session picker
    from claude_launcher.ui.session_picker import pick_session
    result = pick_session(repo)
    if result is None:
        # User pressed back -- re-show repo picker without re-discovering
        _run(args, repos=repos)
        return

    repo_path, session_id = result
    cmd = get_ai_launch_args(config, session_id, override=args.command)
    cmd_str = " ".join(cmd)

    # --dry-run
    if args.dry_run:
        console.print()
        console.print(f'  cd "{repo_path}" && {cmd_str}')
        console.print()
        return

    # Verbose launch confirmation
    console.clear()
    console.print()
    console.print("  [bold green]>>  Ready to launch[/]")
    console.print()
    console.print(f"  [#777777]repo:[/]     [bold white]{repo.name}[/]")
    console.print(f"  [#777777]path:[/]     [#80cbc4]{repo_path}[/]")
    console.print(f"  [#777777]branch:[/]   [#80cbc4]{repo.current_branch or '--'}[/]")

    if session_id:
        session = next((s for s in repo.sessions if s.session_id == session_id), None)
        if session:
            from claude_launcher.config import get_session_label
            label = get_session_label(session_id)
            display = label or session.journey_display
            console.print(f"  [#777777]session:[/]  [bold white]{display}[/]")
            console.print(f"  [#777777]messages:[/] [white]{session.message_count}[/]")
            console.print(f"  [#777777]last:[/]     [white]{session.age_display}[/]")
    else:
        console.print(f"  [#777777]session:[/]  [bold #a5d6a7]new chat[/]")

    console.print()
    console.print(f'  [#777777]command:[/]  [bold]cd "{repo_path}" && {cmd_str}[/]')
    console.print()
    console.print("  [#777777]launching...[/]")
    console.print()

    # Check if command binary exists
    binary = cmd[0]
    if not shutil.which(binary):
        console.print(f"  [bold red]Error:[/] '{binary}' not found on PATH.")
        console.print(f"  [#777777]Install it or use --command to specify a different tool.[/]\n")
        return

    # Launch
    os.chdir(repo_path)
    if sys.platform == "win32":
        # Resolve full path to binary to avoid needing shell=True (prevents injection)
        binary_path = shutil.which(binary)
        if binary_path:
            cmd[0] = binary_path
        sys.exit(subprocess.call(cmd))
    else:
        os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
