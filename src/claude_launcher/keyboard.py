"""Cross-platform keyboard input for inline TUI."""

import sys


def get_key() -> str | None:
    """Read a single keypress. Returns 'up','down','left','right','enter','escape','r', etc."""
    if sys.platform == "win32":
        import msvcrt

        key = msvcrt.getch()
        if key in (b"\xe0", b"\x00"):
            key2 = msvcrt.getch()
            mapping = {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}
            return mapping.get(key2)
        if key == b"\r":
            return "enter"
        if key == b"\x1b":
            return "escape"
        if key == b"\x03":
            return "escape"  # Ctrl+C
        try:
            return key.decode("utf-8", errors="ignore")
        except Exception:
            return None
    else:
        import tty
        import termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    mapping = {"A": "up", "B": "down", "C": "right", "D": "left"}
                    return mapping.get(ch3)
                return "escape"
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x03":
                return "escape"  # Ctrl+C
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
