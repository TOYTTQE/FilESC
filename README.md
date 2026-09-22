# FilESC

Command-based file manager for Android (PyDroid 3) with SQLite bookmarks, 256-color image viewer, and tree/grep/find tools.
///
Командный файловый менеджер для Android (PyDroid 3) с закладками в SQLite, просмотром картинок в 256 цветов и инструментами tree/grep/find.

## Features / Возможности

- 📁 Two-panel file manager (L/R) — Две панели
- 📌 Bookmarks stored in SQLite — Закладки в SQLite
- 🖼 Image viewer (256 colors, half-blocks) — Просмотр картинок
- 🌳 Directory tree — Дерево каталогов
- 🔍 Find and Grep — Поиск по имени и содержимому
- 🎨 256-color output — Цветной вывод
- 📝 Command history with replay — История команд с повтором
- 💾 Trash instead of permanent delete — Корзина вместо удаления

## Commands / Команды

| Command | Description |
|---|---|
| `ls` | refresh current directory |
| `cd <path>` | change directory (`..`, `~`, `-`) |
| `b` | go up one level |
| `pwd` | show current path |
| `pane l` / `pane r` | switch active panel |
| `pane swap` | swap panels |
| `u` / `d` | cursor up / down |
| `sel <N>` | jump to row N |
| `open` / `e` | enter directory |
| `cp` | copy selected to other panel |
| `mv` | move selected to other panel |
| `rm` | delete (to trash) |
| `mkdir <name>` | create directory |
| `touch <name>` | create empty file |
| `rename <new>` | rename selected |
| `info` | details about selected file |
| `view` | show file (first 20 lines, numbered) |
| `image [file]` | show image (needs Pillow) |
| `find <mask>` | search files by mask |
| `grep <text> [mask]` | search inside files |
| `tree [depth]` | show directory tree |
| `bm add / go / rm / list` | bookmarks |
| `hist` / `hist <N>` / `hist top` | command history |
| `hidden on / off` | toggle hidden files |
| `q` | quit |

## Installation / Установка

1. Install [PyDroid 3](https://play.google.com/store/apps/details?id=ru.iiec.pydroid3) from Google Play.
2. Install Pillow:
