#!/usr/bin/env python3
"""
FilESC v1.0 — command-based file manager for mobile terminal.
No physical keys, no hotkeys — just commands.
Uses SQLite for bookmarks + history.
Accurate RGB -> ANSI 256 color mapping (nearest color).
"""

import os
import sqlite3
import shutil
import json
from pathlib import Path

TRASH_DIR = Path.home() / ".filesc_trash"
DB_PATH = Path.home() / ".filesc.db"
OLD_JSON = Path.home() / ".filesc_config.json"
CLEAR = "\n" * 1000 + "\033[H\033[2J\033[3J"

# ═══════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКА ЦВЕТА ПОДСВЕТКИ КУРСОРА
# ═══════════════════════════════════════════════════════════════════════════════
HIGHLIGHT = "\033[44;37m"
# HIGHLIGHT = "\033[7m"
# HIGHLIGHT = "\033[43;30m"
# HIGHLIGHT = "\033[45;97m"
# HIGHLIGHT = "\033[100;97m"
# HIGHLIGHT = "\033[42;30m"
# HIGHLIGHT = "\033[44;97m"
# HIGHLIGHT = "\033[41;97m"
# HIGHLIGHT = "\033[47;30m"
# HIGHLIGHT = "\033[40;97m"

MSG_OK  = "\033[32;1m"
MSG_ERR = "\033[31;1m"
RESET   = "\033[0m"

HISTORY_MAX      = 500
TREE_MAX_PER_DIR = 10
TREE_MAX_LINES   = 50


# ─── Utils ───────────────────────────────────────────────────────────────────
def term_width(default=78):
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def human_size(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}T"


# ─── ANSI 256 palette + nearest-color search ─────────────────────────────────
def _build_palette():
    pal = []
    base = [
        (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
        (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
        (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
        (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ]
    pal.extend(base)
    for r in range(6):
        for g in range(6):
            for b in range(6):
                pal.append((r * 51, g * 51, b * 51))
    for i in range(24):
        v = 8 + i * 10
        pal.append((v, v, v))
    return pal


_PALETTE = _build_palette()
_CACHE = {}


def rgb_to_256(r, g, b):
    key = (r >> 2, g >> 2, b >> 2)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    best = 0
    best_dist = 1 << 30
    for i, (pr, pg, pb) in enumerate(_PALETTE):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_dist:
            best_dist = d
            best = i
    _CACHE[key] = best
    return best


# ─── Database ────────────────────────────────────────────────────────────────
def db_init():
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            uses INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()

    if OLD_JSON.exists():
        try:
            with open(OLD_JSON, "r", encoding="utf-8") as f:
                old = json.load(f)
            for name, path in old.get("bookmarks", {}).items():
                cur.execute(
                    "INSERT OR IGNORE INTO bookmarks(name, path) VALUES (?, ?)",
                    (name, path)
                )
            for cmd in old.get("history", []):
                cur.execute("INSERT INTO history(command) VALUES (?)", (cmd,))
            con.commit()
            OLD_JSON.rename(str(OLD_JSON) + ".bak")
        except Exception as e:
            print(f"  ! migration failed: {e}")

    con.close()


def db():
    return sqlite3.connect(str(DB_PATH))


# ─── Panel ───────────────────────────────────────────────────────────────────
class Panel:
    def __init__(self, path, show_hidden=False):
        self.path = Path(path).expanduser().resolve()
        self.items = []
        self.cursor = 0
        self.show_hidden = show_hidden
        self.refresh()

    def refresh(self):
        try:
            entries = []
            for p in self.path.iterdir():
                if not self.show_hidden and p.name.startswith("."):
                    continue
                entries.append(p)
            entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
            self.items = [Path("..")] + entries
        except (PermissionError, FileNotFoundError):
            self.items = [Path("..")]
        if self.items:
            self.cursor = max(0, min(self.cursor, len(self.items) - 1))
        else:
            self.cursor = 0

    def current(self):
        if not self.items:
            return None
        return self.items[self.cursor]

    def enter(self):
        item = self.current()
        if item is None:
            return None
        if item.name == "..":
            self.path = self.path.parent
        elif item.is_dir():
            self.path = item
        else:
            return f"  ! {item.name} is a file, use 'view'"
        self.cursor = 0
        self.refresh()
        return None

    def cd(self, target):
        target = target.strip()
        if target in ("~", ""):
            new = Path.home()
        elif target == "-":
            new = self.path.parent
        elif target.startswith("/"):
            new = Path(target)
        else:
            new = self.path / target
        try:
            new = new.expanduser().resolve()
            if new.is_dir():
                self.path = new
                self.cursor = 0
                self.refresh()
                return None
            else:
                return f"  ! not a directory: {new}"
        except Exception as e:
            return f"  ! {e}"


# ─── Render ──────────────────────────────────────────────────────────────────
def render(left, right, active, message, rows=10):
    print(CLEAR, end="")

    WIDTH = term_width()
    half = max(20, (WIDTH - 3) // 2)
    bar = "─" * half

    def make_title(panel, tag):
        name = str(panel.path)
        max_len = half - 4
        if len(name) > max_len:
            name = "…" + name[-(max_len - 1):]
        return ("┌" + tag + " " + name).ljust(half, "─")

    left_top = make_title(left, "L")
    right_top = make_title(right, "R")
    print(left_top[:-1] + "┬" + right_top[1:])
    print("├" + bar + "┼" + bar + "┤")

    def window(panel, n):
        total = len(panel.items)
        if total <= n:
            return 0
        if panel.cursor < n // 2:
            return 0
        if panel.cursor > total - n // 2 - 1:
            return max(0, total - n)
        return panel.cursor - n // 2

    lo = window(left, rows)
    ro = window(right, rows)

    for i in range(rows):
        cells = []
        for panel, off, is_active in ((left, lo, active == "L"),
                                      (right, ro, active == "R")):
            idx = off + i
            if idx < len(panel.items):
                item = panel.items[idx]
                is_cur = is_active and idx == panel.cursor

                name = item.name
                emoji = "📁" if item.is_dir() else "📄"
                tag = f"[{emoji}]"

                visible_tag = 6
                prefix = f"{idx+1:>3}. {name}"
                visible_len = len(prefix) + 1 + visible_tag

                if visible_len > half - 1:
                    excess = visible_len - (half - 1)
                    if len(name) > excess:
                        name = name[:len(name) - excess - 1] + "…"
                        prefix = f"{idx+1:>3}. {name}"
                        visible_len = len(prefix) + 1 + visible_tag

                body = f"{prefix} {tag}"
                pad = " " * max(0, half - 1 - visible_len)
                line = " " + body + pad

                if is_cur:
                    line = HIGHLIGHT + line + "\033[0m"

                cells.append(line)
            else:
                cells.append(" " * half)
        print("│" + cells[0] + "│" + cells[1] + "│")

    print("└" + bar + "┴" + bar + "┘")

    cur_panel = left if active == "L" else right
    cur = cur_panel.current()
    if cur:
        try:
            size = human_size(cur.stat().st_size) if cur.is_file() else "DIR"
        except Exception:
            size = "?"
        pos = f"{cur_panel.cursor + 1}/{len(cur_panel.items)}"
        line = f"  {active} | [{cur.name}] | {size} | {pos} | {cur_panel.path}"
    else:
        line = f"  {active} | (empty)"
    print(line[:WIDTH])

    if message:
        if message.startswith("  +"):
            print(MSG_OK + message[:WIDTH] + RESET)
        elif message.startswith("  !"):
            print(MSG_ERR + message[:WIDTH] + RESET)
        else:
            print(message[:WIDTH])


# ─── File commands ───────────────────────────────────────────────────────────
def cmd_cp(active_panel, other_panel):
    item = active_panel.current()
    if item is None or item.name == "..":
        return "  ! nothing to copy"
    try:
        dest = other_panel.path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
        other_panel.refresh()
        return f"  + copied -> {dest}"
    except Exception as e:
        return f"  ! {e}"


def cmd_mv(active_panel, other_panel):
    item = active_panel.current()
    if item is None or item.name == "..":
        return "  ! nothing to move"
    try:
        dest = other_panel.path / item.name
        shutil.move(str(item), str(dest))
        active_panel.refresh()
        other_panel.refresh()
        return f"  + moved -> {dest}"
    except Exception as e:
        return f"  ! {e}"


def cmd_rm(active_panel):
    item = active_panel.current()
    if item is None or item.name == "..":
        return "  ! nothing to delete"
    ans = input(f"  Delete '{item.name}'? (y/N): ").strip().lower()
    if ans != "y":
        return "  cancelled"
    try:
        TRASH_DIR.mkdir(exist_ok=True)
        target = TRASH_DIR / item.name
        i = 1
        while target.exists():
            target = TRASH_DIR / f"{item.name}.{i}"
            i += 1
        shutil.move(str(item), str(target))
        active_panel.refresh()
        return f"  + to trash -> {target}"
    except Exception as e:
        return f"  ! {e}"


def cmd_mkdir(active_panel, name):
    if not name:
        return "  ! specify a name"
    try:
        (active_panel.path / name).mkdir()
        active_panel.refresh()
        return f"  + created: {name}"
    except Exception as e:
        return f"  ! {e}"


def cmd_touch(active_panel, name):
    if not name:
        return "  ! specify a name"
    try:
        (active_panel.path / name).touch()
        active_panel.refresh()
        return f"  + created: {name}"
    except Exception as e:
        return f"  ! {e}"


def cmd_rename(active_panel, new_name):
    item = active_panel.current()
    if item is None or item.name == "..":
        return "  ! nothing to rename"
    if not new_name:
        return "  ! specify new name"
    try:
        old = item.name
        item.rename(active_panel.path / new_name)
        active_panel.refresh()
        return f"  + {old} -> {new_name}"
    except Exception as e:
        return f"  ! {e}"


def cmd_view(active_panel):
    item = active_panel.current()
    if item is None or not item.is_file():
        return "  ! select a file"
    try:
        lines = []
        with open(item, "r", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 20:
                    lines.append("  ... (truncated at 20 lines)")
                    break
                lines.append(f"  \033[2m{i+1:>3}\033[0m | {line.rstrip()}")
        print()
        for l in lines:
            print(l[:term_width()])
        input("  [Enter to continue]")
        return None
    except Exception as e:
        return f"  ! {e}"


def cmd_info(active_panel):
    item = active_panel.current()
    if item is None:
        return "  ! empty"
    try:
        st = item.stat()
        print()
        print(f"  Name: {item.name}")
        print(f"  Path: {item}")
        print(f"  Type: {'dir' if item.is_dir() else 'file'}")
        print(f"  Size: {human_size(st.st_size)}")
        print(f"  Mode: {oct(st.st_mode)[-3:]}")
        input("  [Enter to continue]")
        return None
    except Exception as e:
        return f"  ! {e}"


def cmd_find(active_panel, mask):
    if not mask:
        return "  ! specify a mask, e.g.: find *.txt"
    found = list(active_panel.path.rglob(mask))
    if not found:
        return "  nothing found"
    print()
    for i, p in enumerate(found[:50]):
        try:
            rel = p.relative_to(active_panel.path)
        except Exception:
            rel = p
        print(f"  {i+1}. {rel}"[:term_width()])
    if len(found) > 50:
        print(f"  ... and {len(found) - 50} more")
    input("  [Enter to continue]")
    return None


def cmd_grep(active_panel, arg):
    if not arg:
        return "  ! grep <text> [mask]"
    parts = arg.split(maxsplit=1)
    needle = parts[0].lower()
    mask = parts[1] if len(parts) > 1 else "*"

    hits = []
    MAX_HITS = 100
    MAX_SIZE = 1024 * 1024

    for item in active_panel.items[1:]:
        if not item.is_file():
            continue
        if mask != "*" and not item.match(mask):
            continue
        try:
            if item.stat().st_size > MAX_SIZE:
                continue
            with open(item, "r", errors="replace") as f:
                for i, line in enumerate(f):
                    if needle in line.lower():
                        hits.append(f"{item.name}:{i+1}: {line.rstrip()}")
                        if len(hits) >= MAX_HITS:
                            break
        except Exception:
            continue
        if len(hits) >= MAX_HITS:
            break

    if not hits:
        return "  nothing found"

    print()
    for h in hits:
        print(f"  {h}"[:term_width()])
    if len(hits) >= MAX_HITS:
        print("  ... (more results truncated)")
    input("  [Enter to continue]")
    return None


def cmd_image(active_panel, arg):
    try:
        from PIL import Image
    except ImportError:
        return "  ! Pillow not installed (pip install pillow)"

    item = active_panel.current()
    if arg:
        target = (active_panel.path / arg).expanduser()
    elif item and item.is_file():
        target = item
    else:
        return "  ! select a file or: image <filename>"

    if not target.is_file():
        return f"  ! no such file: {target}"

    try:
        img = Image.open(target).convert("RGB")
        orig_w, orig_h = img.size

        WIDTH = term_width()
        target_w = WIDTH - 4
        target_h = int((orig_h / orig_w) * target_w / 2)
        if target_h < 1:
            target_h = 1

        img = img.resize((target_w, target_h * 2))

        print()
        print(f"  {target.name}  {orig_w}x{orig_h} -> {target_w}x{target_h*2} (px)")
        print()

        for y in range(target_h):
            line = "  "
            for x in range(target_w):
                top = img.getpixel((x, y * 2))
                bot = img.getpixel((x, y * 2 + 1))
                tcode = rgb_to_256(*top)
                bcode = rgb_to_256(*bot)
                line += f"\033[38;5;{tcode}m\033[48;5;{bcode}m▀"
            line += "\033[0m"
            print(line)

        print()
        input("  [Enter to continue]")
        return None
    except Exception as e:
        return f"  ! {e}"


def cmd_play(active_panel, arg):
    return "  ! This file is not supported in FilESC"


def cmd_video(active_panel, arg):
    return "  ! This file is not supported in FilESC"


def cmd_audio(active_panel, arg):
    return "  ! This file is not supported in FilESC"


# ─── Tree ────────────────────────────────────────────────────────────────────
def cmd_tree(active_panel, arg):
    depth = 2
    if arg:
        if arg.isdigit():
            depth = int(arg)
        else:
            return "  ! tree [depth]   e.g. tree 3"

    lines = []
    root = active_panel.path
    lines.append(f"  {root}/")
    truncated = False

    def walk(path, prefix, level):
        nonlocal truncated
        if level > depth or truncated:
            return
        try:
            entries = sorted(
                [p for p in path.iterdir()
                 if active_panel.show_hidden or not p.name.startswith(".")],
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except (PermissionError, FileNotFoundError):
            return

        shown = 0
        for i, item in enumerate(entries):
            if truncated:
                return
            if item.is_symlink():
                continue
            if shown >= TREE_MAX_PER_DIR:
                remaining = len(entries) - shown
                lines.append(f"  {prefix}└── ... and {remaining} more")
                if len(lines) > TREE_MAX_LINES:
                    truncated = True
                return
            last = (i == len(entries) - 1)
            branch = "└── " if last else "├── "
            name = item.name + ("/" if item.is_dir() else "")
            lines.append(f"  {prefix}{branch}{name}")
            if len(lines) > TREE_MAX_LINES:
                truncated = True
                return
            shown += 1
            if item.is_dir():
                ext = "    " if last else "│   "
                walk(item, prefix + ext, level + 1)

    try:
        walk(root, "", 1)
    except Exception as e:
        return f"  ! {e}"

    print()
    for l in lines[:TREE_MAX_LINES]:
        print(l[:term_width()])
    if truncated or len(lines) > TREE_MAX_LINES:
        print("  ... (truncated — increase depth or cd deeper)")
    input("  [Enter to continue]")
    return None


# ─── History (SQLite) ────────────────────────────────────────────────────────
def hist_add(command):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT INTO history(command) VALUES (?)", (command,))
    cur.execute("""
        DELETE FROM history WHERE id NOT IN (
            SELECT id FROM history ORDER BY id DESC LIMIT ?
        )
    """, (HISTORY_MAX,))
    con.commit()
    con.close()


def cmd_hist(arg):
    con = db()
    cur = con.cursor()

    if arg == "clear":
        cur.execute("DELETE FROM history")
        con.commit()
        con.close()
        return "  + history cleared"

    if arg == "top":
        cur.execute("""
            SELECT command, COUNT(*) as n
            FROM history
            GROUP BY command
            ORDER BY n DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
        con.close()
        if not rows:
            return "  (history empty)"
        print()
        for i, (cmd, n) in enumerate(rows, 1):
            print(f"  {i:>2}. [{n}x] {cmd}"[:term_width()])
        input("  [Enter to continue]")
        return None

    if arg.startswith("grep "):
        needle = arg[5:].strip().lower()
        if not needle:
            con.close()
            return "  ! hist.grep <text>"
        cur.execute("""
            SELECT command FROM history
            WHERE LOWER(command) LIKE ?
            ORDER BY id DESC LIMIT 50
        """, (f"%{needle}%",))
        rows = cur.fetchall()
        con.close()
        if not rows:
            return "  nothing found"
        print()
        for i, (cmd,) in enumerate(rows, 1):
            print(f"  {i:>3}. {cmd}"[:term_width()])
        input("  [Enter to continue]")
        return None

    if arg.isdigit():
        n = int(arg)
        cur.execute("SELECT command FROM history ORDER BY id ASC")
        rows = [r[0] for r in cur.fetchall()]
        con.close()
        if 1 <= n <= len(rows):
            return f"__
