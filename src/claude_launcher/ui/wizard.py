"""Setup wizard -- interactive visual configuration with live previews."""

from __future__ import annotations

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich import box

from claude_launcher.config import load_config, save_config, DEFAULT_REPOS_DIR, console


GROUPING_PREVIEWS = {
    "chronological": """
  +---------------------------------------------------+
  |  3h ago  |  66 msgs  |  main                      |
  |  "fix responsive layout"  ->  "add breakpoints.." |
  +---------------------------------------------------+
  |  1d ago  |  85 msgs  |  feat/auth                 |
  |  "fix token refresh"  ->  "add tests for.."       |
  +---------------------------------------------------+""",
    "by_branch": """
  -- main --------------------------------------------------
  |  3h ago  |  66 msgs  |  "fix responsive layout..."     |
  |  3d ago  |  34 msgs  |  "set up CI pipeline"            |
  -- feat/auth ----------------------------------------------
  |  1d ago  |  85 msgs  |  "fix token refresh"            |""",
    "by_time_period": """
  -- Today --------------------------------------------------
  |  3h ago  |  66 msgs  |  "fix responsive layout..."     |
  -- This Week ----------------------------------------------
  |  1d ago  |  85 msgs  |  "fix token refresh"            |
  |  3d ago  |  34 msgs  |  "set up CI pipeline"            |
  -- Older --------------------------------------------------
  |  2w ago  |  12 msgs  |  "initial project setup"        |""",
}

DENSITY_PREVIEWS = {
    "compact": """
  +----------------------------------+
  |  my-web-app                      |
  |  ~ main        [24 chats]       |
  +----------------------------------+
  2 lines per card, minimal info""",
    "standard": """
  +----------------------------------+
  |  my-web-app                      |
  |  ~ main                         |
  |  [24 chats]  3h ago             |
  |  "fix responsive layout..."     |
  +----------------------------------+
  4 lines per card: branch, chats, age, topic""",
    "detailed": """
  +----------------------------------+
  |  my-web-app                      |
  |  ~ main                         |
  |  [24 chats]  3h ago             |
  |  "fix responsive layout..."     |
  +----------------------------------+
  4 lines per card, same as standard + more room""",
}


def run_wizard(force: bool = False):
    """Run the interactive setup wizard."""
    config = load_config()

    console.clear()
    console.print()
    console.print("  [bold #b388ff]Claude Launcher Setup[/]")
    console.print("  [#777777]Configure how your launcher looks and behaves.[/]")
    console.print("  [#777777]You can re-run this anytime with: cl --setup[/]")
    console.print()

    # -- Step 1: Repos directories --
    console.print("  [bold white]Step 1/6[/]  [#777777]Repos directories[/]")
    console.print("  [#777777]Enter one or more directories, comma-separated.[/]")
    console.print()

    current_dirs = config.get("repos_dirs", [str(DEFAULT_REPOS_DIR)])
    default_str = ", ".join(current_dirs)

    repos_input = inquirer.text(
        message="Repos directories:",
        default=default_str,
        qmark="  >",
    ).execute()

    dirs = [d.strip() for d in repos_input.split(",") if d.strip()]
    config["repos_dirs"] = dirs if dirs else [str(DEFAULT_REPOS_DIR)]
    console.print()

    # -- Step 2: AI tool selection --
    console.print("  [bold white]Step 2/6[/]  [#777777]AI tool[/]")
    console.print("  [#777777]Sessions and repos always come from Claude Code's history.[/]")
    console.print("  [#777777]Custom commands let you use a wrapper (e.g. proxy-claude, copilot).[/]")
    console.print()

    ai_tool = inquirer.select(
        message="Which command should launch?",
        choices=[
            {"name": "Claude Code -- the 'claude' CLI (default)", "value": "claude"},
            {"name": "Custom command -- specify your own (e.g. proxy-claude, copilot)", "value": "custom"},
        ],
        default=config.get("ai_tool", "claude"),
        pointer="  >",
        qmark="  ",
    ).execute()
    config["ai_tool"] = ai_tool

    if ai_tool == "custom":
        custom_cmd = inquirer.text(
            message="Custom command name:",
            default=config.get("custom_command", "claude"),
            qmark="  >",
        ).execute()
        config["custom_command"] = custom_cmd.strip()
    console.print()

    # -- Step 3: Session grouping --
    console.print("  [bold white]Step 3/6[/]  [#777777]Session list grouping[/]")
    console.print()

    for name, preview in GROUPING_PREVIEWS.items():
        label = name.replace("_", " ").title()
        console.print(f"  [bold #b388ff]{label}:[/]")
        console.print(preview)
        console.print()

    grouping = inquirer.select(
        message="How should sessions be grouped?",
        choices=[
            {"name": "Chronological -- simple list by time (recommended)", "value": "chronological"},
            {"name": "By Branch -- group under git branch", "value": "by_branch"},
            {"name": "By Time Period -- Today / This Week / Older", "value": "by_time_period"},
        ],
        default=config.get("session_grouping", "chronological"),
        pointer="  >",
        qmark="  ",
    ).execute()
    config["session_grouping"] = grouping
    console.print()

    # -- Step 4: Sort order --
    console.print("  [bold white]Step 4/6[/]  [#777777]Session sort order[/]")
    console.print()

    sort_order = inquirer.select(
        message="How should sessions be sorted?",
        choices=[
            {"name": "Most recent first (recommended)", "value": "recent_first"},
            {"name": "Most messages first", "value": "most_messages"},
        ],
        default=config.get("session_sort", "recent_first"),
        pointer="  >",
        qmark="  ",
    ).execute()
    config["session_sort"] = sort_order
    console.print()

    # -- Step 5: Card density --
    console.print("  [bold white]Step 5/6[/]  [#777777]Repo card density[/]")
    console.print()

    for name, preview in DENSITY_PREVIEWS.items():
        console.print(f"  [bold #b388ff]{name.title()}:[/]")
        console.print(preview)
        console.print()

    density = inquirer.select(
        message="How much info per repo card?",
        choices=[
            {"name": "Compact -- name + branch + chats", "value": "compact"},
            {"name": "Standard -- adds last active + topic (recommended)", "value": "standard"},
            {"name": "Detailed -- same with more room", "value": "detailed"},
        ],
        default=config.get("card_density", "standard"),
        pointer="  >",
        qmark="  ",
    ).execute()
    config["card_density"] = density
    console.print()

    # -- Step 6: Show empty repos --
    console.print("  [bold white]Step 6/6[/]  [#777777]Show empty repos?[/]")
    console.print()

    show_empty = inquirer.confirm(
        message="Show repos that have no sessions?",
        default=config.get("show_empty_repos", True),
        qmark="  ",
    ).execute()
    config["show_empty_repos"] = show_empty
    console.print()

    # -- Save --
    config["setup_complete"] = True
    save_config(config)

    console.print("  [bold green]>>  Setup complete![/]")
    console.print("  [#777777]Config saved to ~/.claude-launcher/config.json[/]")
    console.print("  [#777777]Run 'cl --setup' anytime to reconfigure.[/]")
    console.print()

    return config
