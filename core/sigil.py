#!/usr/bin/env python3
"""
Sigil engine — full version (single-file)
Includes:
- persistent aliases/variables stored in C:\Sigil (per-profile .sigilrc files)
- profile management (prof)
- many utility commands
- simple shell bridges: ps, cmd (alias cp), sh
- variables, let/ask sugar, single-quote shorthand
- rpt loops, exists, arg, script.dir/file
- comments via &, #, //, /* ... */
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
SIGIL_CONFIG_DIR = os.path.abspath(r"C:\Sigil")
os.makedirs(SIGIL_CONFIG_DIR, exist_ok=True)

PLUGIN_DIR = os.path.join(SIGIL_CONFIG_DIR, "plugins")
os.makedirs(PLUGIN_DIR, exist_ok=True)
_PLUGIN_REGISTRY_PATH = os.path.join(PLUGIN_DIR, "plugins.json")

CURRENT_PROFILE = "default"
CURRENT_DIR = os.getcwd()

# script-related info (set when running a script)
SCRIPT_FILE: str = ""
SCRIPT_DIR: str = ""
SCRIPT_ARGS: List[str] = []

UNDO_STACK: List[dict] = []
REDO_STACK: List[dict] = []
UNDO_LIMIT = 200
UNDO_BASE = os.path.join(tempfile.gettempdir(), "sigil_undo")
os.makedirs(UNDO_BASE, exist_ok=True)

ALIASES: dict = {}     # name -> command string
VARIABLES: dict = {}   # name -> value (str/int/float)
EXPORTED_VARS: set = set()   # names exported to OS env
READONLY_VARS: set = set()   # names marked readonly via let -r

LOADING_RC = False  # guard: true while load_sigilrc is running

PLUGIN_REGISTRY: dict = {}

# =============================
# Helpers: rc persistence
# =============================
def rc_path(profile: str | None = None) -> str:
    name = profile or CURRENT_PROFILE
    if name == "default":
        return os.path.join(SIGIL_CONFIG_DIR, ".sigilrc")
    return os.path.join(SIGIL_CONFIG_DIR, f".sigilrc.{name}")

def save_sigilrc() -> None:
    """Write current ALIASES, VARIABLES and metadata to the active profile rc file."""
    path = rc_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Sigil RC — profile: {CURRENT_PROFILE}\n")
            f.write("# Aliases\n")
            for k, v in ALIASES.items():
                f.write(f"alia {k} {v}\n")
            f.write("\n# Variables\n")
            for k, v in VARIABLES.items():
                if isinstance(v, str):
                    needs_quote = any(ch.isspace() for ch in v) or v == ""
                    v_escaped = v.replace('"', '\\"')
                    if needs_quote:
                        f.write(f'let {k} = "{v_escaped}"\n')
                    else:
                        f.write(f"let {k} = {v_escaped}\n")
                else:
                    f.write(f"let {k} = {v}\n")
            # record readonly list
            if READONLY_VARS:
                for name in sorted(READONLY_VARS):
                    f.write(f"let -r {name} = {VARIABLES.get(name, '')}\n")
            # record exported (best-effort)
            if EXPORTED_VARS:
                for name in sorted(EXPORTED_VARS):
                    f.write(f"export {name}\n")
    except Exception as e:
        print(f"Failed to save .sigilrc: {e}")

def load_sigilrc() -> None:
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
    # New behavior: support '&' as comment starter (kid-friendly), plus existing //, #, /* */
    if in_block_comment:
        end_idx = line.find("*/")
        if end_idx == -1:
            return "", True
        line = line[end_idx+2:]
        in_block_comment = False
    # handle block comments /* ... */
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
    # if first non-space character is '&', treat entire line as comment
    stripped_line = line.lstrip()
    if stripped_line.startswith('&'):
        return "", in_block_comment
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
            if c == '&':
                break
        result.append(c)
        i += 1
    stripped = "".join(result).rstrip()
    return stripped, in_block_comment

# =============================
# Variable interpolation helpers
# =============================
_varname_re = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')

def expand_vars_in_string(s: str) -> str:
    """Expand $name and ${name} inside the given string using VARIABLES then os.environ.
       If not found, leave empty string for $name or preserve original? We'll use empty string fallback.
    """
    out = []
    i = 0
    L = len(s)
    while i < L:
        c = s[i]
        if c == '\\\\' and i + 1 < L:
            out.append(s[i+1])
            i += 2
            continue
        if c == '$':
            # ${name} or $name
            if i + 1 < L and s[i+1] == '{':
                j = s.find('}', i+2)
                if j == -1:
                    # no close, treat literally
                    out.append(s[i])
                    i += 1
                    continue
                name = s[i+2:j]
                val = VARIABLES.get(name, os.environ.get(name, ""))
                out.append(str(val))
                i = j + 1
                continue
            else:
                # parse bare name
                j = i + 1
                match = _varname_re.match(s[j:])  # match from j
                if match:
                    name = match.group(0)
                    val = VARIABLES.get(name, os.environ.get(name, ""))
                    out.append(str(val))
                    i = j + len(name)
                    continue
                else:
                    # solitary $, keep
                    out.append('$')
                    i += 1
                    continue
        else:
            out.append(c)
            i += 1
    return "".join(out)

def _safe_plugin_name(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_\-]', '_', name).strip('_')

def expand_aliases_and_vars(line: str) -> str:
    """Expand alias (if first token is alias) and substitute variables.
       Variables expand in forms:
       - single-quoted token 'name' -> replaced by variable value (shorthand)
       - double-quoted strings have interpolation inside
       - $name and ${name} anywhere inside tokens
       - bare token equal to variable name -> replaced
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
        return expand_aliases_and_vars(new_line)
    new_tokens = []
    for t in tokens:
        # single-quoted token: treat as variable reference shorthand
        if len(t) >= 2 and t[0] == "'" and t[-1] == "'":
            inner = t[1:-1]
            if inner in VARIABLES:
                new_tokens.append(str(VARIABLES[inner]))
            elif inner in os.environ:
                new_tokens.append(os.environ[inner])
            else:
                new_tokens.append(inner)
            continue
        # double-quoted: interpolate inside and keep quotes
        if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
            inner = t[1:-1]
            inner_expanded = expand_vars_in_string(inner)
            new_tokens.append('"' + inner_expanded.replace('"', '\\"') + '"')
            continue
        # token contains $ => expand within token
        if '$' in t:
            new_tokens.append(expand_vars_in_string(t))
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
    "help": "help [command]\n  Show all commands or help for a specific command\n\nComments: & single-line, # single-line, // single-line, /* ... */ block comments",
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
    "let": "let <name> = <value>\n  Define a variable (string or number). Use variable by name or $name.\n  Also: let name  (declare empty), let -r name = value (readonly), let name = ask \"Prompt\"",
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
    "ps": "ps [command]\n  Run a PowerShell command (or open interactive PowerShell if no args)",
    "cmd": "cmd [command]\n  Run a Command Prompt (cmd.exe) command (or open interactive cmd if no args)",
    "cp": "cp [command]\n  Shortcut for Command Prompt (cmd.exe)",
    "sh": "sh [command]\n  Run a POSIX shell command (or open interactive shell if no args)",
    "rpt": "rpt <count|inf> <command...>  or block form with endrpt\n  Repeat a command multiple times (rpt 10 say hi) or forever (rpt inf).",
    "ask": "ask <name> [prompt]\n  Prompt the user and store input in variable <name> (also supports ask = name)",
    "exit": "exit [code]\n  Exit Sigil with optional exit code",
    "exists": "exists <path>\n  Print 'yes' if path exists, 'no' otherwise; sets last=0 for yes, last=1 for no",
    "arg": "arg <n> | arg count\n  Access script arguments (1-based); 'arg count' returns number of arguments",
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
            try:
                nums.append(float(t))
            except Exception:
                nums.append(0)
    return nums

# =============================
# Plugin helpers (kept minimal)
# =============================
def _save_registry():
    try:
        with open(_PLUGIN_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(PLUGIN_REGISTRY, f, indent=2)
    except Exception:
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
    if not os.path.exists(archive_path):
        raise FileNotFoundError("Archive not found")
    base = os.path.basename(archive_path)
    base_noext = os.path.splitext(base)[0]
    raw_name = name_hint or base_noext
    plugin_name = _safe_plugin_name(raw_name)
    extract_dir = os.path.join(PLUGIN_DIR, plugin_name)
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
    info = {}
    pm_path = os.path.join(extract_dir, "plugin-main.py")
    if os.path.exists(pm_path):
        try:
            g = runpy.run_path(pm_path, run_name="__sigil_plugin_info__")
            if "PLUGIN_INFO" in g and isinstance(g["PLUGIN_INFO"], dict):
                info = g["PLUGIN_INFO"]
                if "name" in info:
                    plugin_name = _safe_plugin_name(info["name"])
                    desired_dir = os.path.join(PLUGIN_DIR, plugin_name)
                    if desired_dir != extract_dir:
                        if os.path.exists(desired_dir):
                            pass
                        else:
                            shutil.move(extract_dir, desired_dir)
                            extract_dir = desired_dir
        except Exception:
            pass
    archive_dest = os.path.join(PLUGIN_DIR, plugin_name + ".sigin")
    try:
        if os.path.abspath(archive_path) != os.path.abspath(archive_dest):
            shutil.copy2(archive_path, archive_dest)
    except Exception:
        pass
    plugin_entry = {
        "archive": os.path.abspath(archive_dest),
        "extract_dir": os.path.abspath(extract_dir),
        "commands": [],
        "info": info
    }
    return plugin_name, plugin_entry

def _load_plugin_commands(plugin_name: str, plugin_entry: dict):
    pdir = plugin_entry.get("extract_dir")
    if not pdir or not os.path.isdir(pdir):
        return
    plugin_py = os.path.join(pdir, "plugin.py")
    if not os.path.exists(plugin_py):
        return
    try:
        g = runpy.run_path(plugin_py, run_name=f"__sigil_plugin_{plugin_name}__")
        if "register" in g and callable(g["register"]):
            helpers = {
                "config_dir": SIGIL_CONFIG_DIR,
                "plugin_dir": PLUGIN_DIR,
                "resolve": resolve,
            }
            reg_result = g["register"](COMMANDS, helpers)
            added_cmds = []
            if isinstance(reg_result, dict):
                for name, fn in reg_result.items():
                    if callable(fn):
                        COMMANDS[name] = fn
                        added_cmds.append(name)
            elif isinstance(reg_result, list):
                for name in reg_result:
                    if name in COMMANDS:
                        added_cmds.append(name)
            if "COMMANDS" in g and isinstance(g["COMMANDS"], dict):
                for name, fn in g["COMMANDS"].items():
                    if callable(fn):
                        COMMANDS[name] = fn
                        added_cmds.append(name)
            plugin_entry["commands"] = sorted(set(plugin_entry.get("commands", []) + added_cmds))
    except Exception as e:
        print(f"Plugin '{plugin_name}' load error: {e}")

def load_plugins_on_startup():
    _load_registry()
    try:
        for item in os.listdir(PLUGIN_DIR):
            p = os.path.join(PLUGIN_DIR, item)
            if item.endswith(".sigin"):
                name = os.path.splitext(item)[0]
                if name not in PLUGIN_REGISTRY:
                    try:
                        _, entry = _plugin_extract_and_register(p, name_hint=name)
                        PLUGIN_REGISTRY[name] = entry
                    except Exception:
                        pass
            elif os.path.isdir(p):
                name = item
                if name not in PLUGIN_REGISTRY:
                    archive_guess = os.path.join(PLUGIN_DIR, name + ".sigin")
                    entry = {"archive": os.path.abspath(archive_guess) if os.path.exists(archive_guess) else "",
                             "extract_dir": os.path.abspath(p),
                             "commands": [],
                             "info": {}}
                    PLUGIN_REGISTRY[name] = entry
    except Exception:
        pass
    for name, entry in list(PLUGIN_REGISTRY.items()):
        try:
            _load_plugin_commands(name, entry)
        except Exception:
            pass
    _save_registry()

# =============================
# Simple shell helpers (no flags)
# =============================
def _run_and_print(cmd_list: List[str], interactive: bool = False) -> int:
    try:
        if interactive:
            cp = subprocess.run(cmd_list)
            rc = cp.returncode if hasattr(cp, 'returncode') else 0
        else:
            cp = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = cp.stdout.decode(errors='replace')
            err = cp.stderr.decode(errors='replace')
            if out:
                print(out, end='')
            if err:
                print(err, end='', flush=True)
            rc = cp.returncode
    except FileNotFoundError:
        print(f"Shell not found: {cmd_list[0]}")
        rc = 127
    except Exception as e:
        print(f"Error running subprocess: {e}")
        rc = 1
    set_last(rc)
    return int(rc)

def cmd_ps(args: List[str]):
    pwsh = shutil.which('pwsh') or shutil.which('powershell')
    if not pwsh:
        print("PowerShell not found on PATH")
        set_last(127)
        return
    if not args:
        _run_and_print([pwsh], interactive=True)
        return
    cmdstr = " ".join(args)
    _run_and_print([pwsh, '-NoProfile', '-NonInteractive', '-Command', cmdstr])

def cmd_cmd(args: List[str]):
    if not args:
        if os.name == 'nt':
            _run_and_print(['cmd'], interactive=True)
        else:
            _run_and_print([os.environ.get('SHELL','/bin/sh')], interactive=True)
        return
    cmdstr = " ".join(args)
    if os.name == 'nt':
        _run_and_print(['cmd', '/c', cmdstr])
    else:
        _run_and_print([os.environ.get('SHELL','/bin/sh'), '-c', cmdstr])

def cmd_sh(args: List[str]):
    shell = os.environ.get('SHELL') or shutil.which('bash') or shutil.which('sh')
    if not shell:
        print("No POSIX shell found")
        set_last(127)
        return
    if not args:
        _run_and_print([shell], interactive=True)
        return
    cmdstr = " ".join(args)
    if os.path.basename(shell) == 'bash':
        _run_and_print([shell, '-lc', cmdstr])
    else:
        _run_and_print([shell, '-c', cmdstr])

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
        set_last(1)
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
            set_last(1)
            return
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
    push_undo({"op": "cpy", "src": src, "dst": dst, "dst_existed": dst_existed, "dst_backup": dst_backup})
    set_last(0)
    print("ok")

def cmd_dlt(args: List[str]):
    if not args:
        print(HELP_TEXT["dlt"])
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Path does not exist")
        set_last(1)
        return
    backup = make_backup_of_path(path)
    push_undo({"op": "dlt", "path": path, "backup": backup})
    set_last(0)
    print("ok")

def cmd_move(args: List[str]):
    if len(args) < 3 or args[0] != "file":
        print(HELP_TEXT["move"])
        set_last(1)
        return
    src = resolve(args[1])
    dst = resolve(args[2])
    if not os.path.exists(src):
        print("Source does not exist")
        set_last(1)
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
    set_last(0)
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
    set_last(0)
    print("ok")

def cmd_opn(args: List[str]):
    if not args:
        print(HELP_TEXT["opn"])
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Path does not exist")
        set_last(1)
        return
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        set_last(0)
        print("ok")
    except Exception as e:
        print("Error opening:", e)
        set_last(1)

def cmd_ex(args: List[str]):
    if os.name == "nt":
        subprocess.Popen(["explorer", CURRENT_DIR])
        set_last(0)
        print("ok")
    else:
        print("Explorer not supported on this OS")
        set_last(1)

def cmd_task(args: List[str]):
    try:
        if os.name == "nt":
            out = subprocess.check_output(["tasklist"]).decode(errors='ignore')
            print(out)
        else:
            out = subprocess.check_output(["ps", "-e"]).decode(errors='ignore')
            print(out)
        set_last(0)
    except Exception as e:
        print("Error listing tasks:", e)
        set_last(1)

def cmd_kill(args: List[str]):
    if len(args) < 2 or args[0] != "task":
        print(HELP_TEXT["kill"])
        set_last(1)
        return
    name = args[1]
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", name, "/F"])
        else:
            subprocess.run(["pkill", name])
        print("ok")
        set_last(0)
    except Exception as e:
        print("Error killing task:", e)
        set_last(1)

def cmd_say(args: List[str]):
    parts: List[str] = []
    for t in args:
        if t.startswith("$") and t[1:] in VARIABLES:
            parts.append(str(VARIABLES[t[1:]]))
        elif t in VARIABLES:
            parts.append(str(VARIABLES[t]))
        else:
            # allow raw tokens to be printed (they may already have had interpolation)
            parts.append(t)
    print(" ".join(parts))
    set_last(0)

# Arithmetic & misc
def cmd_add(args: List[str]):
    if not args:
        print("Usage: add <n1> <n2> [<n3> ...]")
        set_last(1)
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        set_last(1)
        return
    total = nums[0]
    for n in nums[1:]:
        total += n
    if isinstance(total, float) and total.is_integer():
        total = int(total)
    print(total)
    set_last(0)

def cmd_sub(args: List[str]):
    if not args or len(args) < 2:
        print("Usage: sub <n1> <n2> [<n3> ...]")
        set_last(1)
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        set_last(1)
        return
    result = nums[0]
    for n in nums[1:]:
        result -= n
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    print(result)
    set_last(0)

def cmd_mul(args: List[str]):
    if not args:
        print("Usage: mul <n1> <n2> [<n3> ...]")
        set_last(1)
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        set_last(1)
        return
    prod = nums[0]
    for n in nums[1:]:
        prod *= n
    if isinstance(prod, float) and prod.is_integer():
        prod = int(prod)
    print(prod)
    set_last(0)

def cmd_div(args: List[str]):
    if not args or len(args) < 2:
        print("Usage: div <n1> <n2> [<n3> ...]")
        set_last(1)
        return
    try:
        nums = _parse_numbers(args)
    except Exception as e:
        print("Error parsing numbers:", e)
        set_last(1)
        return
    result = float(nums[0])
    try:
        for n in nums[1:]:
            if n == 0:
                print("Error: division by zero")
                set_last(1)
                return
            result /= n
    except Exception as e:
        print("Error during division:", e)
        set_last(1)
        return
    if result.is_integer():
        result = int(result)
    print(result)
    set_last(0)

def cmd_clo(args: List[str]):
    if len(args) < 2 or args[0] != "task":
        print("Usage: clo task <name>")
        set_last(1)
        return
    name = args[1]
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", name])
        else:
            subprocess.run(["pkill", name])
        print("ok")
        set_last(0)
    except Exception as e:
        print("Error closing task:", e)
        set_last(1)

def cmd_rstr(args: List[str]):
    if len(args) == 1 and args[0].lower() == "confirm":
        print("Restarting — immediate. Press Ctrl+C to cancel in the next 2 seconds.")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("Restart cancelled.")
            set_last(1)
            return
        if os.name == "nt":
            subprocess.run(["shutdown", "/r", "/t", "0"])
        else:
            subprocess.run(["shutdown", "-r", "now"])
        set_last(0)
    else:
        print("rstr is destructive. To confirm use: rstr confirm")
        set_last(1)

# Undo/redo helpers (kept from original)
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
        set_last(1)
        return
    action = UNDO_STACK.pop()
    inverse = perform_undo_action(action)
    if inverse:
        REDO_STACK.append(inverse)
    else:
        REDO_STACK.append({"op": "noop"})
    set_last(0)
    print("Undone.")

def cmd_redo(args: List[str]):
    if not REDO_STACK:
        print("Nothing to redo")
        set_last(1)
        return
    action = REDO_STACK.pop()
    inverse = perform_redo_action(action)
    if inverse:
        UNDO_STACK.append(inverse)
    else:
        UNDO_STACK.append({"op": "noop"})
    set_last(0)
    print("Redone.")

def cmd_edt(args: List[str]):
    if not args:
        print(HELP_TEXT["edt"])
        set_last(1)
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
        push_undo({"op": "edit", "path": path, "backup": backup})
        set_last(0)
        print("ok")
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Edit aborted.")
        set_last(1)

def cmd_sdow(args: List[str]):
    if len(args) == 1 and args[0].lower() == "confirm":
        print("Shutting down — immediate. Press Ctrl+C to cancel in the next 2 seconds.")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("Shutdown cancelled.")
            set_last(1)
            return
        if os.name == "nt":
            subprocess.run(["shutdown", "/s", "/t", "0"])
        else:
            subprocess.run(["shutdown", "-h", "now"])
        set_last(0)
    else:
        print("sdow is destructive. To confirm use: sdow confirm")
        set_last(1)

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
    set_last(0)
    print("Bored mode stopped.")

# Aliases, variables, config management
def cmd_alia(args: List[str]):
    if not args:
        if not ALIASES:
            print("no aliases defined")
            set_last(1)
            return
        for k, v in ALIASES.items():
            print(f"{k} -> {v}")
        set_last(0)
        return
    if len(args) >= 2:
        name = args[0]
        cmd_str = " ".join(args[1:])
        ALIASES[name] = cmd_str
        if not LOADING_RC:
            save_sigilrc()
        set_last(0)
        print(f"Alias set: {name} -> {cmd_str}")
        return
    print("Usage: alia <name> <command>")
    set_last(1)

def cmd_unalia(args: List[str]):
    if not args:
        print("Usage: unalia <name>")
        set_last(1)
        return
    name = args[0]
    if name in ALIASES:
        del ALIASES[name]
        if not LOADING_RC:
            save_sigilrc()
        set_last(0)
        print(f"Alias removed: {name}")
    else:
        print("Alias not found")
        set_last(1)

def cmd_let(args: List[str]):
    if not args:
        print(HELP_TEXT["let"])
        set_last(1)
        return
    readonly = False
    if args[0] == "-r":
        readonly = True
        args = args[1:]
    if len(args) == 1:
        name = args[0]
        v = ""
    elif len(args) >= 3 and args[1] == "=":
        name = args[0]
        val = " ".join(args[2:])
    elif len(args) >= 2:
        name = args[0]
        val = " ".join(args[1:])
    else:
        print("Usage: let <name> = <value>")
        set_last(1)
        return
    # support sugar: let x = ask "Prompt"
    if 'v' not in locals():
        toks = tokenize(val)
        if toks and toks[0] == 'ask':
            if len(toks) >= 2:
                prompt_part = " ".join(toks[1:])
                if len(prompt_part) >= 2 and prompt_part[0] == '"' and prompt_part[-1] == '"':
                    prompt = prompt_part[1:-1]
                else:
                    prompt = expand_vars_in_string(prompt_part)
            else:
                prompt = ""
            try:
                entered = input(prompt + (" " if prompt else ""))
            except EOFError:
                entered = ""
            v = entered
        else:
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1].replace('\\"', '"')
                val = expand_vars_in_string(val)
            else:
                val = expand_vars_in_string(val)
            try:
                if isinstance(val, str) and ("." in val or "e" in val.lower()):
                    v = float(val)
                else:
                    v = int(val)
            except Exception:
                v = val
    if name in READONLY_VARS and not readonly:
        print(f"Cannot overwrite readonly variable: {name}")
        set_last(1)
        return
    VARIABLES[name] = v
    if readonly:
        READONLY_VARS.add(name)
    else:
        READONLY_VARS.discard(name)
    if not LOADING_RC:
        save_sigilrc()
    set_last(0)
    print(f"Set {name} = {v}")

def cmd_var(args: List[str]):
    if not VARIABLES:
        print("no variables defined")
        set_last(1)
        return
    for k, v in VARIABLES.items():
        ro = " (readonly)" if k in READONLY_VARS else ""
        exp = " (exported)" if k in EXPORTED_VARS else ""
        print(f"{k} = {v}{ro}{exp}")
    set_last(0)

def cmd_unset(args: List[str]):
    if not args:
        print("Usage: unset <name>")
        set_last(1)
        return
    name = args[0]
    if name in VARIABLES:
        if name in READONLY_VARS:
            print("Cannot unset readonly variable")
            set_last(1)
            return
        del VARIABLES[name]
        EXPORTED_VARS.discard(name)
        if not LOADING_RC:
            save_sigilrc()
        print(f"unset {name}")
        set_last(0)
    else:
        print("variable not found")
        set_last(1)

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
        set_last(1)
        return
    try:
        then_i = args.index("then")
    except ValueError:
        print("Usage: if <cond> then <cmd>")
        set_last(1)
        return
    cond_tokens = args[:then_i]
    cmd_tokens = args[then_i+1:]
    if _eval_condition(cond_tokens):
        run_lines([" ".join(cmd_tokens)])
        set_last(0)
    else:
        set_last(1)

def cmd_wait(args: List[str]):
    if not args:
        print("Usage: wait <seconds>")
        set_last(1)
        return
    try:
        s = float(args[0])
    except Exception:
        print("Invalid number")
        set_last(1)
        return
    time.sleep(s)
    set_last(0)

def cmd_renm(args: List[str]):
    if len(args) < 2:
        print("Usage: renm <old> <new>")
        set_last(1)
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
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("Not found")
        set_last(1)
        return
    if os.path.isfile(path):
        print(os.path.getsize(path))
    else:
        print(_dir_size(path))
    set_last(0)

def cmd_pwd(args: List[str]):
    print(CURRENT_DIR)
    set_last(0)

def cmd_opnapp(args: List[str]):
    if not args:
        print("Usage: opnapp <name>")
        set_last(1)
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
        set_last(0)
        return
    try:
        if os.name == "nt":
            subprocess.Popen(["start", "", name], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        print("ok")
        set_last(0)
    except Exception as e:
        print("Failed to launch:", e)
        set_last(1)

def cmd_run(args: List[str]):
    if not args:
        print("Usage: run <file.sig>")
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        set_last(1)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # when running a script via run, set script context locally
        prev_file = SCRIPT_FILE
        prev_dir = SCRIPT_DIR
        prev_args = SCRIPT_ARGS[:]
        try:
            run_lines(lines)
        finally:
            # restore
            SCRIPT_FILE = prev_file
            SCRIPT_DIR = prev_dir
            SCRIPT_ARGS = prev_args
    except Exception as e:
        print("Error running script:", e)
        set_last(1)

def cmd_inc(args: List[str]):
    if not args:
        print("Usage: inc <file.sig>")
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        set_last(1)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        run_lines(lines)
    except Exception as e:
        print("Error including file:", e)
        set_last(1)

def cmd_fmt(args: List[str]):
    if not args:
        print("Usage: fmt <file.sig>")
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        set_last(1)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [ln.rstrip() for ln in lines]
        out_text = "\n".join(new_lines).rstrip() + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(out_text)
        print("Formatted:", path)
        set_last(0)
    except Exception as e:
        print("Format failed:", e)
        set_last(1)

def cmd_schk(args: List[str]):
    if not args:
        print("Usage: schk <file.sig>")
        set_last(1)
        return
    path = resolve(args[0])
    if not os.path.exists(path):
        print("File not found")
        set_last(1)
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
            set_last(1)
        else:
            print("No syntax problems found.")
            set_last(0)
    except Exception as e:
        print("Check failed:", e)
        set_last(1)

# Profiles (prof), reload/save config commands
def cmd_prof(args: List[str]):
    global CURRENT_PROFILE, ALIASES, VARIABLES
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
        set_last(0)
        return
    if args[0] == "show":
        print(f"current profile: {CURRENT_PROFILE}")
        set_last(0)
        return
    if args[0] == "new" and len(args) == 2:
        name = args[1]
        path = rc_path(name)
        if os.path.exists(path):
            print("profile already exists")
            set_last(1)
            return
        open(path, "w", encoding="utf-8").close()
        print(f"created profile: {name}")
        set_last(0)
        return
    if args[0] == "del" and len(args) == 2:
        name = args[1]
        if name == "default":
            print("cannot delete default profile")
            set_last(1)
            return
        path = rc_path(name)
        if not os.path.exists(path):
            print("profile not found")
            set_last(1)
            return
        os.remove(path)
        print(f"deleted profile: {name}")
        set_last(0)
        return
    name = args[0]
    CURRENT_PROFILE = name
    ALIASES.clear()
    VARIABLES.clear()
    path = rc_path()
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").close()
    load_sigilrc()
    print(f"profile switched to: {name}")
    set_last(0)

def cmd_rrc(args: List[str]):
    load_sigilrc()
    print(f"{os.path.basename(rc_path())} reloaded")
    set_last(0)

def cmd_svrc(args: List[str]):
    save_sigilrc()
    print(f"config saved ({os.path.basename(rc_path())})")
    set_last(0)

# NEW: pause command (pse)
def cmd_pse(args: List[str]):
    msg = ""
    if args:
        joined = " ".join(args)
        if len(joined) >= 2 and joined[0] == '"' and joined[-1] == '"':
            msg = joined[1:-1]
        else:
            msg = joined
    try:
        if msg:
            if msg.endswith("\n"):
                print(msg, end="", flush=True)
            else:
                print(msg, end="", flush=True)
        if msvcrt:
            print(" (press any key to continue)", end="", flush=True)
            msvcrt.getch()
            print("")
        else:
            input(" (press Enter to continue)")
        set_last(0)
    except Exception:
        time.sleep(1)
        set_last(1)

# Plugin command wrappers
def install_plugin_from_path(path: str):
    if not os.path.exists(path):
        print("Plugin archive not found:", path)
        return
    if os.path.isdir(path):
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
    try:
        plugin_name, entry = _plugin_extract_and_register(archive_path)
    except zipfile.BadZipFile:
        print("Not a valid .sigin archive.")
        return
    except Exception as e:
        print("Install failed:", e)
        return
    try:
        pm = os.path.join(entry["extract_dir"], "plugin-main.py")
        if os.path.exists(pm):
            runpy.run_path(pm, run_name=f"__sigil_plugin_install_{plugin_name}__")
    except Exception as e:
        print(f"Plugin-install hook error: {e}")
    try:
        _load_plugin_commands(plugin_name, entry)
    except Exception:
        pass
    PLUGIN_REGISTRY[plugin_name] = entry
    _save_registry()
    print(f"Plugin installed: {plugin_name}")

def uninstall_plugin(name: str):
    safe_name = _safe_plugin_name(name)
    if safe_name not in PLUGIN_REGISTRY:
        print("Plugin not found:", name)
        return
    entry = PLUGIN_REGISTRY[safe_name]
    cmds = entry.get("commands", []) or []
    for c in cmds:
        if c in COMMANDS:
            try:
                del COMMANDS[c]
            except Exception:
                pass
    ex = entry.get("extract_dir")
    try:
        if ex and os.path.exists(ex):
            shutil.rmtree(ex, ignore_errors=True)
    except Exception:
        pass
    arch = entry.get("archive")
    try:
        if arch and os.path.exists(arch):
            os.remove(arch)
    except Exception:
        pass
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
# Exit / last handling
# =============================
def set_last(code: int):
    try:
        icode = int(code)
    except Exception:
        icode = 1
    VARIABLES['last'] = icode
    VARIABLES['LAST'] = icode
    VARIABLES['LAST_EXIT'] = icode

# =============================
# Control primitives: ask, exit, rpt, exists, arg
# =============================
def cmd_ask(args: List[str]):
    if not args:
        print("Usage: ask <name> [prompt]  OR  ask = <name>")
        set_last(1)
        return
    if args[0] == "=":
        if len(args) < 2:
            print("Usage: ask = <name>")
            set_last(1)
            return
        name = args[1]
        prompt = ""
    else:
        name = args[0]
        prompt = " ".join(args[1:]) if len(args) > 1 else ""
        if len(prompt) >= 2 and prompt[0] == '"' and prompt[-1] == '"':
            prompt = prompt[1:-1]
    try:
        val = input(prompt + (" " if prompt else ""))
    except EOFError:
        val = ""
    VARIABLES[name] = val
    set_last(0)

def cmd_exit(args: List[str]):
    code = 0
    if args:
        try:
            code = int(args[0])
        except Exception:
            code = 1
    set_last(code)
    raise SystemExit(code)

def cmd_rpt(args: List[str]):
    if not args:
        print("Usage: rpt <count|inf> <command...>  or rpt <count|inf> (with endrpt block)")
        set_last(1)
        return
    count = args[0]
    if len(args) >= 2:
        cmdline = " ".join(args[1:])
        try:
            if str(count).lower() in ('inf', 'infinite', 'forever'):
                while True:
                    try:
                        run_lines([cmdline])
                    except KeyboardInterrupt:
                        break
            else:
                n = int(count)
                for _ in range(n):
                    run_lines([cmdline])
            set_last(0)
        except KeyboardInterrupt:
            set_last(0)
        except Exception as e:
            print("rpt error:", e)
            set_last(1)
    else:
        set_last(0)

def cmd_exists(args: List[str]):
    if not args:
        print(HELP_TEXT.get("exists", "exists <path>"))
        set_last(1)
        return
    path = resolve(args[0])
    if os.path.exists(path):
        print("yes")
        set_last(0)
    else:
        print("no")
        set_last(1)

def cmd_arg(args: List[str]):
    if not args:
        print(HELP_TEXT.get("arg", "arg <n> | arg count"))
        set_last(1)
        return
    if args[0].lower() == 'count':
        print(len(SCRIPT_ARGS))
        set_last(0)
        return
    try:
        idx = int(args[0])
    except Exception:
        print("Invalid argument index")
        set_last(1)
        return
    if 1 <= idx <= len(SCRIPT_ARGS):
        print(SCRIPT_ARGS[idx-1])
        set_last(0)
    else:
        print("")
        set_last(1)

# simple export command (map sigil var to OS env)
def cmd_export(args: List[str]):
    if not args:
        print("Usage: export NAME [NAME2 ...]")
        set_last(1)
        return
    for name in args:
        if name in VARIABLES:
            v = str(VARIABLES[name])
            os.environ[name] = v
            EXPORTED_VARS.add(name)
        else:
            print(f"variable not found: {name}")
    save_sigilrc()
    set_last(0)

# plugin wrapper commands
def cmd_pin(args: List[str]):
    if not args:
        list_installed_plugins()
        return
    path = args[0]
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = resolve(path)
    install_plugin_from_path(path)

def cmd_prv(args: List[str]):
    if not args:
        print(HELP_TEXT["prv"])
        set_last(1)
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
    "export": cmd_export,
    "ps": cmd_ps,
    "cmd": cmd_cmd,
    "cp": cmd_cmd,
    "sh": cmd_sh,
    "exists": cmd_exists,
    "arg": cmd_arg,
    "rpt": cmd_rpt,
    "ask": cmd_ask,
    "exit": cmd_exit,
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
# Interpreter: execute_line & run_lines
# =============================
def execute_line(line: str, from_rc: bool = False):
    stripped, _ = strip_comments_from_line(line, False)
    if not stripped:
        return
    expanded = expand_aliases_and_vars(stripped)
    parts = tokenize(expanded)
    if not parts:
        return
    cmd = parts[0]
    args = parts[1:]
    if cmd in COMMANDS:
        try:
            res = COMMANDS[cmd](args)
            if isinstance(res, int):
                set_last(res)
            else:
                if 'last' not in VARIABLES and 'LAST' not in VARIABLES and 'LAST_EXIT' not in VARIABLES:
                    set_last(0)
        except SystemExit as se:
            code = getattr(se, 'code', 0)
            set_last(code if code is not None else 0)
            raise
        except Exception as e:
            print(f"Error executing {cmd}: {e}")
            set_last(1)
    else:
        if cmd in ALIASES:
            new_line = ALIASES[cmd] + (" " + " ".join(args) if args else "")
            execute_line(new_line, from_rc=from_rc)
        else:
            print(f"Unknown glyph: {cmd} (try 'help')")
            set_last(1)

def run_lines(lines: List[str], from_rc: bool = False):
    """Run a list of lines. Handles block comments across lines and 'rpt' block form."""
    in_block = False
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        if in_block:
            end_idx = raw.find("*/")
            if end_idx == -1:
                i += 1
                continue
            else:
                raw = raw[end_idx+2:]
                in_block = False
        stripped, enters_block = strip_comments_from_line(raw, False)
        if enters_block:
            in_block = True
        if not stripped:
            i += 1
            continue
        parts = tokenize(stripped)
        if parts and parts[0] == 'rpt':
            if len(parts) >= 3:
                execute_line(stripped, from_rc=from_rc)
                i += 1
                continue
            count = parts[1] if len(parts) >= 2 else 'inf'
            block_lines = []
            j = i + 1
            while j < len(lines):
                raw2 = lines[j].rstrip("\n")
                s2, _ = strip_comments_from_line(raw2, False)
                if s2 and s2.strip() == 'endrpt':
                    break
                block_lines.append(lines[j])
                j += 1
            if j >= len(lines):
                print("rpt block not closed (missing 'endrpt')")
                set_last(1)
                return
            try:
                if str(count).lower() in ('inf', 'infinite', 'forever'):
                    while True:
                        try:
                            run_lines(block_lines, from_rc=from_rc)
                        except KeyboardInterrupt:
                            break
                else:
                    n = int(count)
                    for _ in range(n):
                        run_lines(block_lines, from_rc=from_rc)
            except KeyboardInterrupt:
                pass
            i = j + 1
            continue
        execute_line(stripped, from_rc=from_rc)
        i += 1

# =============================
# Utilities
# =============================
def resolve(path: str) -> str:
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(CURRENT_DIR, path))

# =============================
# REPL / entrypoint
# =============================
def main():
    global SCRIPT_FILE, SCRIPT_DIR, SCRIPT_ARGS, CURRENT_DIR
    load_plugins_on_startup()
    load_sigilrc()
    # initialize script-related variables for interactive sessions
    SCRIPT_FILE = ""
    SCRIPT_DIR = ""
    SCRIPT_ARGS = []
    VARIABLES['script.dir'] = SCRIPT_DIR
    VARIABLES['script.file'] = SCRIPT_FILE
    # handle file execution
    if len(sys.argv) > 1 and sys.argv[1].strip():
        script = sys.argv[1].strip()
        if not os.path.exists(script):
            print(f"File not found: {script}")
            return
        SCRIPT_FILE = os.path.abspath(script)
        SCRIPT_DIR = os.path.dirname(SCRIPT_FILE)
        SCRIPT_ARGS = sys.argv[2:]
        VARIABLES['script.dir'] = SCRIPT_DIR
        VARIABLES['script.file'] = SCRIPT_FILE
        with open(script, "r", encoding="utf-8") as f:
            file_lines = f.readlines()
        run_lines(file_lines)
        return
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
