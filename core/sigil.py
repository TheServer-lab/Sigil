#!/usr/bin/env python3
"""
Sigil engine — full version with:
- persistent aliases/variables stored in C:\\Sigil (per-profile .sigilrc files)
- profile management (prof)
- save/reload rc (svrc, rrc)
- many utility commands
- 'pse [message]' pause command (optional message)
- Plugin system: .sigin packages, pin/prv commands, plugin registration
"""

from __future__ import annotations
import sys
import os
import shutil
import subprocess
import tempfile
import uuid
import time
import random
import webbrowser
from typing import List, Tuple

# added imports for plugin system
import zipfile
import runpy
import json
import re

# platform keypress utilities
try:
    import msvcrt  # Windows-only
except Exception:
    msvcrt = None

try:
    import select
    import termios
    import tty
except Exception:
    select = None
    termios = None
    tty = None

# =============================
# Global state / config directory
# =============================
# User requested: store .sigilrc files in C:\Sigil
SIGIL_CONFIG_DIR = os.path.abspath(r"C:\Sigil")
os.makedirs(SIGIL_CONFIG_DIR, exist_ok=True)

# plugin directory
PLUGIN_DIR = os.path.join(SIGIL_CONFIG_DIR, "plugins")
os.makedirs(PLUGIN_DIR, exist_ok=True)
_PLUGIN_REGISTRY_PATH = os.path.join(PLUGIN_DIR, "plugins.json")

CURRENT_PROFILE = "default"
CURRENT_DIR = os.getcwd()

UNDO_STACK: List[dict] = []
REDO_STACK: List[dict] = []
UNDO_LIMIT = 200
UNDO_BASE = os.path.join(tempfile.gettempdir(), "sigil_undo")
os.makedirs(UNDO_BASE, exist_ok=True)

ALIASES: dict = {}     # name -> command string
VARIABLES: dict = {}   # name -> value (str/int/float)

LOADING_RC = False  # guard: true while load_sigilrc is running

# plugin runtime registry (in-memory)
# plugin_name -> {
#   "archive": "<path to .sigin>",
#   "extract_dir": "<path to extracted files>",
#   "commands": ["cmd1","cmd2"],
#   "info": {...}
# }
PLUGIN_REGISTRY: dict = {}

# =============================
# Helpers
# =============================
def rc_path(profile: str | None = None) -> str:
    """Return the full path to the active profile's rc file in SIGIL_CONFIG_DIR."""
    name = profile or CURRENT_PROFILE
    if name == "default":
        return os.path.join(SIGIL_CONFIG_DIR, ".sigilrc")
    return os.path.join(SIGIL_CONFIG_DIR, f".sigilrc.{name}")

def save_sigilrc() -> None:
    """Write current ALIASES and VARIABLES to the active profile rc file."""
    path = rc_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Sigil RC — profile: {CURRENT_PROFILE}\n")
            f.write("# Aliases\n")
            for k, v in ALIASES.items():
                # write alias as: alia name <command...>
                f.write(f"alia {k} {v}\n")
            f.write("\n# Variables\n")
            for k, v in VARIABLES.items():
                # write let name = value
                if isinstance(v, str):
                    needs_quote = any(ch.isspace() for ch in v) or v == ""
                    v_escaped = v.replace('"', '\\"')
                    if needs_quote:
                        f.write(f'let {k} = "{v_escaped}"\n')
                    else:
                        f.write(f"let {k} = {v_escaped}\n")
                else:
                    # number types
                    f.write(f"let {k} = {v}\n")
    except Exception as e:
        print(f"Failed to save .sigilrc: {e}")

def load_sigilrc() -> None:
    """Load and execute commands from the active profile rc file."""
    global LOADING_RC
    path = rc_path()
    if not os.path.exists(path):
        return
    LOADING_RC = True
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        run_lines(lines, from_rc=True)
    finally:
        LOADING_RC = False

def make_backup_of_path(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    bak_id = str(uuid.uuid4())
    bak_dir = os.path.join(UNDO_BASE, bak_id)
    os.makedirs(bak_dir, exist_ok=True)
    name = os.path.basename(path)
    dest = os.path.join(bak_dir, name)
    shutil.move(path, dest)
    return dest

def backup_file_contents(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    bak_id = str(uuid.uuid4())
    bak_path = os.path.join(UNDO_BASE, bak_id + "_" + os.path.basename(path))
    shutil.copy2(path, bak_path)
    return bak_path

def push_undo(action: dict) -> None:
    UNDO_STACK.append(action)
    if len(UNDO_STACK) > UNDO_LIMIT:
        UNDO_STACK.pop(0)
    REDO_STACK.clear()

def safe_move(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.move(src, dst)

# =============================
# Tokenizer & comment stripper
# =============================
def tokenize(line: str) -> List[str]:
    tokens = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            in_quotes = not in_quotes
            current += c
        elif c == ' ' and not in_quotes:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += c
        i += 1
    if current:
        tokens.append(current)
    return tokens

def strip_comments_from_line(line: str, in_block_comment: bool) -> Tuple[str, bool]:
    if in_block_comment:
        end_idx = line.find("*/")
        if end_idx == -1:
            return "", True
        line = line[end_idx+2:]
        in_block_comment = False
    while True:
        start_idx = line.find("/*")
        if start_idx == -1:
            break
        end_idx = line.find("*/", start_idx+2)
        if end_idx == -1:
            line = line[:start_idx]
            in_block_comment = True
            break
        else:
            line = line[:start_idx] + line[end_idx+2:]
    result = []
    in_quotes = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            in_quotes = not in_quotes
            result.append(c)
            i += 1
            continue
        if not in_quotes:
            if c == '/' and i + 1 < len(line) and line[i+1] == '/':
                break
            if c == '#':
                break
        result.append(c)
        i += 1
    stripped = "".join(result).rstrip()
    return stripped, in_block_comment

# =============================
# Alias & variable expansion
# =============================
def expand_aliases_and_vars(line: str) -> str:
    """Expand alias (if first token is alias) and substitute variables.
       Variables expand in two forms:
       - $name replaced by its value (stringified)
       - bare token equal to a variable name -> replaced
    """
    tokens = tokenize(line)
    if not tokens:
        return line
    # alias expansion for first token
    first = tokens[0]
    if first in ALIASES:
        alias_cmd = ALIASES[first]
        rest = tokens[1:]
        new_line = alias_cmd
        if rest:
            new_line = alias_cmd + " " + " ".join(rest)
        return expand_aliases_and_vars(new_line)  # recursive in case alias maps to alias
    # variable substitution
    new_tokens = []
    for t in tokens:
        replaced = False
        # quoted token
        if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
            inner = t[1:-1]
            if inner in VARIABLES:
                v = VARIABLES[inner]
                if isinstance(v, str):
                    new_tokens.append('"' + str(v).replace('"', '\\"') + '"')
                else:
                    new_tokens.append(str(v))
                replaced = True
            else:
                new_tokens.append(t)
                replaced = True
        if replaced:
            continue
        # $var form
        if t.startswith("$"):
            key = t[1:]
            if key in VARIABLES:
                new_tokens.append(str(VARIABLES[key]))
            else:
                new_tokens.append(t)
            continue
        # bare var name
        if t in VARIABLES:
            new_tokens.append(str(VARIABLES[t]))
            continue
        new_tokens.append(t)
    return " ".join(new_tokens)

# =============================
# Help text
# =============================
HELP_TEXT = {
    "help": "help [command]\n  Show all commands or help for a specific command\n\nComments: # single-line, // single-line, /* ... */ block comments",
    "mk": "mk dir <name>\nmk file <name.ext> [content]\n  Create a directory or file",
    "cpy": "cpy <src> <dst>\n  Copy a file or directory",
    "dlt": "dlt <path>\n  Delete a file or directory (undoable)",
    "move": "move file <src> <dst>\n  Move or rename a file (undoable)",
    "cd": "cd <path>\n  Change current directory (supports Windows paths)",
    "dirlook": "dirlook\n  List contents of the current directory",
    "opnlnk": "opnlnk <url>\n  Open a web link in default browser",
    "opn": "opn <path>\n  Open a local file or folder with default application",
    "ex": "ex\n  Open File Explorer at current directory (Windows only)",
    "task": "task\n  List running tasks / processes",
    "kill": "kill task <name>\n  Kill a running task by image/name",
    "clo": "clo task <name>\n  Gracefully close a running task by name (no force).",
    "say": "say <text>\n  Print text to console (resolves variables)",
    "undo": "undo\n  Undo the last mutating action",
    "redo": "redo\n  Redo the last undone action",
    "edt": "edt <path>\n  Edit a file (uses SIGIL_EDITOR or Notepad/nano). Edit is undoable.",
    "sdow": "sdow confirm\n  Shutdown the machine. MUST use 'confirm' to proceed.",
    "rstr": "rstr confirm\n  Restart the machine. MUST use 'confirm' to proceed.",
    "bored": "bored\n  Say random movie quotes every 3 seconds. Press any key (or Enter) to stop.",
    "add": "add <n1> <n2> [<n3> ...]\n  Add numbers (integers/floats).",
    "sub": "sub <n1> <n2> [<n3> ...]\n  Subtract numbers (n1 - n2 - n3 ...).",
    "mul": "mul <n1> <n2> [<n3> ...]\n  Multiply numbers.",
    "div": "div <n1> <n2> [<n3> ...]\n  Divide numbers (n1 / n2 / n3 ...).",
    "alia": "alia <name> <command>  or  alia  (list aliases)",
    "unalia": "unalia <name>\n  Remove alias",
    "let": "let <name> = <value>\n  Define a variable (string or number). Use variable by name or $name.",
    "var": "var\n  List variables",
    "unset": "unset <name>\n  Remove variable",
    "if": "if <cond> then <cmd>\n  Conditional execution. cond examples: exists <path>, 5 > 3, name == \"bob\"",
    "wait": "wait <seconds>\n  Sleep for given seconds (float allowed)",
    "renm": "renm <old> <new>\n  Rename (alias of move file <old> <new>)",
    "siz": "siz <file|dir>\n  Show size in bytes (dir is recursive)",
    "pwd": "pwd\n  Print current directory",
    "opnapp": "opnapp <name>\n  Launch an application by name or path",
    "run": "run <file.sig>\n  Run another Sigil script file",
    "inc": "inc <file.sig>\n  Include file inline (execute immediately)",
    "fmt": "fmt <file.sig>\n  Basic formatting: trim trailing spaces",
    "schk": "schk <file.sig>\n  Basic syntax check / linter",
    "prof": "prof [show|new <name>|del <name>|<name>]  profile management",
    "rrc": "rrc  Reload active .sigilrc",
    "svrc": "svrc  Save active .sigilrc",
    "pse": "pse [message]  Pause — print optional message then wait for key (Windows) or Enter (other OSs)",
    # plugin commands
    "pin": "pin <path-to-plugin.sigin>  Install a plugin from a .sigin archive.  pin  (no args) lists installed plugins",
    "prv": "prv <name>  Remove/uninstall plugin by name"
}

# =============================
# Arithmetic helper
# =============================
def _parse_numbers(args: List[str]) -> List[float | int]:
    nums: List[float | int] = []
    for t in args:
        if t in VARIABLES:
            t = str(VARIABLES[t])
        if isinstance(t, (int, float)):
            nums.append(t)
            continue
        if isinstance(t, str) and len(t) >= 2 and t[0] == '"' and t[-1] == '"':
            t = t[1:-1]
        try:
            if "." in t or "e" in t.lower():
                nums.append(float(t))
            else:
                nums.append(int(t))
        except Exception:
            nums.append(float(t))
    return nums

# =============================
# Plugin helpers
# =============================
def _safe_plugin_name(name: str) -> str:
    # produce filename-friendly plugin name
    return re.sub(r'[^A-Za-z0-9_\-]', '_', name).strip('_')

def _save_registry():
    try:
        with open(_PLUGIN_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(PLUGIN_REGISTRY, f, indent=2)
    except Exception:
        # best-effort only
        pass

def _load_registry():
    global PLUGIN_REGISTRY
    if os.path.exists(_PLUGIN_REGISTRY_PATH):
        try:
            with open(_PLUGIN_REGISTRY_PATH, "r", encoding="utf-8") as f:
                PLUGIN_REGISTRY = json.load(f)
        except Exception:
            PLUGIN_REGISTRY = {}
    else:
        PLUGIN_REGISTRY = {}

def _plugin_extract_and_register(archive_path: str, name_hint: str | None = None) -> dict:
    """
    Extracts archive_path (.sigin ZIP) to PLUGIN_DIR/<name>
    Returns plugin metadata dict (name, archive, extract_dir, commands, info)
    """
    if not os.path.exists(archive_path):
        raise FileNotFoundError("Archive not found")
    base = os.path.basename(archive_path)
    base_noext = os.path.splitext(base)[0]
    raw_name = name_hint or base_noext
    plugin_name = _safe_plugin_name(raw_name)
    extract_dir = os.path.join(PLUGIN_DIR, plugin_name)
    # ensure unique if exists already by suffixing a number
    if os.path.exists(extract_dir):
        idx = 1
        while os.path.exists(extract_dir + f"_{idx}"):
            idx += 1
        extract_dir = extract_dir + f"_{idx}"
        plugin_name = os.path.basename(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
    except zipfile.BadZipFile as e:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise e
    # attempt to read plugin-main.py metadata if present
    info = {}
    pm_path = os.path.join(extract_dir, "plugin-main.py")
    if os.path.exists(pm_path):
        try:
            g = runpy.run_path(pm_path, run_name="__sigil_plugin_info__")
            # plugin can expose PLUGIN_INFO dict
            if "PLUGIN_INFO" in g and isinstance(g["PLUGIN_INFO"], dict):
                info = g["PLUGIN_INFO"]
                # prefer explicit name if provided
                if "name" in info:
                    plugin_name = _safe_plugin_name(info["name"])
                    # rename extract_dir if needed
                    desired_dir = os.path.join(PLUGIN_DIR, plugin_name)
                    if desired_dir != extract_dir:
                        if os.path.exists(desired_dir):
                            # avoid clobber; keep current extract_dir
                            pass
                        else:
                            shutil.move(extract_dir, desired_dir)
                            extract_dir = desired_dir
        except Exception:
            # plugin-main may perform install-time logic; ignore here for info read
            pass
    # ensure archive is copied into PLUGIN_DIR with canonical name
    archive_dest = os.path.join(PLUGIN_DIR, plugin_name + ".sigin")
    try:
        if os.path.abspath(archive_path) != os.path.abspath(archive_dest):
            shutil.copy2(archive_path, archive_dest)
    except Exception:
        pass
    # register minimal entry
    plugin_entry = {
        "archive": os.path.abspath(archive_dest),
        "extract_dir": os.path.abspath(extract_dir),
        "commands": [],
        "info": info
    }
    return plugin_name, plugin_entry

def _load_plugin_commands(plugin_name: str, plugin_entry: dict):
    """Load plugin.py from plugin_entry['extract_dir'] and call register(COMMANDS, helpers)
       If register returns a dict of commands, add them to COMMANDS and record mapping.
    """
    pdir = plugin_entry.get("extract_dir")
    if not pdir or not os.path.isdir(pdir):
        return
    plugin_py = os.path.join(pdir, "plugin.py")
    if not os.path.exists(plugin_py):
        return
    try:
        g = runpy.run_path(plugin_py, run_name=f"__sigil_plugin_{plugin_name}__")
        # look for register function
        if "register" in g and callable(g["register"]):
            # provide helper API to plugin
            helpers = {
                "config_dir": SIGIL_CONFIG_DIR,
                "plugin_dir": PLUGIN_DIR,
                "resolve": resolve,
            }
            reg_result = g["register"](COMMANDS, helpers)
            # register may return list of commands it added, or dict mapping
            added_cmds = []
            if isinstance(reg_result, dict):
                # reg_result is mapping name->callable
                for name, fn in reg_result.items():
                    if callable(fn):
                        COMMANDS[name] = fn
                        added_cmds.append(name)
            elif isinstance(reg_result, list):
                # assume it's list of names (already registered inside plugin)
                for name in reg_result:
                    if name in COMMANDS:
                        added_cmds.append(name)
            # if plugin provided a 'COMMANDS' dict in its globals, register those too
            if "COMMANDS" in g and isinstance(g["COMMANDS"], dict):
                for name, fn in g["COMMANDS"].items():
                    if callable(fn):
                        COMMANDS[name] = fn
                        added_cmds.append(name)
            # persist recorded commands
            plugin_entry["commands"] = sorted(set(plugin_entry.get("commands", []) + added_cmds))
    except Exception as e:
        print(f"Plugin '{plugin_name}' load error: {e}")

def load_plugins_on_startup():
    """Load plugin registry file, then load plugin commands for each registered plugin."""
    _load_registry()
    # load any discovered archives/extracted dirs that are not in registry
    # scan PLUGIN_DIR for .sigin files and folders
    try:
        for item in os.listdir(PLUGIN_DIR):
            p = os.path.join(PLUGIN_DIR, item)
            if item.endswith(".sigin"):
                name = os.path.splitext(item)[0]
                if name not in PLUGIN_REGISTRY:
                    # we have an orphaned archive: try extract to folder name
                    try:
                        _, entry = _plugin_extract_and_register(p, name_hint=name)
                        PLUGIN_REGISTRY[name] = entry
                    except Exception:
                        pass
            elif os.path.isdir(p):
                name = item
                if name not in PLUGIN_REGISTRY:
                    # create entry pointing to this folder
                    archive_guess = os.path.join(PLUGIN_DIR, name + ".sigin")
                    entry = {"archive": os.path.abspath(archive_guess) if os.path.exists(archive_guess) else "",
                             "extract_dir": os.path.abspath(p),
                             "commands": [],
                             "info": {}}
                    PLUGIN_REGISTRY[name] = entry
    except Exception:
        pass

    # now attempt to load plugin.py for each plugin
    for name, entry in list(PLUGIN_REGISTRY.items()):
        try:
            _load_plugin_commands(name, entry)
        except Exception:
            pass
    # store registry back
    _save_registry()

def install_plugin_from_path(path: str):
    """Install a plugin from a .sigin archive path."""
    if not os.path.exists(path):
        print("Plugin archive not found:", path)
        return
    # if path is a directory (user pointed to extracted folder), we can accept it too:
    if os.path.isdir(path):
        # pack folder into a .sigin archive to canonicalize
        tmp_archive = os.path.join(tempfile.gettempdir(), f"plugin_{uuid.uuid4().hex}.sigin")
        try:
            with zipfile.ZipFile(tmp_archive, "w", zipfile.ZIP_DEFLATED) as z:
                for root, dirs, files in os.walk(path):
                    for fn in files:
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, start=path)
                        z.write(full, arcname=rel)
            archive_path = tmp_archive
        except Exception as e:
            print("Failed to package folder:", e)
            return
    else:
        archive_path = path
    # attempt to extract + register
    try:
        plugin_name, entry = _plugin_extract_and_register(archive_path)
    except zipfile.BadZipFile:
        print("Not a valid .sigin archive.")
        return
    except Exception as e:
        print("Install failed:", e)
        return

    # run plugin-main.py in plugin extract folder (install-time hook)
    try:
        pm = os.path.join(entry["extract_dir"], "plugin-main.py")
        if os.path.exists(pm):
            # run plugin-main with run_name allowing it to perform install-time actions
            runpy.run_path(pm, run_name=f"__sigil_plugin_install_{plugin_name}__")
    except Exception as e:
        print(f"Plugin-install hook error: {e}")

    # load plugin commands
    try:
        _load_plugin_commands(plugin_name, entry)
    except Exception:
        pass

    # save to registry
    PLUGIN_REGISTRY[plugin_name] = entry
    _save_registry()
    print(f"Plugin installed: {plugin_name}")

def uninstall_plugin(name: str):
    """Uninstall plugin by name: remove commands, delete files."""
    safe_name = _safe_plugin_name(name)
    if safe_name not in PLUGIN_REGISTRY:
        print("Plugin not found:", name)
        return
    entry = PLUGIN_REGISTRY[safe_name]
    # remove commands that plugin registered
    cmds = entry.get("commands", []) or []
    for c in cmds:
        if c in COMMANDS:
            try:
                del COMMANDS[c]
            except Exception:
                pass
    # remove extracted folder
    ex = entry.get("extract_dir")
    try:
        if ex and os.path.exists(ex):
            shutil.rmtree(ex, ignore_errors=True)
    except Exception:
        pass
    # remove archive
    arch = entry.get("archive")
    try:
        if arch and os.path.exists(arch):
            os.remove(arch)
    except Exception:
        pass
    # remove from registry
    del PLUGIN_REGISTRY[safe_name]
    _save_registry()
    print(f"Plugin removed: {safe_name}")

def list_installed_plugins():
    if not PLUGIN_REGISTRY:
        print("No plugins installed.")
        return
    for name, entry in PLUGIN_REGISTRY.items():
        info = entry.get("info") or {}
        version = info.get("version", "")
        desc = info.get("description", "")
        print(f"- {name}" + (f" v{version}" if version else "") + (f" — {desc}" if desc else ""))

# =============================
# Commands implementations
# =============================
def cmd_help(args: List[str]):
    if not args:
        print("\nAvailable glyphs:\n")
        for name in sorted(HELP_TEXT):
            print(f"  {name}")
        print("\nType: help <glyph> for details\n")
        return
    print("\n" + HELP_TEXT.get(args[0], "No help available") + "\n")

def cmd_mk(args: List[str]):
    if len(args) < 2:
        print(HELP_TEXT["mk"])
        return
    if args[0] == "dir":
        path = resolve(args[1])
        existed = os.path.exists(path)
        if not existed:
            os.makedirs(path, exist_ok=True)
        push_undo({"op": "mk_dir", "path": path, "existed": existed})
        print("ok")
    elif args[0] == "file":
        path = resolve(args[1])
        content = " ".join(args[2:]) if len(args) > 2 else ""
        existed = os.path.exists(path)
        backup = None
        if existed:
            backup = backup_file_contents(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        push_undo({"op": "mk_file", "path": path, "existed": existed, "backup": backup})
        print("ok")
    else:
        print("Unknown mk target")

def cmd_cpy(args: List[str]):
    if len(args) < 2:
        print(HELP_TEXT["cpy"])
        return
    src = resolve(args[0])
    dst = resolve(args[1])
    if not os.path.exists(src):
        print("Source does not exist")
        return
    dst_existed = os.path.exists(dst)
    dst_backup = None
    if dst_existed:
        if os.path.isdir(dst):
            dst_backup = make_backup_of_path(dst)
        else:
            dst_backup = backup_file_contents(dst)
    if os.path.isdir(src):
        if os.path.exists(dst):
            print("Destination exists (for directory copy) — operation aborted")
            return
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
    push_undo({"op": "cpy", "src": src, "dst": dst, "dst_existed": dst_existed, "dst_backup": dst_backup})
    print("ok")

def cmd_dlt(args: List[str]):
    if not args:
        print(HELP_TEXT["dlt"])
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Path does not exist")
        return
    backup = make_backup_of_path(path)
    push_undo({"op": "dlt", "path": path, "backup": backup})
    print("ok")

def cmd_move(args: List[str]):
    if len(args) < 3 or args[0] != "file":
        print(HELP_TEXT["move"])
        return
    src = resolve(args[1])
    dst = resolve(args[2])
    if not os.path.exists(src):
        print("Source does not exist")
        return
    dst_existed = os.path.exists(dst)
    dst_backup = None
    if dst_existed:
        if os.path.isdir(dst):
            dst_backup = make_backup_of_path(dst)
        else:
            dst_backup = backup_file_contents(dst)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.move(src, dst)
    push_undo({"op": "move", "src": src, "dst": dst, "dst_existed": dst_existed, "dst_backup": dst_backup})
    print("ok")

def cmd_cd(args: List[str]):
    global CURRENT_DIR
    if not args:
        print(CURRENT_DIR)
        return
    path = resolve(args[0])
    if os.path.isdir(path):
        CURRENT_DIR = path
        print("CWD:", CURRENT_DIR)
    else:
        print("Not a directory")

def cmd_dirlook(args: List[str]):
    print(f"\n📁 {CURRENT_DIR}\n")
    try:
        for item in os.listdir(CURRENT_DIR):
            print(item)
    except PermissionError:
        print("Permission denied")

def cmd_opnlnk(args: List[str]):
    if not args:
        print(HELP_TEXT["opnlnk"])
        return
    webbrowser.open(args[0])
    print("ok")

def cmd_opn(args: List[str]):
    if not args:
        print(HELP_TEXT["opn"])
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Path does not exist")
        return
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])
    print("ok")

def cmd_ex(args: List[str]):
    if os.name == "nt":
        subprocess.Popen(["explorer", CURRENT_DIR])
        print("ok")
    else:
        print("Explorer not supported on this OS")

def cmd_task(args: List[str]):
    try:
        if os.name == "nt":
            out = subprocess.check_output(["tasklist"]).decode(errors='ignore')
            print(out)
        else:
            out = subprocess.check_output(["ps", "-e"]).decode(errors='ignore')
            print(out)
    except Exception as e:
        print("Error listing tasks:", e)

def cmd_kill(args: List[str]):
    if len(args) < 2 or args[0] != "task":
        print(HELP_TEXT["kill"])
        return
    name = args[1]
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", name, "/F"])
        else:
            subprocess.run(["pkill", name])
        print("ok")
    except Exception as e:
        print("Error killing task:", e)

def cmd_say(args: List[str]):
    parts: List[str] = []
    for t in args:
        if t.startswith("$") and t[1:] in VARIABLES:
            parts.append(str(VARIABLES[t[1:]]))
        elif t in VARIABLES:
            parts.append(str(VARIABLES[t]))
        else:
            parts.append(t)
    print(" ".join(parts))

# Arithmetic & misc
def cmd_add(args: List[str]):
    if not args:
        print("Usage: add <n1> <n2> [<n3> ...]")
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        return
    total = nums[0]
    for n in nums[1:]:
        total += n
    if isinstance(total, float) and total.is_integer():
        total = int(total)
    print(total)

def cmd_sub(args: List[str]):
    if not args or len(args) < 2:
        print("Usage: sub <n1> <n2> [<n3> ...]")
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        return
    result = nums[0]
    for n in nums[1:]:
        result -= n
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    print(result)

def cmd_mul(args: List[str]):
    if not args:
        print("Usage: mul <n1> <n2> [<n3> ...]")
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        return
    prod = nums[0]
    for n in nums[1:]:
        prod *= n
    if isinstance(prod, float) and prod.is_integer():
        prod = int(prod)
    print(prod)

def cmd_div(args: List[str]):
    if not args or len(args) < 2:
        print("Usage: div <n1> <n2> [<n3> ...]")
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        return
    result = float(nums[0])
    try:
        for n in nums[1:]:
            if n == 0:
                print("Error: division by zero")
                return
            result /= n
    except Exception as e:
        print("Error during division:", e)
        return
    if result.is_integer():
        result = int(result)
    print(result)

def cmd_clo(args: List[str]):
    if len(args) < 2 or args[0] != "task":
        print("Usage: clo task <name>")
        return
    name = args[1]
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", name])
        else:
            subprocess.run(["pkill", name])
        print("ok")
    except Exception as e:
        print("Error closing task:", e)

def cmd_rstr(args: List[str]):
    if len(args) == 1 and args[0].lower() == "confirm":
        print("Restarting — immediate. Press Ctrl+C to cancel in the next 2 seconds.")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("Restart cancelled.")
            return
        if os.name == "nt":
            subprocess.run(["shutdown", "/r", "/t", "0"])
        else:
            subprocess.run(["shutdown", "-r", "now"])
    else:
        print("rstr is destructive. To confirm use: rstr confirm")

# Undo/redo helpers
def perform_undo_action(action: dict):
    op = action.get("op")
    if op == "mk_dir":
        path = action["path"]
        if not action.get("existed", False):
            if os.path.isdir(path):
                backup = make_backup_of_path(path)
                return {"op": "dlt", "path": path, "backup": backup}
        return None
    if op == "mk_file":
        path = action["path"]
        existed = action.get("existed", False)
        backup = action.get("backup")
        if not existed:
            if os.path.exists(path):
                bak = make_backup_of_path(path)
                return {"op": "dlt", "path": path, "backup": bak}
        else:
            if backup and os.path.exists(backup):
                cur_exists = os.path.exists(path)
                cur_bak = None
                if cur_exists:
                    cur_bak = make_backup_of_path(path)
                shutil.move(backup, path)
                return {"op": "restore_file_after_mkfile", "path": path, "backup": cur_bak}
        return None
    if op == "cpy":
        dst = action["dst"]
        dst_existed = action.get("dst_existed", False)
        dst_backup = action.get("dst_backup")
        if not dst_existed:
            if os.path.exists(dst):
                bak = make_backup_of_path(dst)
                return {"op": "dlt", "path": dst, "backup": bak}
        else:
            if dst_backup:
                if os.path.exists(dst):
                    cur_bak = make_backup_of_path(dst)
                safe_move(dst_backup, dst)
                return {"op": "cpy_restore", "dst": dst, "cur_bak": cur_bak if 'cur_bak' in locals() else None}
        return None
    if op == "dlt":
        backup = action.get("backup")
        path = action.get("path")
        if backup and os.path.exists(backup):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            shutil.move(backup, path)
            return {"op": "dlt_after_restore", "path": path}
        return None
    if op == "move":
        src = action["src"]
        dst = action["dst"]
        dst_backup = action.get("dst_backup")
        dst_existed = action.get("dst_existed", False)
        if os.path.exists(dst):
            os.makedirs(os.path.dirname(src) or ".", exist_ok=True)
            shutil.move(dst, src)
            if dst_backup:
                if os.path.exists(dst_backup):
                    safe_move(dst_backup, dst)
                return {"op": "move_redo", "src": src, "dst": dst, "dst_backup": None}
            else:
                return {"op": "move_redo", "src": src, "dst": dst, "dst_backup": None}
        return None
    if op == "edit":
        path = action.get("path")
        backup = action.get("backup")
        if backup and os.path.exists(backup):
            cur_bak = None
            if os.path.exists(path):
                cur_bak = backup_file_contents(path)
            shutil.copy2(backup, path)
            return {"op": "edit_redo", "path": path, "backup": cur_bak}
        return None
    return None

def perform_redo_action(action: dict):
    op = action.get("op")
    if op == "dlt":
        path = action["path"]
        if os.path.exists(path):
            bak = make_backup_of_path(path)
            return {"op": "dlt", "path": path, "backup": bak}
        return None
    if op == "move_redo" or op == "move":
        src = action.get("src")
        dst = action.get("dst")
        if os.path.exists(src):
            dst_backup = None
            dst_existed = os.path.exists(dst)
            if dst_existed:
                if os.path.isdir(dst):
                    dst_backup = make_backup_of_path(dst)
                else:
                    dst_backup = backup_file_contents(dst)
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.move(src, dst)
            return {"op": "move", "src": src, "dst": dst, "dst_backup": dst_backup, "dst_existed": dst_existed}
        return None
    if op == "cpy_restore" or op == "cpy":
        return None
    if op == "dlt_after_restore":
        return None
    if op == "edit_redo":
        path = action.get("path")
        backup = action.get("backup")
        if backup and os.path.exists(backup):
            cur_backup = None
            if os.path.exists(path):
                cur_backup = backup_file_contents(path)
            shutil.copy2(backup, path)
            return {"op": "edit", "path": path, "backup": cur_backup}
        return None
    return None

def cmd_undo(args: List[str]):
    if not UNDO_STACK:
        print("Nothing to undo")
        return
    action = UNDO_STACK.pop()
    inverse = perform_undo_action(action)
    if inverse:
        REDO_STACK.append(inverse)
    else:
        REDO_STACK.append({"op": "noop"})
    print("Undone.")

def cmd_redo(args: List[str]):
    if not REDO_STACK:
        print("Nothing to redo")
        return
    action = REDO_STACK.pop()
    inverse = perform_redo_action(action)
    if inverse:
        UNDO_STACK.append(inverse)
    else:
        UNDO_STACK.append({"op": "noop"})
    print("Redone.")

def cmd_edt(args: List[str]):
    if not args:
        print(HELP_TEXT["edt"])
        return
    path = resolve(args[0])
    existed = os.path.exists(path)
    if not existed:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "a", encoding="utf-8").close()
    backup = backup_file_contents(path)
    editor = os.environ.get("SIGIL_EDITOR")
    if not editor:
        editor = "notepad" if os.name == "nt" else "nano"
    try:
        subprocess.run([editor, path])
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Edit aborted.")
        return
    push_undo({"op": "edit", "path": path, "backup": backup})
    print("ok")

def cmd_sdow(args: List[str]):
    if len(args) == 1 and args[0].lower() == "confirm":
        print("Shutting down — immediate. Press Ctrl+C to cancel in the next 2 seconds.")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("Shutdown cancelled.")
            return
        if os.name == "nt":
            subprocess.run(["shutdown", "/s", "/t", "0"])
        else:
            subprocess.run(["shutdown", "-h", "now"])
    else:
        print("sdow is destructive. To confirm use: sdow confirm")

MOVIE_QUOTES = [
    "May the Force be with you.",
    "I'm gonna make him an offer he can't refuse.",
    "Here's looking at you, kid.",
    "You talking to me?",
    "I'll be back.",
    "You shall not pass!",
    "Why so serious?",
    "There's no place like home.",
    "I love the smell of napalm in the morning.",
    "I'm the king of the world!",
    "Elementary, my dear Watson.",
    "Keep your friends close, but your enemies closer."
]

def _bored_wait_for_key() -> bool:
    if msvcrt:
        if msvcrt.kbhit():
            msvcrt.getch()
            return True
        return False
    if select and termios and tty:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(dr)
    return False

def cmd_bored(args: List[str]):
    print("Bored mode — press any key (or Enter) to stop.")
    old_settings = None
    using_unix_raw = False
    if not msvcrt and termios and tty:
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            using_unix_raw = True
        except Exception:
            old_settings = None
            using_unix_raw = False
    try:
        while True:
            quote = random.choice(MOVIE_QUOTES)
            print(f"💬 {quote}")
            waited = 0.0
            interval = 0.1
            stop = False
            while waited < 3.0:
                time.sleep(interval)
                waited += interval
                if msvcrt:
                    if msvcrt.kbhit():
                        _ = msvcrt.getch()
                        stop = True
                        break
                elif select and termios:
                    dr, _, _ = select.select([sys.stdin], [], [], 0)
                    if dr:
                        _ = sys.stdin.read(1)
                        stop = True
                        break
            if stop:
                break
    finally:
        if using_unix_raw and old_settings:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass
    print("Bored mode stopped.")

# Aliases, variables, config management
def cmd_alia(args: List[str]):
    # list aliases if no args
    if not args:
        if not ALIASES:
            print("no aliases defined")
            return
        for k, v in ALIASES.items():
            print(f"{k} -> {v}")
        return
    # create alias
    if len(args) >= 2:
        name = args[0]
        cmd_str = " ".join(args[1:])
        ALIASES[name] = cmd_str
        if not LOADING_RC:
            save_sigilrc()
        print(f"Alias set: {name} -> {cmd_str}")
        return
    print("Usage: alia <name> <command>")

def cmd_unalia(args: List[str]):
    if not args:
        print("Usage: unalia <name>")
        return
    name = args[0]
    if name in ALIASES:
        del ALIASES[name]
        if not LOADING_RC:
            save_sigilrc()
        print(f"Alias removed: {name}")
    else:
        print("Alias not found")

def cmd_let(args: List[str]):
    if not args:
        print(HELP_TEXT["let"])
        return
    # let name = value  OR let name value
    if len(args) >= 3 and args[1] == "=":
        name = args[0]
        val = " ".join(args[2:])
    elif len(args) >= 2:
        name = args[0]
        val = " ".join(args[1:])
    else:
        print("Usage: let <name> = <value>")
        return
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        val = val[1:-1].replace('\\"', '"')
    # try numeric cast
    try:
        if "." in val or "e" in val.lower():
            v = float(val)
        else:
            v = int(val)
    except Exception:
        v = val
    VARIABLES[name] = v
    if not LOADING_RC:
        save_sigilrc()
    print(f"Set {name} = {v}")

def cmd_var(args: List[str]):
    if not VARIABLES:
        print("no variables defined")
        return
    for k, v in VARIABLES.items():
        print(f"{k} = {v}")

def cmd_unset(args: List[str]):
    if not args:
        print("Usage: unset <name>")
        return
    name = args[0]
    if name in VARIABLES:
        del VARIABLES[name]
        if not LOADING_RC:
            save_sigilrc()
        print(f"unset {name}")
    else:
        print("variable not found")

def _eval_condition(tokens: List[str]) -> bool:
    if not tokens:
        return False
    if tokens[0] == "exists" and len(tokens) >= 2:
        p = resolve(tokens[1])
        return os.path.exists(p)
    if len(tokens) >= 3:
        left = tokens[0]
        op = tokens[1]
        right = " ".join(tokens[2:])
        if left in VARIABLES:
            left = VARIABLES[left]
        if right in VARIABLES:
            right = VARIABLES[right]
        # numeric?
        try:
            lnum = float(left)
            rnum = float(right)
            if op == "==": return lnum == rnum
            if op == "!=": return lnum != rnum
            if op == ">": return lnum > rnum
            if op == "<": return lnum < rnum
            if op == ">=": return lnum >= rnum
            if op == "<=": return lnum <= rnum
        except Exception:
            if op == "==": return str(left) == str(right)
            if op == "!=": return str(left) != str(right)
            if op == ">": return str(left) > str(right)
            if op == "<": return str(left) < str(right)
            if op == ">=": return str(left) >= str(right)
            if op == "<=": return str(left) <= str(right)
    return False

def cmd_if(args: List[str]):
    if not args:
        print("Usage: if <cond> then <cmd>")
        return
    try:
        then_i = args.index("then")
    except ValueError:
        print("Usage: if <cond> then <cmd>")
        return
    cond_tokens = args[:then_i]
    cmd_tokens = args[then_i+1:]
    if _eval_condition(cond_tokens):
        run_lines([" ".join(cmd_tokens)])
    else:
        pass

def cmd_wait(args: List[str]):
    if not args:
        print("Usage: wait <seconds>")
        return
    try:
        s = float(args[0])
    except Exception:
        print("Invalid number")
        return
    time.sleep(s)

def cmd_renm(args: List[str]):
    if len(args) < 2:
        print("Usage: renm <old> <new>")
        return
    cmd_move(["file", args[0], args[1]])

def _dir_size(path: str) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                fp = os.path.join(root, f)
                total += os.path.getsize(fp)
            except Exception:
                pass
    return total

def cmd_siz(args: List[str]):
    if not args:
        print("Usage: siz <file|dir>")
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Not found")
        return
    if os.path.isfile(path):
        print(os.path.getsize(path))
    else:
        print(_dir_size(path))

def cmd_pwd(args: List[str]):
    print(CURRENT_DIR)

def cmd_opnapp(args: List[str]):
    if not args:
        print("Usage: opnapp <name>")
        return
    name = args[0]
    if os.path.exists(name):
        if os.name == "nt":
            os.startfile(os.path.abspath(name))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", name])
        else:
            subprocess.Popen([name])
        print("ok")
        return
    try:
        if os.name == "nt":
            subprocess.Popen(["start", "", name], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        print("ok")
    except Exception as e:
        print("Failed to launch:", e)

def cmd_run(args: List[str]):
    if not args:
        print("Usage: run <file.sig>")
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        run_lines(lines)
    except Exception as e:
        print("Error running script:", e)

def cmd_inc(args: List[str]):
    if not args:
        print("Usage: inc <file.sig>")
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        run_lines(lines)
    except Exception as e:
        print("Error including file:", e)

def cmd_fmt(args: List[str]):
    if not args:
        print("Usage: fmt <file.sig>")
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [ln.rstrip() for ln in lines]
        out_text = "\n".join(new_lines).rstrip() + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(out_text)
        print("Formatted:", path)
    except Exception as e:
        print("Format failed:", e)

def cmd_schk(args: List[str]):
    if not args:
        print("Usage: schk <file.sig>")
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        return
    problems = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_block = False
        for i, raw in enumerate(lines, start=1):
            line = raw.rstrip("\n")
            stripped, in_block = strip_comments_from_line(line, in_block)
            if stripped.count('"') % 2 != 0:
                problems.append((i, "Unmatched quote"))
            parts = tokenize(stripped)
            if not parts:
                continue
            cmd = parts[0]
            if cmd not in COMMANDS and cmd not in ALIASES:
                problems.append((i, f"Unknown glyph: {cmd}"))
        if problems:
            print("Syntax check found problems:")
            for ln, msg in problems:
                print(f"  Line {ln}: {msg}")
        else:
            print("No syntax problems found.")
    except Exception as e:
        print("Check failed:", e)

# Profiles (prof), reload/save config commands
def cmd_prof(args: List[str]):
    global CURRENT_PROFILE, ALIASES, VARIABLES
    # list profiles
    if not args:
        profiles = ["default"]
        try:
            for f in os.listdir(SIGIL_CONFIG_DIR):
                if f.startswith(".sigilrc.") and not f.endswith(".bak"):
                    profiles.append(f.replace(".sigilrc.", ""))
        except Exception:
            pass
        for p in sorted(set(profiles)):
            print(p)
        return
    # show
    if args[0] == "show":
        print(f"current profile: {CURRENT_PROFILE}")
        return
    # new
    if args[0] == "new" and len(args) == 2:
        name = args[1]
        path = rc_path(name)
        if os.path.exists(path):
            print("profile already exists")
            return
        open(path, "w", encoding="utf-8").close()
        print(f"created profile: {name}")
        return
    # delete
    if args[0] == "del" and len(args) == 2:
        name = args[1]
        if name == "default":
            print("cannot delete default profile")
            return
        path = rc_path(name)
        if not os.path.exists(path):
            print("profile not found")
            return
        os.remove(path)
        print(f"deleted profile: {name}")
        return
    # switch
    name = args[0]
    CURRENT_PROFILE = name
    ALIASES.clear()
    VARIABLES.clear()
    path = rc_path()
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").close()
    load_sigilrc()
    print(f"profile switched to: {name}")

def cmd_rrc(args: List[str]):
    load_sigilrc()
    print(f"{os.path.basename(rc_path())} reloaded")

def cmd_svrc(args: List[str]):
    save_sigilrc()
    print(f"config saved ({os.path.basename(rc_path())})")

# NEW: pause command (pse)
def cmd_pse(args: List[str]):
    """
    pse [message]
    Pause so the user can inspect output.
    - If a message is provided it'll be printed before waiting.
    - On Windows: waits for any keypress (msvcrt.getch).
    - On other OSes: prompts and waits for Enter.
    """
    msg = ""
    if args:
        joined = " ".join(args)
        if len(joined) >= 2 and joined[0] == '"' and joined[-1] == '"':
            msg = joined[1:-1]
        else:
            msg = joined
    try:
        if msg:
            # print message without extra newline if it already ends with one
            if msg.endswith("\n"):
                print(msg, end="", flush=True)
            else:
                print(msg, end="", flush=True)
        if msvcrt:
            # Windows: any key
            print(" (press any key to continue)", end="", flush=True)
            msvcrt.getch()
            print("")  # newline
        else:
            input(" (press Enter to continue)")
    except Exception:
        time.sleep(1)

# =============================
# Plugin command wrappers
# =============================
def cmd_pin(args: List[str]):
    """
    pin <path-to-plugin.sigin>  -> install plugin from archive or folder
    pin                         -> list installed plugins
    """
    if not args:
        list_installed_plugins()
        return
    path = args[0]
    # allow ~ expansion
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = resolve(path)
    install_plugin_from_path(path)

def cmd_prv(args: List[str]):
    """
    prv <plugin-name> -> Remove/uninstall plugin
    """
    if not args:
        print(HELP_TEXT["prv"])
        return
    name = args[0]
    uninstall_plugin(name)

# =============================
# Registry
# =============================
COMMANDS = {
    "help": cmd_help,
    "mk": cmd_mk,
    "cpy": cmd_cpy,
    "dlt": cmd_dlt,
    "move": cmd_move,
    "cd": cmd_cd,
    "dirlook": cmd_dirlook,
    "opnlnk": cmd_opnlnk,
    "opn": cmd_opn,
    "ex": cmd_ex,
    "task": cmd_task,
    "kill": cmd_kill,
    "clo": cmd_clo,
    "say": cmd_say,
    "undo": cmd_undo,
    "redo": cmd_redo,
    "edt": cmd_edt,
    "sdow": cmd_sdow,
    "rstr": cmd_rstr,
    "bored": cmd_bored,
    "add": cmd_add,
    "sub": cmd_sub,
    "mul": cmd_mul,
    "div": cmd_div,
    "alia": cmd_alia,
    "unalia": cmd_unalia,
    "let": cmd_let,
    "var": cmd_var,
    "unset": cmd_unset,
    "if": cmd_if,
    "wait": cmd_wait,
    "sleep": cmd_wait,
    "renm": cmd_renm,
    "rename": cmd_renm,
    "siz": cmd_siz,
    "size": cmd_siz,
    "pwd": cmd_pwd,
    "opnapp": cmd_opnapp,
    "run": cmd_run,
    "inc": cmd_inc,
    "include": cmd_inc,
    "fmt": cmd_fmt,
    "schk": cmd_schk,
    "prof": cmd_prof,
    "rrc": cmd_rrc,
    "svrc": cmd_svrc,
    "pse": cmd_pse,
    # plugin management commands
    "pin": cmd_pin,
    "prv": cmd_prv,
}

# =============================
# Interpreter
# =============================
def execute_line(line: str, from_rc: bool = False):
    # strip comments first
    stripped, _ = strip_comments_from_line(line, False)
    if not stripped:
        return
    # expand aliases and variables
    expanded = expand_aliases_and_vars(stripped)
    parts = tokenize(expanded)
    if not parts:
        return
    cmd = parts[0]
    args = parts[1:]
    if cmd in COMMANDS:
        try:
            COMMANDS[cmd](args)
        except Exception as e:
            print(f"Error executing {cmd}: {e}")
    else:
        # maybe alias exists untreated
        if cmd in ALIASES:
            new_line = ALIASES[cmd] + (" " + " ".join(args) if args else "")
            execute_line(new_line, from_rc=from_rc)
        else:
            print(f"Unknown glyph: {cmd} (try 'help')")

def run_lines(lines: List[str], from_rc: bool = False):
    """Run a list of lines. Handles block comments across lines."""
    in_block = False
    for raw in lines:
        line = raw.rstrip("\n")
        if in_block:
            # check for end of block inside this line
            end_idx = line.find("*/")
            if end_idx == -1:
                # still in block
                continue
            else:
                line = line[end_idx+2:]
                in_block = False
        # strip comments (this returns state but we handle block manually)
        stripped, enters_block = strip_comments_from_line(line, False)
        if enters_block:
            # a '/*' started and not closed on same line; mark and continue
            # we still process the part before the block (strip_comments_from_line removed block)
            in_block = True
        if not stripped:
            continue
        execute_line(stripped, from_rc=from_rc)

# =============================
# Utilities
# =============================
def resolve(path: str) -> str:
    # Support absolute paths as-is
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(CURRENT_DIR, path))

# =============================
# REPL / entrypoint
# =============================
def main():
    # load plugin registry and load plugins before rc so plugin commands are available in rc
    load_plugins_on_startup()

    # initial load of rc (from SIGIL_CONFIG_DIR)
    load_sigilrc()
    # handle file execution
    if len(sys.argv) > 1 and sys.argv[1].strip():
        script = sys.argv[1].strip()
        if not os.path.exists(script):
            print(f"File not found: {script}")
            return
        with open(script, "r", encoding="utf-8") as f:
            file_lines = f.readlines()
        run_lines(file_lines)
        return
    # interactive REPL
    print("🔮 Sigil REPL — type 'help' for glyphs, 'exit' to leave")
    while True:
        try:
            line = input("sigil> ")
        except EOFError:
            break
        if not line:
            continue
        if line.strip() in ("exit", "quit"):
            break
        run_lines([line])

if __name__ == "__main__":
    main()
