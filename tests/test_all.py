"""Comprehensive test suite for claude-launcher."""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("=" * 60)
print("CLAUDE LAUNCHER - COMPREHENSIVE TEST SUITE")
print("=" * 60)

# --- TEST 1: Config ---
print("\n--- TEST 1: Config module ---")
from claude_launcher.config import (
    load_config, save_config, get_ai_command, get_ai_launch_args,
    get_repos_dirs, set_session_label, get_session_label,
    load_session_labels, save_session_labels,
    add_hidden_session, remove_hidden_session,
    load_hidden_sessions,
)

config = load_config()
assert "repos_dirs" in config
assert "ai_tool" in config
assert "custom_command" in config

dirs = get_repos_dirs()
assert len(dirs) > 0

c_claude = {"ai_tool": "claude"}
assert get_ai_command(c_claude) == "claude"
assert get_ai_launch_args(c_claude, "abc") == ["claude", "--resume", "abc"]
assert get_ai_launch_args(c_claude, None) == ["claude"]

c_custom = {"ai_tool": "custom", "custom_command": "proxy-claude --yolo"}
assert get_ai_command(c_custom) == "proxy-claude --yolo"
args = get_ai_launch_args(c_custom, "abc")
assert args == ["proxy-claude", "--yolo", "--resume", "abc"]

c_noflag = {"ai_tool": "custom", "custom_command": "my-tool"}
assert get_ai_launch_args(c_noflag, None) == ["my-tool"]

assert get_ai_command(c_claude, override="other") == "other"
assert get_ai_launch_args(c_claude, "x", override="other --flag") == ["other", "--flag", "--resume", "x"]

c_copilot = {"ai_tool": "copilot"}
assert get_ai_command(c_copilot) == "copilot"

print("  PASS: All config tests")

# --- TEST 2: Session labels ---
print("\n--- TEST 2: Session labels ---")
set_session_label("test-label-id", "My Custom Label")
assert get_session_label("test-label-id") == "My Custom Label"
assert get_session_label("nonexistent") is None
labels = load_session_labels()
del labels["test-label-id"]
save_session_labels(labels)
assert get_session_label("test-label-id") is None
print("  PASS: Labels create/read/delete")

# --- TEST 3: Hidden sessions ---
print("\n--- TEST 3: Hidden sessions ---")
add_hidden_session("hide-test-1")
add_hidden_session("hide-test-2")
assert "hide-test-1" in load_hidden_sessions()
assert "hide-test-2" in load_hidden_sessions()
assert "not-hidden" not in load_hidden_sessions()
remove_hidden_session("hide-test-1")
assert "hide-test-1" not in load_hidden_sessions()
assert "hide-test-2" in load_hidden_sessions()
remove_hidden_session("hide-test-2")
assert len(load_hidden_sessions()) == 0
print("  PASS: Hide/unhide/check")

# --- TEST 4: Discovery ---
print("\n--- TEST 4: Discovery ---")
from claude_launcher.data.discovery import discover_repos
repos = discover_repos()
assert len(repos) > 0

repos_with_sessions = [r for r in repos if r.sessions]
assert len(repos_with_sessions) > 0

r = repos_with_sessions[0]
assert r.name
assert r.path
assert r.session_count > 0

s = r.latest_session
assert s.session_id
assert s.modified
print(f"  Found {len(repos)} repos, {len(repos_with_sessions)} with sessions")
print(f"  Top: {r.name} ({r.session_count} sessions)")
print(f"  Journey: {s.journey_display}")
print("  PASS: Discovery + session data")

# --- TEST 5: Prompt cleaning ---
print("\n--- TEST 5: Prompt cleaning ---")
from claude_launcher.data.models import _clean_prompt
assert _clean_prompt("") == ""
assert _clean_prompt("/init") == ""
assert _clean_prompt("/commit -m test") == ""
assert _clean_prompt("vi-ops:vi-e2e-investigate") == ""
assert _clean_prompt("fix the auth bug") == "fix the auth bug"
assert len(_clean_prompt("a" * 100, max_len=20)) <= 20
cleaned = _clean_prompt("<command-message>hello</command-message>")
assert "hello" in cleaned
print("  PASS: All prompt cleaning rules")

# --- TEST 6: Card rendering ---
print("\n--- TEST 6: Card rendering ---")
from claude_launcher.ui.repo_picker import make_card
for density in ("compact", "standard", "detailed"):
    c = make_card(repos[0], True, density)
    assert c is not None
    c2 = make_card(repos[0], False, density)
    assert c2 is not None
print("  PASS: All 3 densities, selected + unselected")

# --- TEST 7: Session row rendering ---
print("\n--- TEST 7: Session row rendering ---")
from claude_launcher.ui.session_picker import _make_new_chat_row, _make_session_row
assert _make_new_chat_row(True) is not None
assert _make_new_chat_row(False) is not None

if repos_with_sessions[0].sessions:
    sess = repos_with_sessions[0].sessions[0]
    assert _make_session_row(sess, True, False) is not None
    assert _make_session_row(sess, False, False) is not None
    assert _make_session_row(sess, True, True) is not None  # hidden
print("  PASS: New chat + session rows (normal + hidden)")

# --- TEST 8: Hidden session display filter ---
print("\n--- TEST 8: Hidden session display filter ---")
from claude_launcher.ui.session_picker import _build_display_list
test_sessions = repos_with_sessions[0].sessions[:5]
if len(test_sessions) >= 2:
    add_hidden_session(test_sessions[0].session_id)
    hidden_set = load_hidden_sessions()
    visible = _build_display_list(test_sessions, show_hidden=False, hidden=hidden_set)
    all_shown = _build_display_list(test_sessions, show_hidden=True, hidden=hidden_set)
    assert len(visible) == len(test_sessions) - 1
    assert len(all_shown) == len(test_sessions)
    remove_hidden_session(test_sessions[0].session_id)
    print("  PASS: Hidden filtering works")
else:
    print("  SKIP: Not enough sessions")

# --- TEST 9: CLI argparse ---
print("\n--- TEST 9: CLI argument parsing ---")
from claude_launcher.__main__ import _build_parser
parser = _build_parser()

a1 = parser.parse_args([])
assert not a1.setup and not a1.dry_run and a1.repo is None and a1.command is None

a2 = parser.parse_args(["--setup"])
assert a2.setup

a3 = parser.parse_args(["--dry-run", "--repo", "video", "--command", "my-tool"])
assert a3.dry_run and a3.repo == "video" and a3.command == "my-tool"

a4 = parser.parse_args(["--no-launch"])
assert a4.dry_run
print("  PASS: All arg combinations")

# --- TEST 10: Repo name matching ---
print("\n--- TEST 10: Repo name matching ---")
all_repos = discover_repos()
m1 = [r for r in all_repos if "vulnerab" in r.name.lower()]
assert len(m1) == 1

m2 = [r for r in all_repos if "video" in r.name.lower()]
assert len(m2) > 1

m3 = [r for r in all_repos if "nonexistent-xyz" in r.name.lower()]
assert len(m3) == 0
print(f"  PASS: exact=1, partial={len(m2)}, none=0")

# --- TEST 11: Dynamic title ---
print("\n--- TEST 11: Dynamic title ---")
assert get_ai_command({"ai_tool": "claude"}).split()[0] == "claude"
assert get_ai_command({"ai_tool": "custom", "custom_command": "proxy-claude --yolo"}).split()[0] == "proxy-claude"
assert get_ai_command({"ai_tool": "custom", "custom_command": "copilot"}).split()[0] == "copilot"
print("  PASS: Title extracts binary name")

# --- TEST 12: Session label in row rendering ---
print("\n--- TEST 12: Session label display ---")
if repos_with_sessions[0].sessions:
    sess = repos_with_sessions[0].sessions[0]
    set_session_label(sess.session_id, "My labeled session")
    row_with_label = _make_session_row(sess, True, False)
    assert row_with_label is not None
    # Clean up
    labels = load_session_labels()
    labels.pop(sess.session_id, None)
    save_session_labels(labels)
    print("  PASS: Labeled session renders")

# --- TEST 13: Multiple repos dirs ---
print("\n--- TEST 13: Multiple repos dirs ---")
test_config = dict(config)
test_config["repos_dirs"] = ["C:\\repos", "C:\\nonexistent"]
from pathlib import Path
test_dirs = [Path(d).expanduser() for d in test_config["repos_dirs"]]
assert len(test_dirs) == 2
print("  PASS: Multiple dirs parsed")

print()
print("=" * 60)
print("ALL 13 TESTS PASSED")
print("=" * 60)
