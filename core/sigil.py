#!/usr/bin/env python3
"""
Sigil — Single-File Shell Engine (Polished Edition)

A feature-rich scripting shell with:
- Persistent profiles with aliases/variables
- Control flow: if/case/rpt/goto/labels
- File operations with undo support
- Graphical prompts and JSON manipulation
- Plugin system
- Cross-platform compatibility

Version: 1.0.1
License: NOT MIT
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
import zipfile
import json
import re
import getpass
import fnmatch  # Added for pattern matching
import urllib.request
import urllib.error
import ssl
from typing import List, Tuple, Any, Dict, Optional
from pathlib import Path

# ============================================================================
# PLATFORM DETECTION & IMPORTS
# ============================================================================

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    msvcrt = None
    HAS_MSVCRT = False

try:
    import select
    import termios
    import tty
    HAS_UNIX_TERM = True
except ImportError:
    select = None
    termios = None
    tty = None
    HAS_UNIX_TERM = False

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    HAS_TKINTER = True
except ImportError:
    tk = None
    tty = None
    messagebox = None
    HAS_TKINTER = False

# ============================================================================
# UPDATE CHECKER
# ============================================================================

class UpdateChecker:
    """Check for updates to Sigil"""
    
    VERSION_URL = "https://raw.githubusercontent.com/TheServer-lab/Sigil/main/version.txt"
    RELEASES_URL = "https://github.com/TheServer-lab/Sigil/releases"
    
    @staticmethod
    def check_for_updates(silent: bool = False, force_check: bool = False) -> bool:
        """
        Check if a newer version of Sigil is available
        
        Args:
            silent: If True, don't show any output unless update is available
            force_check: If True, ignore the check interval and force a check
            
        Returns:
            True if update is available, False otherwise
        """
        try:
            # Don't check too frequently (once per day)
            if not force_check:
                last_check_file = Config.CONFIG_DIR / ".last_update_check"
                if last_check_file.exists():
                    try:
                        last_check = float(last_check_file.read_text().strip())
                        # If checked within last 24 hours, skip
                        if time.time() - last_check < 86400:  # 24 hours in seconds
                            return False
                    except (ValueError, OSError):
                        pass
            
            if not silent:
                print("🔍 Checking for updates...")
            
            # Create SSL context to handle certificate verification
            ssl_context = ssl.create_default_context()
            
            # Fetch version file
            try:
                request = urllib.request.Request(
                    UpdateChecker.VERSION_URL,
                    headers={'User-Agent': f'Sigil/{Config.VERSION}'}
                )
                response = urllib.request.urlopen(request, timeout=10, context=ssl_context)
                remote_version = response.read().decode('utf-8').strip()
                
                # Save last check time
                try:
                    last_check_file = Config.CONFIG_DIR / ".last_update_check"
                    last_check_file.write_text(str(time.time()))
                except OSError:
                    pass
                
                # Compare versions
                if UpdateChecker._is_newer_version(remote_version, Config.VERSION):
                    if not silent:
                        UpdateChecker._show_update_prompt(remote_version)
                    return True
                else:
                    if not silent:
                        print(f"✓ You're running the latest version ({Config.VERSION})")
                    return False
                    
            except urllib.error.URLError as e:
                if not silent:
                    print(f"⚠ Could not check for updates: {e.reason}")
                return False
            except Exception as e:
                if not silent:
                    print(f"⚠ Update check failed: {e}")
                return False
                
        except Exception as e:
            if not silent:
                print(f"⚠ Unexpected error during update check: {e}")
            return False
    
    @staticmethod
    def _is_newer_version(remote: str, current: str) -> bool:
        """Compare version strings to see if remote is newer than current"""
        try:
            # Split version strings into parts
            remote_parts = list(map(int, remote.split('.')))
            current_parts = list(map(int, current.split('.')))
            
            # Pad with zeros if needed
            max_len = max(len(remote_parts), len(current_parts))
            remote_parts += [0] * (max_len - len(remote_parts))
            current_parts += [0] * (max_len - len(current_parts))
            
            # Compare each part
            for r, c in zip(remote_parts, current_parts):
                if r > c:
                    return True
                elif r < c:
                    return False
            
            return False  # Versions are equal
        except (ValueError, AttributeError):
            # If parsing fails, do string comparison
            return remote > current
    
    @staticmethod
    def _show_update_prompt(new_version: str) -> None:
        """Show update notification to user"""
        print("\n" + "="*60)
        print("📢 UPDATE AVAILABLE!")
        print("="*60)
        print(f"Hello there, it seems like you are using an outdated version of Sigil.")
        print(f"Current version: {Config.VERSION}")
        print(f"Latest version:  {new_version}")
        print("\nWhat's new in the latest version?")
        print("• Bug fixes and performance improvements")
        print("• New features and enhancements")
        print("• Better compatibility")
        print("\nWould you like to update?")
        
        # Check if we have tkinter for graphical prompt
        if HAS_TKINTER:
            try:
                response = messagebox.askyesno(
                    "Sigil Update Available",
                    f"Update available!\n\nCurrent: {Config.VERSION}\nLatest: {new_version}\n\n"
                    f"Click 'Yes' to open the download page, or 'No' to continue.",
                    icon='info'
                )
                if response:
                    webbrowser.open(UpdateChecker.RELEASES_URL)
                    print(f"✓ Opened: {UpdateChecker.RELEASES_URL}")
                else:
                    print("⚠ Update skipped. You can update manually later.")
            except Exception:
                # Fallback to console
                UpdateChecker._console_update_prompt(new_version)
        else:
            UpdateChecker._console_update_prompt(new_version)
        
        print("="*60 + "\n")
    
    @staticmethod
    def _console_update_prompt(new_version: str) -> None:
        """Console-based update prompt"""
        try:
            response = input("Open download page? (yes/no): ").strip().lower()
            if response in ('yes', 'y'):
                webbrowser.open(UpdateChecker.RELEASES_URL)
                print(f"✓ Opened: {UpdateChecker.RELEASES_URL}")
            else:
                print("⚠ Update skipped. You can update manually using:")
                print(f"  opnlnk {UpdateChecker.RELEASES_URL}")
        except (EOFError, KeyboardInterrupt):
            print("\n⚠ Update check cancelled")
    
    @staticmethod
    def update_command(args: List[str]) -> None:
        """Check for updates command"""
        if args and args[0] == "force":
            UpdateChecker.check_for_updates(silent=False, force_check=True)
        else:
            UpdateChecker.check_for_updates(silent=False, force_check=False)

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

class Config:
    """Central configuration"""
    VERSION = "1.0.1"
    UNDO_LIMIT = 200
    ALIAS_RECURSION_LIMIT = 20

    if os.name == "nt":
        CONFIG_DIR = Path(r"C:\Sigil")
    else:
        CONFIG_DIR = Path.home() / ".sigil"

    @classmethod
    def init_directories(cls):
        """Initialize all required directories"""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cls.PLUGIN_DIR = cls.CONFIG_DIR / "plugins"
        cls.PLUGIN_DIR.mkdir(exist_ok=True)
        cls.UNDO_DIR = Path(tempfile.gettempdir()) / "sigil_undo"
        cls.UNDO_DIR.mkdir(exist_ok=True)

Config.init_directories()

class State:
    """Application state management"""
    current_profile: str = "default"
    current_dir: Path = Path.cwd()

    script_file: str = ""
    script_dir: str = ""
    script_args: List[str] = []

    aliases: Dict[str, str] = {}
    variables: Dict[str, Any] = {}
    exported_vars: set = set()
    readonly_vars: set = set()
    
    functions: Dict[str, List[str]] = {}  # Store functions with their commands

    undo_stack: List[dict] = []
    redo_stack: List[dict] = []

    loading_rc: bool = False
    plugin_registry: dict = {}

# ============================================================================
# EXCEPTIONS
# ============================================================================

class BreakException(Exception):
    """Signal break from loop/case block"""
    pass

class SigilError(Exception):
    """Base exception for Sigil errors"""
    pass

class CommandError(SigilError):
    """Error executing command"""
    pass

# ============================================================================
# KEYBOARD INPUT UTILITY
# ============================================================================

def wait_for_any_key(prompt: str = "Press any key to continue . . .") -> None:
    """Wait for any key press (cross-platform)"""
    print(prompt, end="", flush=True)
    
    try:
        if HAS_MSVCRT:
            # Windows implementation
            msvcrt.getch()
        elif HAS_UNIX_TERM:
            # Unix/Linux implementation
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        else:
            # Fallback for other platforms
            input()
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C gracefully
        print()
        return
    finally:
        print()  # Newline after key press

# ============================================================================
# PERSISTENCE (RC FILES)
# ============================================================================

class RCManager:
    """Manage .sigilrc profile files"""

    @staticmethod
    def get_rc_path(profile: Optional[str] = None) -> Path:
        """Get path to profile's RC file"""
        name = profile or State.current_profile
        if name == "default":
            return Config.CONFIG_DIR / ".sigilrc"
        return Config.CONFIG_DIR / f".sigilrc.{name}"

    @staticmethod
    def save() -> None:
        """Save current state to RC file"""
        path = RCManager.get_rc_path()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Sigil RC — Profile: {State.current_profile}\n")
                f.write(f"# Version: {Config.VERSION}\n\n")

                # Save aliases
                if State.aliases:
                    f.write("# Aliases\n")
                    for name, cmd in sorted(State.aliases.items()):
                        f.write(f"alia {name} {cmd}\n")
                    f.write("\n")

                # Save variables
                if State.variables:
                    f.write("# Variables\n")
                    for name, value in sorted(State.variables.items()):
                        if isinstance(value, str):
                            needs_quote = any(ch.isspace() for ch in value) or value == ""
                            escaped = value.replace('"', '\\"')
                            readonly_flag = "-r " if name in State.readonly_vars else ""

                            if needs_quote:
                                f.write(f'let {readonly_flag}{name} = "{escaped}"\n')
                            else:
                                f.write(f"let {readonly_flag}{name} = {escaped}\n")
                        else:
                            readonly_flag = "-r " if name in State.readonly_vars else ""
                            f.write(f"let {readonly_flag}{name} = {value}\n")
                    f.write("\n")

                # Save functions
                if State.functions:
                    f.write("# Functions\n")
                    for name, commands in sorted(State.functions.items()):
                        # Join commands with " nxt " separator
                        commands_str = " nxt ".join(commands)
                        f.write(f"fnc {name} {commands_str}\n")
                    f.write("\n")

                # Save exports
                if State.exported_vars:
                    f.write("# Exports\n")
                    for name in sorted(State.exported_vars):
                        f.write(f"export {name}\n")

        except Exception as e:
            print(f"⚠ Failed to save .sigilrc: {e}")

    @staticmethod
    def load() -> None:
        """Load RC file for current profile"""
        path = RCManager.get_rc_path()

        if not path.exists():
            return

        State.loading_rc = True
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            Interpreter.run_lines(lines, from_rc=True)
        except Exception as e:
            print(f"⚠ Error loading .sigilrc: {e}")
        finally:
            State.loading_rc = False

# ============================================================================
# UNDO/BACKUP SYSTEM
# ============================================================================
class UndoManager:
    """Manage undo/redo operations"""

    @staticmethod
    def backup_path(path: Path) -> Optional[Path]:
        """Create backup of path (move to temp), return backup location"""
        if not path.exists():
            return None

        backup_id = str(uuid.uuid4())
        backup_dir = Config.UNDO_DIR / backup_id
        backup_dir.mkdir(exist_ok=True)

        dest = backup_dir / path.name
        shutil.move(str(path), str(dest))
        return dest

    @staticmethod
    def backup_contents(path: Path) -> Optional[Path]:
        """Create backup of file contents (copy), return backup location"""
        if not path.exists() or path.is_dir():
            return None

        backup_id = str(uuid.uuid4())
        backup_path = Config.UNDO_DIR / f"{backup_id}_{path.name}"
        shutil.copy2(str(path), str(backup_path))
        return backup_path

    @staticmethod
    def push(action: dict) -> None:
        """Push action onto undo stack"""
        State.undo_stack.append(action)
        if len(State.undo_stack) > Config.UNDO_LIMIT:
            State.undo_stack.pop(0)
        State.redo_stack.clear()

    @staticmethod
    def safe_move(src: Path, dst: Path) -> None:
        """Safely move file, creating parent directories"""
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

# ============================================================================
# TEXT PROCESSING
# ============================================================================

class TextProcessor:
    """Handle tokenization, comment stripping, variable expansion"""

    _varname_re = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')

    @staticmethod
    def tokenize(line: str) -> List[str]:
        """Split line into tokens, respecting quotes"""
        tokens = []
        current = ""
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
                current += char
            elif not in_quotes and char.isspace():
                if current:
                    tokens.append(current)
                    current = ""
            else:
                current += char

        if current:
            tokens.append(current)

        return tokens

    @staticmethod
    def strip_comments(line: str, in_block_comment: bool) -> Tuple[str, bool]:
        """Strip comments from line, handle block comments"""
        # Handle existing block comment
        if in_block_comment:
            end_idx = line.find("*/")
            if end_idx == -1:
                return "", True
            line = line[end_idx + 2:]
            in_block_comment = False

        # Handle new block comments
        while True:
            start_idx = line.find("/*")
            if start_idx == -1:
                break

            end_idx = line.find("*/", start_idx + 2)
            if end_idx == -1:
                line = line[:start_idx]
                in_block_comment = True
                break
            else:
                line = line[:start_idx] + line[end_idx + 2:]

        # Check for line comment markers
        stripped = line.lstrip()
        if stripped.startswith('&'):
            return "", in_block_comment

        # Process character by character for inline comments
        result = []
        in_quotes = False
        i = 0

        while i < len(line):
            char = line[i]

            if char == '"':
                in_quotes = not in_quotes
                result.append(char)
                i += 1
                continue

            if not in_quotes:
                # Check for comment markers
                if char in ('&', '#'):
                    break
                if char == '/' and i + 1 < len(line) and line[i + 1] == '/':
                    break

            result.append(char)
            i += 1

        return "".join(result).rstrip(), in_block_comment

    @staticmethod
    def expand_vars_in_string(text: str) -> str:
        """Expand $var and ${var} in string.

        Preserve regular backslashes (so Windows paths like C:\\Users\\... keep their backslashes).
        Treat backslash as an escape only for $, {, }, '"' and backslash itself.
        """
        result = []
        i = 0
        length = len(text)

        while i < length:
            char = text[i]

            # Handle backslash escapes for a small safe set
            if char == '\\':
                if i + 1 < length:
                    nxt = text[i + 1]
                    # Only consume the backslash when escaping one of these characters
                    if nxt in ('$', '{', '}', '"', '\\'):
                        result.append(nxt)
                        i += 2
                        continue
                    else:
                        # keep the backslash as a literal and keep the next char too
                        result.append('\\')
                        i += 1
                        continue
                else:
                    # trailing backslash - keep it
                    result.append('\\')
                    i += 1
                    continue

            # Handle variable expansion
            if char == '$':
                # ${var} form
                if i + 1 < length and text[i + 1] == '{':
                    end_idx = text.find('}', i + 2)
                    if end_idx != -1:
                        var_name = text[i + 2:end_idx]
                        value = State.variables.get(var_name, os.environ.get(var_name, ""))
                        result.append(str(value))
                        i = end_idx + 1
                        continue

                # $var form
                match = TextProcessor._varname_re.match(text[i + 1:])
                if match:
                    var_name = match.group(0)
                    value = State.variables.get(var_name, os.environ.get(var_name, ""))
                    result.append(str(value))
                    i += 1 + len(var_name)
                    continue

            result.append(char)
            i += 1

        return "".join(result)

    @staticmethod
    def expand_aliases_and_vars(line: str) -> str:
        """Expand aliases and variables in command line"""
        tokens = TextProcessor.tokenize(line)
        if not tokens:
            return line

        # Expand aliases recursively (with depth limit)
        first = tokens[0]
        if first in State.aliases:
            new_line = State.aliases[first]
            if len(tokens) > 1:
                new_line += " " + " ".join(tokens[1:])

            # Recursive expansion with depth limit
            for _ in range(Config.ALIAS_RECURSION_LIMIT):
                new_tokens = TextProcessor.tokenize(new_line)
                if new_tokens and new_tokens[0] in State.aliases:
                    rest = " " + " ".join(new_tokens[1:]) if len(new_tokens) > 1 else ""
                    new_line = State.aliases[new_tokens[0]] + rest
                else:
                    break

            return TextProcessor.expand_aliases_and_vars(new_line)

        # Expand variables in tokens
        expanded_tokens = []
        for token in tokens:
            # Single-quote shorthand: 'varname' -> value
            if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
                inner = token[1:-1]
                value = State.variables.get(inner, os.environ.get(inner, inner))
                expanded_tokens.append(str(value))
                continue

            # Double-quoted string: expand vars inside
            if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
                inner = token[1:-1]
                expanded = TextProcessor.expand_vars_in_string(inner)
                expanded_tokens.append('"' + expanded.replace('"', '\\"') + '"')
                continue

            # Token with $ in it
            if '$' in token:
                expanded_tokens.append(TextProcessor.expand_vars_in_string(token))
                continue

            # Direct variable reference
            if token in State.variables:
                expanded_tokens.append(str(State.variables[token]))
                continue

            expanded_tokens.append(token)

        return " ".join(expanded_tokens)

# ============================================================================
# EXECUTION LOGGING
# ============================================================================

class ExecutionLogger:
    """Log all executed commands and scripts"""
    
    LOG_FILE = Config.CONFIG_DIR / "uses.log"
    
    @staticmethod
    def init_log_file() -> None:
        """Initialize the log file with headers if it doesn't exist"""
        if not ExecutionLogger.LOG_FILE.exists():
            ExecutionLogger.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ExecutionLogger.LOG_FILE, "w", encoding="utf-8") as f:
                f.write("# Sigil Execution Log\n")
                f.write("# Format: TIMESTAMP | MODE | COMMAND/FILE | EXIT_CODE | WORKING_DIR | USER\n")
                f.write("# " + "=" * 80 + "\n")
    
    @staticmethod
    def log_execution(mode: str, command: str, exit_code: int = 0) -> None:
        """
        Log an execution to the uses.log file
        
        Args:
            mode: "CMD" for command, "SCRIPT" for script file, "REPL" for interactive command
            command: The command or script path that was executed
            exit_code: Exit/return code of the execution
        """
        try:
            ExecutionLogger.init_log_file()
            
            # Get current user
            try:
                user = getpass.getuser()
            except Exception:
                user = "unknown"
            
            # Sanitize command for logging (remove passwords, etc.)
            sanitized_cmd = ExecutionLogger._sanitize_command(command)
            
            # Format timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Format log entry
            log_entry = f"{timestamp} | {mode:6} | {sanitized_cmd:60} | {exit_code:3} | {State.current_dir} | {user}\n"
            
            # Write to log file
            with open(ExecutionLogger.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)
                
        except Exception as e:
            # Don't crash if logging fails
            pass
    
    @staticmethod
    def _sanitize_command(command: str) -> str:
        """Sanitize command for logging (remove sensitive data)"""
        # Remove passwords from commands
        sanitized = command
        
        # Check for common password patterns
        password_patterns = [
            r'-p\s+["\']?[^"\'\s]+["\']?',
            r'--password\s+["\']?[^"\'\s]+["\']?',
            r'passwd\s*=\s*["\']?[^"\'\s]+["\']?',
            r'password\s*=\s*["\']?[^"\'\s]+["\']?',
            r'--key\s+["\']?[^"\'\s]+["\']?',
            r'--token\s+["\']?[^"\'\s]+["\']?',
            r'--secret\s+["\']?[^"\'\s]+["\']?',
        ]
        
        for pattern in password_patterns:
            sanitized = re.sub(pattern, lambda m: m.group(0).split('=')[0] + '=*****' if '=' in m.group(0) else m.group(0).split()[0] + ' *****', sanitized)
        
        # Truncate very long commands
        if len(sanitized) > 100:
            sanitized = sanitized[:97] + "..."
        
        return sanitized

# Initialize the logger at module load
ExecutionLogger.init_log_file()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def resolve_path(path_str: str) -> Path:
    """Resolve path with variable expansion and relative to CWD"""
    expanded = TextProcessor.expand_vars_in_string(path_str)
    path = Path(expanded).expanduser()

    if not path.is_absolute():
        path = State.current_dir / path

    return path.resolve()

def set_last_exit(code: int) -> None:
    """Set last exit code variables"""
    try:
        int_code = int(code)
    except (ValueError, TypeError):
        int_code = 1

    State.variables['last'] = int_code
    State.variables['LAST'] = int_code
    State.variables['LAST_EXIT'] = int_code

def parse_number(text: str) -> float | int:
    """Parse numeric value from string"""
    if text in State.variables:
        text = str(State.variables[text])

    # Remove quotes if present
    if isinstance(text, str) and len(text) >= 2:
        if text[0] == '"' and text[-1] == '"':
            text = text[1:-1]

    # Try parsing
    try:
        if "." in str(text) or "e" in str(text).lower():
            return float(text)
        return int(text)
    except (ValueError, TypeError):
        return 0

def parse_numbers(args: List[str]) -> List[float | int]:
    """Parse list of numbers"""
    return [parse_number(arg) for arg in args]

def confirm_destructive_action(action: str) -> bool:
    """Ask user to confirm destructive action"""
    try:
        response = input(f"⚠ Confirm {action}? (yes/no): ").strip().lower()
        return response in ('yes', 'y')
    except (EOFError, KeyboardInterrupt):
        print()
        return False

# ============================================================================
# PATH MANAGEMENT COMMANDS (renamed to pth)
# ============================================================================

class PthCommands:
    """Manage system PATH environment variable (now called 'pth')"""

    @staticmethod
    def _get_path_separator() -> str:
        """Get PATH separator for current platform"""
        return ';' if os.name == 'nt' else ':'

    @staticmethod
    def _get_path_list() -> List[str]:
        """Get current PATH as list of directories"""
        path_str = os.environ.get('PATH', '')
        separator = PthCommands._get_path_separator()
        return [p.strip() for p in path_str.split(separator) if p.strip()]

    @staticmethod
    def _set_path_list(path_list: List[str]) -> None:
        """Set PATH from list of directories"""
        separator = PthCommands._get_path_separator()
        new_path = separator.join(path_list)
        os.environ['PATH'] = new_path
        # Also update in State variables
        State.variables['PATH'] = new_path
        State.exported_vars.add('PATH')

    @staticmethod
    def _resolve_dir(dir_path: str) -> Path:
        """Resolve directory path, expanding variables and making absolute"""
        expanded = TextProcessor.expand_vars_in_string(dir_path)
        path = Path(expanded).expanduser()
        
        if not path.is_absolute():
            path = State.current_dir / path
            
        return path.resolve()

    @staticmethod
    def add(args: List[str]) -> None:
        """Add directory to PATH if not already present"""
        if not args:
            print("Usage: pth add <directory>")
            print("Example: pth add /usr/local/bin")
            print("         pth add \"C:\\Program Files\\MyApp\\bin\"")
            set_last_exit(1)
            return

        dir_path = args[0]
        resolved_path = PthCommands._resolve_dir(dir_path)
        
        # Check if directory exists
        if not resolved_path.exists():
            try:
                resolved_path.mkdir(parents=True, exist_ok=True)
                print(f"✓ Created directory: {resolved_path}")
            except Exception as e:
                print(f"⚠ Failed to create directory: {e}")
                set_last_exit(1)
                return
        
        if not resolved_path.is_dir():
            print(f"⚠ Not a directory: {resolved_path}")
            set_last_exit(1)
            return
        
        # Get current PATH
        current_paths = PthCommands._get_path_list()
        dir_str = str(resolved_path)
        
        # Check if already in PATH
        if any(p == dir_str for p in current_paths):
            print(f"✓ Directory already in PATH: {resolved_path}")
            set_last_exit(0)
            return
        
        # Add to PATH (at the end)
        current_paths.append(dir_str)
        
        # Update PATH in os.environ
        separator = PthCommands._get_path_separator()
        new_path = separator.join(current_paths)
        
        # Update system environment variable
        os.environ['PATH'] = new_path
        
        # Also update in State variables
        State.variables['PATH'] = new_path
        State.exported_vars.add('PATH')
        
        # On Windows, we might want to update the system PATH permanently
        # This is more complex and may require registry edits
        if os.name == 'nt':
            try:
                # Try to update the user PATH in registry
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS) as key:
                    try:
                        # Get existing user PATH
                        user_path, _ = winreg.QueryValueEx(key, 'PATH')
                    except FileNotFoundError:
                        user_path = ''
                    
                    # Add our directory if not already present
                    user_paths = user_path.split(separator) if user_path else []
                    if dir_str not in user_paths:
                        user_paths.append(dir_str)
                        new_user_path = separator.join(user_paths)
                        winreg.SetValueEx(key, 'PATH', 0, winreg.REG_EXPAND_SZ, new_user_path)
                        print(f"✓ Updated permanent user PATH in registry")
                    else:
                        print(f"✓ Directory already in permanent user PATH")
            except Exception as e:
                print(f"⚠ Note: Could not update permanent PATH in registry: {e}")
                print(f"  The PATH change is only for this Sigil session.")
        
        print(f"✓ Added to PATH: {resolved_path}")
        print(f"  PATH is now: {new_path}")
        
        # Also save to profile if not loading RC
        if not State.loading_rc:
            # Add a line to RC file for persistence
            rc_path = RCManager.get_rc_path()
            try:
                with open(rc_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n# PATH addition\n")
                    f.write(f'pth add "{dir_str}"\n')
            except Exception as e:
                print(f"⚠ Note: Could not save to .sigilrc: {e}")
        
        set_last_exit(0)

    @staticmethod
    def rmv(args: List[str]) -> None:
        """Remove directory from PATH"""
        if not args:
            print("Usage: pth rmv <directory>")
            print("Example: pth rmv /usr/local/bin")
            print("         pth rmv \"C:\\Program Files\\MyApp\\bin\"")
            set_last_exit(1)
            return

        dir_path = args[0]
        resolved_path = PthCommands._resolve_dir(dir_path)
        
        # Get current PATH
        current_paths = PthCommands._get_path_list()
        dir_str = str(resolved_path)
        
        # Find and remove the directory
        new_paths = [p for p in current_paths if p != dir_str]
        
        if len(new_paths) == len(current_paths):
            # Nothing was removed
            print(f"⚠ Directory not found in PATH: {resolved_path}")
            print(f"  Use 'pth lst' to see current PATH entries")
            set_last_exit(1)
            return
        
        # Update PATH
        PthCommands._set_path_list(new_paths)
        
        print(f"✓ Removed from PATH: {resolved_path}")
        set_last_exit(0)

    @staticmethod
    def lst(args: List[str]) -> None:
        """List all directories in PATH"""
        current_paths = PthCommands._get_path_list()
        
        if not current_paths:
            print("PATH is empty")
            set_last_exit(0)
            return
        
        print(f"\n📁 PATH Environment Variable ({len(current_paths)} entries):")
        print("=" * 80)
        
        for i, path in enumerate(current_paths, 1):
            path_obj = Path(path)
            exists = path_obj.exists() and path_obj.is_dir()
            status = "✓" if exists else "✗"
            print(f"{i:3}. {status} {path}")
            
            # Show subdirectories if -v flag is used
            if args and '-v' in args and exists:
                try:
                    items = list(path_obj.iterdir())
                    if items:
                        for item in items[:5]:  # Show first 5 items
                            if item.is_dir():
                                print(f"      📂 {item.name}/")
                            else:
                                print(f"      📄 {item.name}")
                        if len(items) > 5:
                            print(f"      ... and {len(items) - 5} more")
                except PermissionError:
                    print(f"      ⚠ Permission denied")
                except Exception:
                    pass
        
        print("=" * 80)
        print(f"Total: {len(current_paths)} directories")
        set_last_exit(0)

    @staticmethod
    def has(args: List[str]) -> None:
        """Check if a directory is in PATH"""
        if not args:
            print("Usage: pth has <directory>")
            print("Example: pth has /usr/local/bin")
            set_last_exit(1)
            return

        dir_path = args[0]
        resolved_path = PthCommands._resolve_dir(dir_path)
        
        # Get current PATH
        current_paths = PthCommands._get_path_list()
        dir_str = str(resolved_path)
        
        # Check if in PATH
        if any(p == dir_str for p in current_paths):
            print(f"yes (found in PATH)")
            set_last_exit(0)
        else:
            print(f"no (not in PATH)")
            set_last_exit(1)

    @staticmethod
    def pth(args: List[str]) -> None:
        """Main pth command dispatcher (shorter name)"""
        if not args:
            print("Usage: pth <command> [options]")
            print("Commands:")
            print("  add <directory>    - Add directory to PATH if not already present")
            print("  rmv <directory>    - Remove directory from PATH")
            print("  lst [-v]           - List all directories in PATH")
            print("  has <directory>    - Check if directory is in PATH")
            print("\nExamples:")
            print("  pth add /usr/local/bin")
            print('  pth add "C:\\Tools\\MyApp\\bin"')
            print("  pth rmv /old/dir")
            print("  pth lst")
            print("  pth lst -v       # List with directory contents")
            print("  pth has ~/bin")
            set_last_exit(1)
            return
        
        subcommand = args[0].lower()
        sub_args = args[1:]
        
        if subcommand == "add":
            PthCommands.add(sub_args)
        elif subcommand == "rmv":
            PthCommands.rmv(sub_args)
        elif subcommand == "lst":
            PthCommands.lst(sub_args)
        elif subcommand == "has":
            PthCommands.has(sub_args)
        else:
            print(f"⚠ Unknown pth subcommand: {subcommand}")
            set_last_exit(1)

# ============================================================================
# NETWORK COMMANDS
# ============================================================================

class NetCommands:
    """Network-related commands for downloading and pinging"""

    @staticmethod
    def dwn(args: List[str]) -> None:
        """Download a file from URL to local path
        
        Usage: net dwn <url> [save_path]
        Example: net dwn https://example.com/file.zip
                 net dwn https://example.com/file.zip ./downloads/file.zip
        """
        if not args:
            print("Usage: net dwn <url> [save_path]")
            print("Example: net dwn https://example.com/file.zip")
            print("         net dwn https://example.com/file.zip ./downloads/file.zip")
            set_last_exit(1)
            return

        url = args[0]
        
        # Determine save path
        if len(args) >= 2:
            save_path = resolve_path(args[1])
        else:
            # Extract filename from URL
            filename = url.split('/')[-1]
            if '?' in filename:  # Remove query parameters
                filename = filename.split('?')[0]
            if not filename:
                filename = f"download_{int(time.time())}.bin"
            save_path = State.current_dir / filename
        
        try:
            # Create SSL context (allow self-signed certs for local networks)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Ensure save directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"⬇️  Downloading: {url}")
            print(f"   Destination: {save_path}")
            
            # Create a user agent header
            headers = {'User-Agent': f'Sigil/{Config.VERSION}'}
            request = urllib.request.Request(url, headers=headers)
            
            # Show progress
            start_time = time.time()
            
            def show_progress(block_num, block_size, total_size):
                downloaded = block_num * block_size
                if total_size > 0:
                    percent = min(100, (downloaded * 100) / total_size)
                    # Show progress every 5% or for every 1MB
                    if block_num % max(1, int(total_size / block_size / 20)) == 0 or downloaded % (1024 * 1024) == 0:
                        mb_downloaded = downloaded / (1024 * 1024)
                        if total_size > 0:
                            mb_total = total_size / (1024 * 1024)
                            print(f"   Progress: {percent:.1f}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)", end='\r')
                        else:
                            print(f"   Progress: {mb_downloaded:.1f} MB downloaded", end='\r')
            
            # Download with progress
            urllib.request.urlretrieve(
                url, 
                str(save_path),
                reporthook=show_progress,
                context=ssl_context
            )
            
            # Clear progress line and show completion
            print(" " * 80, end='\r')
            
            # Verify download
            if save_path.exists():
                file_size = save_path.stat().st_size
                elapsed = time.time() - start_time
                speed = file_size / elapsed / (1024 * 1024) if elapsed > 0 else 0
                
                print(f"✓ Download complete!")
                print(f"  File: {save_path}")
                print(f"  Size: {file_size:,} bytes ({file_size/(1024*1024):.2f} MB)")
                print(f"  Time: {elapsed:.2f} seconds")
                print(f"  Speed: {speed:.2f} MB/s")
                set_last_exit(0)
            else:
                print(f"⚠ Download failed - file not created")
                set_last_exit(1)
                
        except urllib.error.HTTPError as e:
            print(f"⚠ HTTP Error {e.code}: {e.reason}")
            set_last_exit(1)
        except urllib.error.URLError as e:
            print(f"⚠ URL Error: {e.reason}")
            set_last_exit(1)
        except ssl.SSLError as e:
            print(f"⚠ SSL Error: {e}")
            set_last_exit(1)
        except Exception as e:
            print(f"⚠ Download failed: {e}")
            set_last_exit(1)

    @staticmethod
    def png(args: List[str]) -> None:
        """Ping a host to check network connectivity
        
        Usage: net png <host> [count]
        Example: net png google.com
                 net png 8.8.8.8 5
                 net png localhost 3
        """
        if not args:
            print("Usage: net png <host> [count]")
            print("Example: net png google.com")
            print("         net png 8.8.8.8 5")
            print("         net png localhost 3")
            set_last_exit(1)
            return

        host = args[0]
        count = 4  # Default ping count
        
        if len(args) >= 2:
            try:
                count = int(args[1])
                if count < 1:
                    count = 1
                elif count > 100:
                    count = 100
                    print("⚠ Limiting to 100 pings maximum")
            except (ValueError, TypeError):
                print(f"⚠ Invalid count, using default (4)")
        
        print(f"🔄 Pinging {host} {count} times...")
        
        try:
            if os.name == "nt":
                # Windows ping command
                cmd = ["ping", "-n", str(count), host]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
                
                # Parse Windows ping output
                output = result.stdout
                lines = output.split('\n')
                
                # Find summary lines
                for line in lines:
                    if "Packets:" in line or "Sent =" in line:
                        print(line.strip())
                    elif "Approximate round trip times" in line or "Minimum =" in line:
                        print(line.strip())
                    elif "Request timed out" in line:
                        print("⚠ Request timed out")
                
                if result.returncode == 0:
                    print(f"✓ {host} is reachable")
                else:
                    print(f"✗ {host} is not reachable (or ping blocked)")
                    
            else:
                # Unix/Linux ping command
                cmd = ["ping", "-c", str(count), host]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
                
                # Parse Unix ping output
                output = result.stdout
                lines = output.split('\n')
                
                # Show relevant ping statistics
                for line in lines:
                    if "packets transmitted" in line or "rtt min/avg/max" in line:
                        print(line.strip())
                    elif "PING" in line and line.startswith("PING"):
                        # Show the ping command echo
                        pass
                
                if result.returncode == 0:
                    print(f"✓ {host} is reachable")
                else:
                    print(f"✗ {host} is not reachable (or ping blocked)")
            
            set_last_exit(result.returncode)
            
        except FileNotFoundError:
            print("⚠ Ping command not found. Make sure you have network utilities installed.")
            set_last_exit(127)
        except Exception as e:
            print(f"⚠ Ping failed: {e}")
            set_last_exit(1)

    @staticmethod
    def net(args: List[str]) -> None:
        """Network utilities - download and ping
        
        Usage: net <command> [arguments]
        Commands:
          dwn <url> [save_path]    - Download file from URL
          png <host> [count]       - Ping host (1-100 times)
        """
        if not args:
            print("Usage: net <command> [arguments]")
            print("Commands:")
            print("  dwn <url> [save_path]    - Download file from URL")
            print("  png <host> [count]       - Ping host (1-100 times)")
            print("\nExamples:")
            print("  net dwn https://example.com/file.zip")
            print("  net dwn https://example.com/file.zip ./downloads/file.zip")
            print("  net png google.com")
            print("  net png 8.8.8.8 5")
            print("  net png localhost 3")
            set_last_exit(1)
            return
        
        subcommand = args[0].lower()
        sub_args = args[1:]
        
        if subcommand == "dwn":
            NetCommands.dwn(sub_args)
        elif subcommand == "png":
            NetCommands.png(sub_args)
        else:
            print(f"⚠ Unknown net subcommand: {subcommand}")
            print("  Use: dwn (download) or png (ping)")
            set_last_exit(1)

# ============================================================================
# ARCHIVE COMMANDS (ZIP/UNZIP)
# ============================================================================

class ArchiveCommands:
    """Archive operations - zip and unzip files"""

    @staticmethod
    def zip(args: List[str]) -> None:
        """Create a zip archive
        
        Usage: zip <archive.zip> <file1> <file2> ... [options]
               zip <archive.zip> -d <directory> [options]
        
        Options:
          -d, --dir   Zip an entire directory
          -r, --recurse  Recurse into subdirectories (default: True)
          -x, --exclude <pattern>  Exclude files matching pattern
          
        Examples:
          zip archive.zip file1.txt file2.jpg
          zip backup.zip -d ./myfolder
          zip project.zip -d ./project -x "*.tmp"
        """
        if not args:
            print("Usage: zip <archive.zip> <file1> <file2> ... [options]")
            print("       zip <archive.zip> -d <directory> [options]")
            print("\nOptions:")
            print("  -d, --dir <directory>   Zip an entire directory")
            print("  -r, --recurse           Recurse into subdirectories (default: True)")
            print("  -x, --exclude <pattern> Exclude files matching pattern")
            print("\nExamples:")
            print("  zip archive.zip file1.txt file2.jpg")
            print("  zip backup.zip -d ./myfolder")
            print("  zip project.zip -d ./project -x \"*.tmp\"")
            set_last_exit(1)
            return

        # Parse arguments
        archive_path = resolve_path(args[0])
        files_to_zip = []
        dir_to_zip = None
        recurse = True
        exclude_patterns = []
        
        i = 1
        while i < len(args):
            arg = args[i]
            if arg in ("-d", "--dir"):
                if i + 1 >= len(args):
                    print("⚠ Missing directory path after -d")
                    set_last_exit(1)
                    return
                dir_to_zip = resolve_path(args[i + 1])
                i += 2
            elif arg in ("-r", "--recurse"):
                recurse = True
                i += 1
            elif arg in ("-nr", "--no-recurse"):
                recurse = False
                i += 1
            elif arg in ("-x", "--exclude"):
                if i + 1 >= len(args):
                    print("⚠ Missing pattern after -x")
                    set_last_exit(1)
                    return
                exclude_patterns.append(args[i + 1])
                i += 2
            else:
                # Treat as a file to zip
                files_to_zip.append(resolve_path(arg))
                i += 1
        
        try:
            # Ensure archive has .zip extension
            if not str(archive_path).lower().endswith('.zip'):
                archive_path = Path(str(archive_path) + '.zip')
            
            # Check if archive already exists
            if archive_path.exists():
                if not confirm_destructive_action(f"overwrite existing archive {archive_path.name}"):
                    print("✗ Operation cancelled")
                    set_last_exit(1)
                    return
            
            print(f"📦 Creating archive: {archive_path.name}")
            
            if dir_to_zip:
                # Zip a directory
                if not dir_to_zip.exists():
                    print(f"⚠ Directory not found: {dir_to_zip}")
                    set_last_exit(1)
                    return
                
                if not dir_to_zip.is_dir():
                    print(f"⚠ Not a directory: {dir_to_zip}")
                    set_last_exit(1)
                    return
                
                # Count files for progress
                file_count = 0
                if recurse:
                    for root, dirs, files in os.walk(dir_to_zip):
                        # Apply exclude patterns
                        for pattern in exclude_patterns:
                            files = [f for f in files if not fnmatch.fnmatch(f, pattern)]
                        file_count += len(files)
                else:
                    file_count = len([f for f in dir_to_zip.iterdir() if f.is_file()])
                
                print(f"  Source: {dir_to_zip}")
                print(f"  Files to archive: {file_count}")
                
                # Create the zip file
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    if recurse:
                        for root, dirs, files in os.walk(dir_to_zip):
                            # Apply exclude patterns
                            for pattern in exclude_patterns:
                                files = [f for f in files if not fnmatch.fnmatch(f, pattern)]
                            
                            for file in files:
                                file_path = Path(root) / file
                                # Create relative path for archive
                                rel_path = file_path.relative_to(dir_to_zip)
                                zipf.write(file_path, rel_path)
                                
                                # Show progress every 10 files
                                if file_count > 10 and len(zipf.namelist()) % 10 == 0:
                                    progress = len(zipf.namelist()) / file_count * 100
                                    print(f"  Progress: {progress:.1f}% ({len(zipf.namelist())}/{file_count})", end='\r')
                    else:
                        # Only top-level files
                        for item in dir_to_zip.iterdir():
                            if item.is_file():
                                # Apply exclude patterns
                                skip = False
                                for pattern in exclude_patterns:
                                    if fnmatch.fnmatch(item.name, pattern):
                                        skip = True
                                        break
                                if skip:
                                    continue
                                    
                                zipf.write(item, item.name)
                
            elif files_to_zip:
                # Zip specific files
                print(f"  Files to archive: {len(files_to_zip)}")
                
                # Check if files exist
                for file_path in files_to_zip:
                    if not file_path.exists():
                        print(f"⚠ File not found: {file_path}")
                        set_last_exit(1)
                        return
                
                # Create the zip file
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for i, file_path in enumerate(files_to_zip):
                        zipf.write(file_path, file_path.name)
                        
                        # Show progress
                        progress = (i + 1) / len(files_to_zip) * 100
                        print(f"  Progress: {progress:.1f}% ({i + 1}/{len(files_to_zip)})", end='\r')
            else:
                print("⚠ No files or directory specified to zip")
                set_last_exit(1)
                return
            
            # Clear progress line
            print(" " * 80, end='\r')
            
            # Show archive info
            archive_size = archive_path.stat().st_size
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                file_count = len(zipf.namelist())
            
            print(f"✓ Archive created: {archive_path.name}")
            print(f"  Size: {archive_size:,} bytes ({archive_size/(1024*1024):.2f} MB)")
            print(f"  Files: {file_count}")
            set_last_exit(0)
            
        except Exception as e:
            print(f"⚠ Failed to create archive: {e}")
            # Clean up partial archive if it exists
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except:
                    pass
            set_last_exit(1)

    @staticmethod
    def uzip(args: List[str]) -> None:
        """Extract a zip archive
        
        Usage: uzip <archive.zip> [destination] [options]
        
        Options:
          -d, --dir <path>     Extract to specific directory
          -l, --list           List contents without extracting
          -o, --overwrite      Overwrite existing files without asking
          -q, --quiet          Quiet mode (minimal output)
          
        Examples:
          uzip archive.zip
          uzip archive.zip ./extracted
          uzip archive.zip -l
          uzip archive.zip -d ./output
        """
        if not args:
            print("Usage: uzip <archive.zip> [destination] [options]")
            print("\nOptions:")
            print("  -d, --dir <path>     Extract to specific directory")
            print("  -l, --list           List contents without extracting")
            print("  -o, --overwrite      Overwrite existing files without asking")
            print("  -q, --quiet          Quiet mode (minimal output)")
            print("\nExamples:")
            print("  uzip archive.zip")
            print("  uzip archive.zip ./extracted")
            print("  uzip archive.zip -l")
            print("  uzip archive.zip -d ./output")
            set_last_exit(1)
            return

        # Parse arguments
        archive_path = None
        extract_dir = None
        list_only = False
        overwrite = False
        quiet = False
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg in ("-d", "--dir"):
                if i + 1 >= len(args):
                    print("⚠ Missing directory path after -d")
                    set_last_exit(1)
                    return
                extract_dir = resolve_path(args[i + 1])
                i += 2
            elif arg in ("-l", "--list"):
                list_only = True
                i += 1
            elif arg in ("-o", "--overwrite"):
                overwrite = True
                i += 1
            elif arg in ("-q", "--quiet"):
                quiet = True
                i += 1
            else:
                # This should be the archive path (only one archive allowed)
                if archive_path is None:
                    archive_path = resolve_path(arg)
                    i += 1
                else:
                    # If we already have an archive, treat as extract directory (positional)
                    if extract_dir is None:
                        extract_dir = resolve_path(arg)
                        i += 1
                    else:
                        print(f"⚠ Unexpected argument: {arg}")
                        set_last_exit(1)
                        return
        
        if archive_path is None:
            print("⚠ No archive file specified")
            set_last_exit(1)
            return
        
        # Check if archive exists
        if not archive_path.exists():
            print(f"⚠ Archive not found: {archive_path}")
            set_last_exit(1)
            return
        
        try:
            # Open the zip file
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # List contents
                if list_only:
                    print(f"📦 Contents of {archive_path.name}:")
                    print("=" * 80)
                    
                    # Get file info
                    file_list = zipf.infolist()
                    total_size = sum(f.file_size for f in file_list)
                    compressed_size = sum(f.compress_size for f in file_list)
                    
                    # List files
                    for file_info in file_list:
                        # Format the date
                        date_str = f"{file_info.date_time[0]}-{file_info.date_time[1]:02d}-{file_info.date_time[2]:02d}"
                        
                        # Show directory vs file
                        if file_info.filename.endswith('/'):
                            icon = "📁"
                            size_str = "     DIR"
                        else:
                            icon = "📄"
                            size_str = f"{file_info.file_size:8,}"
                        
                        print(f"{icon} {date_str} {size_str} {file_info.filename}")
                    
                    print("=" * 80)
                    print(f"Total files: {len(file_list)}")
                    print(f"Uncompressed size: {total_size:,} bytes ({total_size/(1024*1024):.2f} MB)")
                    print(f"Compressed size: {compressed_size:,} bytes ({compressed_size/(1024*1024):.2f} MB)")
                    
                    if total_size > 0:
                        ratio = (1 - compressed_size / total_size) * 100
                        print(f"Compression ratio: {ratio:.1f}%")
                    
                    set_last_exit(0)
                    return
                
                # Determine extraction directory
                if extract_dir is None:
                    # Default: extract to current directory with archive name (without .zip)
                    archive_name = archive_path.stem
                    extract_dir = State.current_dir / archive_name
                else:
                    extract_dir = extract_dir.resolve()
                
                # Create extraction directory if it doesn't exist
                extract_dir.mkdir(parents=True, exist_ok=True)
                
                # Count files for progress
                file_list = zipf.namelist()
                file_count = len(file_list)
                
                if not quiet:
                    print(f"📦 Extracting: {archive_path.name}")
                    print(f"  Destination: {extract_dir}")
                    print(f"  Files to extract: {file_count}")
                
                # Extract files
                extracted_count = 0
                skipped_count = 0
                error_count = 0
                
                for i, filename in enumerate(file_list):
                    # Determine destination path
                    dest_path = extract_dir / filename
                    
                    # Skip if it's a directory entry
                    if filename.endswith('/'):
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue
                    
                    # Check if file already exists
                    if dest_path.exists() and not overwrite:
                        if not quiet:
                            print(f"  ⚠ Skipping (exists): {filename}")
                        skipped_count += 1
                        continue
                    
                    try:
                        # Create parent directory if needed
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Extract the file
                        zipf.extract(filename, extract_dir)
                        extracted_count += 1
                        
                        if not quiet and file_count > 10:
                            progress = (i + 1) / file_count * 100
                            print(f"  Progress: {progress:.1f}% ({i + 1}/{file_count})", end='\r')
                            
                    except Exception as e:
                        if not quiet:
                            print(f"  ⚠ Failed to extract {filename}: {e}")
                        error_count += 1
                
                # Clear progress line
                if not quiet and file_count > 10:
                    print(" " * 80, end='\r')
                
                # Show summary
                if not quiet:
                    print(f"✓ Extraction complete!")
                    print(f"  Extracted: {extracted_count} files")
                    if skipped_count > 0:
                        print(f"  Skipped: {skipped_count} files (already exist)")
                    if error_count > 0:
                        print(f"  Errors: {error_count} files")
                    print(f"  Location: {extract_dir}")
                else:
                    # Quiet mode: just show basic info
                    print(f"Extracted {extracted_count} files to {extract_dir}")
                
                set_last_exit(0 if error_count == 0 else 1)
                
        except zipfile.BadZipFile:
            print(f"⚠ Invalid or corrupted zip file: {archive_path}")
            set_last_exit(1)
        except Exception as e:
            print(f"⚠ Failed to extract archive: {e}")
            set_last_exit(1)

    @staticmethod
    def unzip(args: List[str]) -> None:
        """Alias for uzip command"""
        ArchiveCommands.uzip(args)

# ============================================================================
# SCRIPT CONTROL COMMAND
# ============================================================================

class ScriptCommands:
    """Script control commands - start new scripts"""

    @staticmethod
    def sns(args: List[str]) -> None:
        """Start New Script - end current script and execute new one
        
        Usage: sns <script.sig> [arguments...]
        
        This command immediately terminates the current script and starts
        executing the specified script. The new script runs in the same
        environment (variables, aliases, etc.) but with new script arguments.
        
        Example:
          sns backup.sig            # Run backup.sig now
          sns install.sig --force   # Run install.sig with --force argument
        """
        if not args:
            print("Usage: sns <script.sig> [arguments...]")
            print("\nExample:")
            print("  sns backup.sig")
            print("  sns install.sig --force")
            set_last_exit(1)
            return

        script_file = args[0]
        
        # Remove quotes if present
        if script_file.startswith('"') and script_file.endswith('"'):
            script_file = script_file[1:-1]
        elif script_file.startswith("'") and script_file.endswith("'"):
            script_file = script_file[1:-1]
        
        # Expand variables in the script path
        script_file = TextProcessor.expand_vars_in_string(script_file)
        
        # Resolve the script path
        script_path = resolve_path(script_file)
        
        # Check if script exists
        if not script_path.exists():
            print(f"⚠ Script not found: {script_path}")
            set_last_exit(1)
            return
        
        # Check if it's a .sig file
        if not str(script_path).lower().endswith('.sig'):
            print(f"⚠ Not a Sigil script (.sig file): {script_path}")
            set_last_exit(1)
            return
        
        print(f"🔄 Starting new script: {script_path.name}")
        print("=" * 60)
        
        # Save current state
        original_dir = State.current_dir
        original_script_file = State.script_file
        original_script_dir = State.script_dir
        original_script_args = State.script_args[:]  # Copy list
        
        try:
            # Set new script context
            State.script_file = str(script_path)
            State.script_dir = str(script_path.parent)
            State.script_args = args[1:] if len(args) > 1 else []
            
            # Change to script's directory
            State.current_dir = script_path.parent
            
            # Read and execute the new script
            content = script_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            # Log the script switch
            ExecutionLogger.log_execution("SNS", f"Switched to: {script_path}", 0)
            
            # Clear undo stack for new script context
            State.undo_stack.clear()
            State.redo_stack.clear()
            
            # Execute the new script
            Interpreter.run_lines(lines, script_name=str(script_path))
            
            print("=" * 60)
            exit_code = State.variables.get('last', 0)
            print(f"✓ New script completed. Exit code: {exit_code}")
            
            # Log completion
            ExecutionLogger.log_execution("SNS", f"Completed: {script_path}", exit_code)
            
            # Terminate the current script by raising SystemExit
            # This will bubble up through the call stack
            sys.exit(exit_code)
            
        except SystemExit as e:
            # Re-raise the SystemExit to propagate it
            raise
        except Exception as e:
            print(f"⚠ Failed to execute new script: {e}")
            # Restore original context
            State.current_dir = original_dir
            State.script_file = original_script_file
            State.script_dir = original_script_dir
            State.script_args = original_script_args
            
            # Log failure
            ExecutionLogger.log_execution("SNS", f"Failed: {script_path}", 1)
            
            import traceback
            traceback.print_exc()
            set_last_exit(1)

# ============================================================================
# GLOBAL CLEANER COMMAND (MODIFIED - NO FLAGS)
# ============================================================================

class GlobalCleaner:
    """Global cleaner - reset Sigil environment to clean state"""
    
    # List of protected variables that should NOT be cleared
    PROTECTED_VARS = {
        'last', 'LAST', 'LAST_EXIT',  # Exit code tracking
        'PATH',  # System PATH
        'HOME', 'USER', 'USERNAME',   # User info
        'PWD', 'OLDPWD',              # Directory tracking
        'OS', 'OSTYPE',               # OS info
        'HOSTNAME', 'HOST',           # Host info
        'SHELL', 'TERM',              # Shell/Terminal info
        'TEMP', 'TMP', 'TMPDIR',      # Temp directories
        'LANG', 'LC_ALL',             # Locale settings
        'PROCESSOR_ARCHITECTURE',     # CPU architecture
        'NUMBER_OF_PROCESSORS',       # CPU count
        'COMPUTERNAME',               # Computer name
    }
    
    @staticmethod
    def gbc(args: List[str]) -> None:
        """Global Cleaner - reset Sigil environment to clean state (with confirmation)
        
        Usage: gbc
        
        This command will:
          1. Remove all user-defined variables (except protected ones)
          2. Clear all aliases
          3. Clear all functions
          4. Clear undo/redo stacks
          
        It will ask for confirmation before proceeding.
        
        Example:
          gbc  # Asks for confirmation before cleaning
        """
        # Show summary
        print("🔧 Global Cleaner")
        print("=" * 60)
        print("⚠ WARNING: This will reset Sigil's environment!")
        print("\nClearing:")
        print(f"  ✓ {len(State.aliases)} aliases")
        print(f"  ✓ {len(State.functions)} functions")
        print(f"  ✓ {len(State.undo_stack)} undo entries")
        print(f"  ✓ {len(State.redo_stack)} redo entries")
        
        # Variables summary
        vars_to_clear_count = 0
        vars_to_keep_count = 0
        for var in State.variables:
            if var not in GlobalCleaner.PROTECTED_VARS:
                vars_to_clear_count += 1
            else:
                vars_to_keep_count += 1
        
        print(f"  ✓ {vars_to_clear_count} user variables")
        if vars_to_keep_count > 0:
            print(f"  ✗ {vars_to_keep_count} protected variables (not cleared)")
        
        print("=" * 60)
        
        # Ask for confirmation
        try:
            response = input("Continue? (yes/no): ").strip().lower()
            if response not in ('yes', 'y'):
                print("✗ Cleanup cancelled")
                set_last_exit(0)
                return
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Cleanup cancelled")
            set_last_exit(0)
            return
        
        # Perform cleanup
        cleared_items = []
        
        try:
            # 1. Clear variables (except protected ones)
            vars_to_delete = []
            for var_name in list(State.variables.keys()):
                if var_name not in GlobalCleaner.PROTECTED_VARS:
                    # Don't delete if variable is readonly
                    if var_name in State.readonly_vars:
                        print(f"  ⚠ Skipping readonly variable: {var_name}")
                        continue
                    
                    # Remove from exported vars
                    if var_name in State.exported_vars:
                        State.exported_vars.remove(var_name)
                        # Also remove from environment
                        if var_name in os.environ:
                            del os.environ[var_name]
                    
                    # Remove from variables dict
                    del State.variables[var_name]
                    vars_to_delete.append(var_name)
            
            if vars_to_delete:
                cleared_items.append(f"{len(vars_to_delete)} variables")
            
            # 2. Clear aliases
            alias_count = len(State.aliases)
            if alias_count > 0:
                State.aliases.clear()
                cleared_items.append(f"{alias_count} aliases")
            
            # 3. Clear functions
            function_count = len(State.functions)
            if function_count > 0:
                State.functions.clear()
                cleared_items.append(f"{function_count} functions")
            
            # 4. Clear undo/redo stacks
            undo_count = len(State.undo_stack)
            redo_count = len(State.redo_stack)
            if undo_count > 0:
                State.undo_stack.clear()
                cleared_items.append(f"{undo_count} undo entries")
            if redo_count > 0:
                State.redo_stack.clear()
                cleared_items.append(f"{redo_count} redo entries")
            
            # 5. Save the clean state to RC file
            if not State.loading_rc:
                try:
                    RCManager.save()
                except Exception as e:
                    print(f"  ⚠ Could not save clean state: {e}")
            
            # Show completion message
            if cleared_items:
                print(f"\n✅ Global cleanup complete!")
                print(f"   Cleared: {', '.join(cleared_items)}")
                
                # Show remaining protected variables
                if State.variables:
                    protected_vars = [v for v in State.variables.keys() if v in GlobalCleaner.PROTECTED_VARS]
                    if protected_vars:
                        print(f"   Protected: {len(protected_vars)} variables kept")
            else:
                print("\n✅ Nothing to clean (already clean)")
            
            set_last_exit(0)
            
        except Exception as e:
            print(f"\n❌ Cleanup failed: {e}")
            import traceback
            traceback.print_exc()
            set_last_exit(1)
    
    @staticmethod
    def cnf(args: List[str]) -> None:
        """Confirm Clean - reset Sigil environment without confirmation
        
        Usage: cnf
        
        This command does the same as 'gbc' but without asking for confirmation.
        
        Example:
          cnf  # Clears everything immediately without confirmation
        """
        # Show summary
        print("🔧 Global Cleaner (No Confirmation)")
        print("=" * 60)
        
        # Perform cleanup directly
        cleared_items = []
        
        try:
            # 1. Clear variables (except protected ones)
            vars_to_delete = []
            for var_name in list(State.variables.keys()):
                if var_name not in GlobalCleaner.PROTECTED_VARS:
                    # Don't delete if variable is readonly
                    if var_name in State.readonly_vars:
                        continue
                    
                    # Remove from exported vars
                    if var_name in State.exported_vars:
                        State.exported_vars.remove(var_name)
                        # Also remove from environment
                        if var_name in os.environ:
                            del os.environ[var_name]
                    
                    # Remove from variables dict
                    del State.variables[var_name]
                    vars_to_delete.append(var_name)
            
            if vars_to_delete:
                cleared_items.append(f"{len(vars_to_delete)} variables")
            
            # 2. Clear aliases
            alias_count = len(State.aliases)
            if alias_count > 0:
                State.aliases.clear()
                cleared_items.append(f"{alias_count} aliases")
            
            # 3. Clear functions
            function_count = len(State.functions)
            if function_count > 0:
                State.functions.clear()
                cleared_items.append(f"{function_count} functions")
            
            # 4. Clear undo/redo stacks
            undo_count = len(State.undo_stack)
            redo_count = len(State.redo_stack)
            if undo_count > 0:
                State.undo_stack.clear()
                cleared_items.append(f"{undo_count} undo entries")
            if redo_count > 0:
                State.redo_stack.clear()
                cleared_items.append(f"{redo_count} redo entries")
            
            # 5. Save the clean state to RC file
            if not State.loading_rc:
                try:
                    RCManager.save()
                except Exception as e:
                    print(f"  ⚠ Could not save clean state: {e}")
            
            # Show completion message
            if cleared_items:
                print(f"✅ Global cleanup complete!")
                print(f"   Cleared: {', '.join(cleared_items)}")
            else:
                print("✅ Nothing to clean (already clean)")
            
            set_last_exit(0)
            
        except Exception as e:
            print(f"\n❌ Cleanup failed: {e}")
            import traceback
            traceback.print_exc()
            set_last_exit(1)

# ============================================================================
# FUNCTION COMMANDS (NEW)
# ============================================================================

class FunctionCommands:
    """Function management commands"""
    
    @staticmethod
    def fnc(args: List[str]) -> None:
        """Define a function in one line using 'nxt' as separator
        
        Usage: fnc <name> <command1> nxt <command2> nxt <command3> ...
        
        Example:
          fnc test mk dir test nxt say made a folder called test nxt pse
          
        This creates a function named 'test' that when called will:
          1. Create a directory named 'test'
          2. Print "made a folder called test"
          3. Wait for any key press
        """
        if len(args) < 3:
            print("Usage: fnc <name> <command1> nxt <command2> ...")
            print("\nExample:")
            print("  fnc test mk dir test nxt say made a folder called test nxt pse")
            print("  fnc greet say Hello nxt say World nxt wait 1")
            set_last_exit(1)
            return
        
        name = args[0]
        
        # Join the rest of the arguments
        rest = " ".join(args[1:])
        
        # Split by 'nxt' to get individual commands
        commands = [cmd.strip() for cmd in rest.split("nxt") if cmd.strip()]
        
        if not commands:
            print(f"⚠ Function '{name}' has no commands")
            set_last_exit(1)
            return
        
        # Store the function
        State.functions[name] = commands
        
        # Save to RC file if not loading RC
        if not State.loading_rc:
            try:
                RCManager.save()
            except Exception as e:
                print(f"⚠ Could not save function to .sigilrc: {e}")
        
        print(f"✓ Function '{name}' defined with {len(commands)} command(s)")
        set_last_exit(0)
    
    @staticmethod
    def clf(args: List[str]) -> None:
        """Call a previously defined function
        
        Usage: clf <name>
        
        Example:
          clf test  # Calls the function named 'test'
        """
        if not args:
            print("Usage: clf <name>")
            print("\nExample:")
            print("  clf test")
            set_last_exit(1)
            return
        
        name = args[0]
        
        if name not in State.functions:
            print(f"⚠ Function not found: {name}")
            set_last_exit(1)
            return
        
        # Get the function commands
        commands = State.functions[name]
        
        # Execute each command in the function
        print(f"🔧 Calling function: {name}")
        
        for i, cmd in enumerate(commands, 1):
            # Expand variables in the command before execution
            expanded_cmd = TextProcessor.expand_aliases_and_vars(cmd)
            
            # Log the command execution
            if not State.loading_rc:
                ExecutionLogger.log_execution("FUNC", f"{name}: {cmd}", 0)
            
            # Execute the command
            try:
                # Use the interpreter to execute the command
                Interpreter._execute_line(expanded_cmd, from_script=True)
            except SystemExit as e:
                # If the function calls exit, propagate it
                raise
            except BreakException:
                # If the function calls break, stop executing the function
                print(f"  ⚠ Break in function '{name}' at command {i}")
                break
            except Exception as e:
                print(f"  ⚠ Error in function '{name}' at command {i}: {e}")
                print(f"    Command: {cmd}")
                set_last_exit(1)
                return
        
        print(f"✓ Function '{name}' completed")
        set_last_exit(0)
    
    @staticmethod
    def fnlist(args: List[str]) -> None:
        """List all defined functions
        
        Usage: fnlist
        """
        if not State.functions:
            print("No functions defined")
            set_last_exit(0)
            return
        
        print("\n🔧 Defined Functions:\n")
        for name, commands in sorted(State.functions.items()):
            print(f"  {name}:")
            for i, cmd in enumerate(commands, 1):
                print(f"    {i:2}. {cmd}")
            print()
        
        set_last_exit(0)
    
    @staticmethod
    def fnrm(args: List[str]) -> None:
        """Remove a function
        
        Usage: fnrm <name>
        
        Example:
          fnrm test  # Removes the function named 'test'
        """
        if not args:
            print("Usage: fnrm <name>")
            print("\nExample:")
            print("  fnrm test")
            set_last_exit(1)
            return
        
        name = args[0]
        
        if name not in State.functions:
            print(f"⚠ Function not found: {name}")
            set_last_exit(1)
            return
        
        # Remove the function
        del State.functions[name]
        
        # Save to RC file if not loading RC
        if not State.loading_rc:
            try:
                RCManager.save()
            except Exception as e:
                print(f"⚠ Could not save changes to .sigilrc: {e}")
        
        print(f"✓ Function removed: {name}")
        set_last_exit(0)

# ============================================================================
# GUI UTILITIES
# ============================================================================

class GUIPrompt:
    """Handle graphical prompt dialogs using tkinter"""

    @staticmethod
    def show_prompt(title: str, fields: List[Tuple[str, str]]) -> Dict[str, str]:
        """
        Show a graphical prompt dialog with multiple fields.
        
        Args:
            title: Dialog title
            fields: List of (field_name, field_type) tuples
                    field_type can be: "text", "password", "number", "checkbox"
        
        Returns:
            Dictionary mapping field names to values, or empty dict if cancelled
        """
        if not HAS_TKINTER:
            print("⚠ Tkinter not available, falling back to console input")
            return GUIPrompt._console_fallback(title, fields)

        result = {}
        cancelled = [False]

        def on_submit():
            for name, entry in entries.items():
                if field_types[name] == "checkbox":
                    # For checkboxes, get the value from the BooleanVar
                    result[name] = vars_dict[name].get()
                else:
                    # For other field types, get the value from the Entry widget
                    result[name] = entry.get()
            root.quit()

        def on_cancel():
            cancelled[0] = True
            root.quit()

        root = tk.Tk()
        root.title(title)
        root.geometry("400x300")
        
        # Center window
        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
        y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
        root.geometry(f"+{x}+{y}")

        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        entries = {}
        vars_dict = {}
        field_types = {}  # Track field types

        for idx, (field_name, field_type) in enumerate(fields):
            field_types[field_name] = field_type  # Store field type
            
            label = ttk.Label(main_frame, text=field_name + ":")
            label.grid(row=idx, column=0, sticky=tk.W, pady=5)

            if field_type == "checkbox":
                var = tk.BooleanVar(value=False)  # Default to unchecked
                vars_dict[field_name] = var
                entry = ttk.Checkbutton(main_frame, variable=var)
                entries[field_name] = entry
            elif field_type == "password":
                entry = ttk.Entry(main_frame, show="*", width=30)
                entries[field_name] = entry
            elif field_type == "number":
                entry = ttk.Entry(main_frame, width=30)
                entries[field_name] = entry
            else:  # text or default
                entry = ttk.Entry(main_frame, width=30)
                entries[field_name] = entry

            entry.grid(row=idx, column=1, sticky=(tk.W, tk.E), pady=5)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=len(fields), column=0, columnspan=2, pady=10)

        submit_btn = ttk.Button(button_frame, text="OK", command=on_submit)
        submit_btn.grid(row=0, column=0, padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=on_cancel)
        cancel_btn.grid(row=0, column=1, padx=5)

        # Bind Enter to submit
        root.bind('<Return>', lambda e: on_submit())
        root.bind('<Escape>', lambda e: on_cancel())

        # Focus first entry
        if entries:
            first_entry = list(entries.values())[0]
            if not isinstance(first_entry, tk.Checkbutton):
                first_entry.focus()

        root.mainloop()
        root.destroy()

        return {} if cancelled[0] else result

    @staticmethod
    def _console_fallback(title: str, fields: List[Tuple[str, str]]) -> Dict[str, str]:
        """Console fallback when tkinter is not available"""
        print(f"\n{title}")
        print("=" * len(title))
        result = {}
        
        try:
            for field_name, field_type in fields:
                if field_type == "checkbox":
                    value = input(f"{field_name} (yes/no): ").strip().lower()
                    result[field_name] = value in ('yes', 'y', 'true', '1')
                elif field_type == "password":
                    result[field_name] = getpass.getpass(f"{field_name}: ")
                else:
                    result[field_name] = input(f"{field_name}: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return {}
        
        return result

# ============================================================================
# SHELL INTEGRATION
# ============================================================================

class ShellRunner:
    """Run external shell commands"""

    @staticmethod
    def run_and_print(cmd_list: List[str], interactive: bool = False) -> int:
        """Run command and print output, return exit code"""
        try:
            if interactive:
                result = subprocess.run(cmd_list)
                rc = result.returncode if hasattr(result, 'returncode') else 0
            else:
                result = subprocess.run(
                    cmd_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.stdout:
                    print(result.stdout, end='')
                if result.stderr:
                    print(result.stderr, end='', flush=True)
                rc = result.returncode

        except FileNotFoundError:
            print(f"⚠ Shell not found: {cmd_list[0]}")
            rc = 127
        except Exception as e:
            print(f"⚠ Error running subprocess: {e}")
            rc = 1

        set_last_exit(rc)
        return rc

    @staticmethod
    def powershell(args: List[str]) -> None:
        """Run PowerShell command"""
        pwsh = shutil.which('pwsh') or shutil.which('powershell')
        if not pwsh:
            print("⚠ PowerShell not found on PATH")
            set_last_exit(127)
            return

        if not args:
            ShellRunner.run_and_print([pwsh], interactive=True)
        else:
            cmd_str = " ".join(args)
            ShellRunner.run_and_print([pwsh, '-NoProfile', '-NonInteractive', '-Command', cmd_str])

    @staticmethod
    def cmd(args: List[str]) -> None:
        """Run cmd.exe or system shell command"""
        if not args:
            if os.name == 'nt':
                ShellRunner.run_and_print(['cmd'], interactive=True)
            else:
                shell = os.environ.get('SHELL', '/bin/sh')
                ShellRunner.run_and_print([shell], interactive=True)
            return

        cmd_str = " ".join(args)
        if os.name == 'nt':
            ShellRunner.run_and_print(['cmd', '/c', cmd_str])
        else:
            shell = os.environ.get('SHELL', '/bin/sh')
            ShellRunner.run_and_print([shell, '-c', cmd_str])

    @staticmethod
    def sh(args: List[str]) -> None:
        """Run POSIX shell command"""
        shell = os.environ.get('SHELL') or shutil.which('bash') or shutil.which('sh')
        if not shell:
            print("⚠ No POSIX shell found")
            set_last_exit(127)
            return

        if not args:
            ShellRunner.run_and_print([shell], interactive=True)
        else:
            cmd_str = " ".join(args)
            if 'bash' in os.path.basename(shell):
                ShellRunner.run_and_print([shell, '-lc', cmd_str])
            else:
                ShellRunner.run_and_print([shell, '-c', cmd_str])

# ============================================================================
# COMMAND IMPLEMENTATIONS
# ============================================================================

class Commands:
    """All command implementations"""

    # Help text database
    HELP_TEXT = {
        "help": "help [command]\n  Show all commands or help for a specific command",
        "mk": "mk dir <name>  — Create directory\nmk file <name> [content]  — Create file",
        "cpy": "cpy <src> <dst>  — Copy file or directory",
        "dlt": "dlt <path>  — Delete file or directory",
        "move": "move file <src> <dst>  — Move/rename file",
        "cd": "cd <path>  — Change directory\ncd  — Show current directory",
        "pwd": "pwd  — Print working directory",
        "dirlook": "dirlook  — List directory contents",
        "opnlnk": "opnlnk <url>  — Open URL in browser",
        "opn": "opn <path>  — Open file with default application",
        "ex": "ex  — Open file explorer (Windows only)",
        "task": "task  — List running processes",
        "kill": "kill task <name>  — Force kill process",
        "clo": "clo task <name>  — Close process gracefully",
        "say": "say <text>  — Print text (expands variables)",
        "undo": "undo  — Undo last file operation",
        "redo": "redo  — Redo last undone operation",
        "add": "add <n1> <n2> [...]  — Add numbers",
        "sub": "sub <n1> <n2> [...]  — Subtract numbers",
        "mul": "mul <n1> <n2> [...]  — Multiply numbers",
        "div": "div <n1> <n2> [...]  — Divide numbers",
        "alia": "alia  — List all aliases\nalia <name> <command>  — Create alias",
        "unalia": "unalia <name>  — Remove alias",
        "let": "let <name> = <value>  — Set variable\nlet -r <name> = <value>  — Set readonly variable",
        "var": "var  — List all variables",
        "unset": "unset <name>  — Remove variable",
        "export": "export <name>  — Export variable to environment",
        "if": "if <condition> then <command>",
        "wait": "wait <seconds>  — Pause execution",
        "pse": "pse [message]  — Pause and wait for any key press",
        "rpt": "rpt <count|inf> <command>  — Repeat command\nrpt <count|inf> ... endrpt  — Repeat block",
        "ask": "ask <varname> [prompt]  — Prompt for input",
        "exit": "exit [code]  — Exit with code",
        "exists": "exists <path>  — Check if path exists",
        "arg": "arg <n>  — Get script argument\narg count  — Count arguments",
        "prof": "prof  — List profiles\nprof <name>  — Switch profile\nprof new <name>  — Create profile\nprof del <name>  — Delete profile",
        "run": "run <file.sig>  — Run script file",
        "inc": "inc <file.sig>  — Include script file",
        "wrt": "wrt line <n> <text> <file>  — Write line to file\nwrt json <key.path> <value> <file>  — Write JSON value",
        "gp": "gp <message> <field1_label> <field2_label>  — Display graphical prompt with two fields",
        "ide": "ide [filename]  — Open terminal-based code editor\n  Ctrl+S: Save, Ctrl+R: Run, Ctrl+Q: Quit, Ctrl+O: Open, Ctrl+F: Find",
        "edit": "Alias for 'ide'",
        "case": "case <var> ... when <val> ... else ... endcase  — Switch statement",
        "goto": "goto <label>  — Jump to label",
        "brk": "brk  — Break from loop/case",
        "pin": "pin <path>  — Install plugin",
        "prv": "prv <name>  — Remove plugin",
        "sdow": "sdow  — Shutdown computer (with confirmation)",
        "shutdown": "shutdown  — Shutdown computer (with confirmation)",
        "log": "log [show [count] | clear | tail]\n  View or manage execution log",
        "pth": "pth add <directory>  — Add directory to PATH\npth rmv <directory>  — Remove directory from PATH\npth lst [-v]  — List PATH entries\npth has <directory>  — Check if directory is in PATH",
        "update": "update [force]  — Check for Sigil updates\n  Use 'update force' to bypass 24-hour check interval",
        "check-updates": "Alias for 'update'",
        "net": "net dwn <url> [save_path]  — Download file from URL\nnet png <host> [count]  — Ping host (1-100 times)",
        "zip": "zip <archive.zip> <file1> <file2> ...  — Create zip archive\nzip <archive.zip> -d <directory>  — Zip entire directory",
        "uzip": "uzip <archive.zip> [destination]  — Extract zip archive\nuzip <archive.zip> -l  — List archive contents",
        "unzip": "Alias for 'uzip'",
        "sns": "sns <script.sig> [arguments...]  — Start new script (ends current script)\n  Alias: exec",
        "exec": "Alias for 'sns'",
        "gbc": "gbc  — Global cleaner - reset Sigil environment (with confirmation)\n  Alias: clean, reset",
        "cnf": "cnf  — Global cleaner without confirmation (force clean)",
        "fnc": "fnc <name> <command1> nxt <command2> ...  — Define a function (one-line, multiple commands separated by 'nxt')",
        "clf": "clf <name>  — Call a function",
        "fnlist": "fnlist  — List all defined functions",
        "fnrm": "fnrm <name>  — Remove a function",
    }

    @staticmethod
    def help(args: List[str]) -> None:
        """Show help information"""
        if not args:
            print("\n🔮 Sigil Commands (v1.0.1):\n")
            categories = {
                "Files": ["mk", "cpy", "dlt", "move", "cd", "pwd", "dirlook", "opn", "opnlnk", "ex", "zip", "uzip"],
                "Network": ["net"],
                "Process": ["task", "kill", "clo"],
                "System": ["sdow", "shutdown", "pse", "pth", "update", "gbc", "cnf"],
                "Output": ["say"],
                "Math": ["add", "sub", "mul", "div"],
                "Variables": ["let", "var", "unset", "export", "alia", "unalia"],
                "Functions": ["fnc", "clf", "fnlist", "fnrm"],
                "Control": ["if", "case", "rpt", "goto", "brk", "exit", "wait", "pse"],
                "I/O": ["ask", "wrt", "gp"],
                "Scripts": ["run", "inc", "exists", "arg", "sns"],
                "Editor": ["ide", "edit"],
                "Config": ["prof"],
                "Plugins": ["pin", "prv"],
                "Shell": ["ps", "cmd", "sh"],
            }

            for category, cmds in categories.items():
                print(f"  {category}:")
                for cmd in cmds:
                    if cmd in Commands.HELP_TEXT:
                        desc = Commands.HELP_TEXT[cmd].split('\n')[0].split('—')[-1].strip()
                        print(f"    {cmd:12} — {desc}")
                print()

            print("Type: help <command> for details\n")
            print("Comments: & # // single-line, /* */ block comments\n")
            print(f"Version: {Config.VERSION}")
            return

        cmd_name = args[0]
        if cmd_name in Commands.HELP_TEXT:
            print(f"\n{Commands.HELP_TEXT[cmd_name]}\n")
        else:
            print(f"⚠ No help available for: {cmd_name}")

    @staticmethod
    def mk(args: List[str]) -> None:
        """Make directory or file"""
        if len(args) < 2:
            print(Commands.HELP_TEXT["mk"])
            set_last_exit(1)
            return

        target_type = args[0]

        if target_type == "dir":
            path = resolve_path(args[1])
            existed = path.exists()

            if not existed:
                path.mkdir(parents=True, exist_ok=True)

            UndoManager.push({
                "op": "mk_dir",
                "path": str(path),
                "existed": existed
            })
            print(f"✓ Created directory: {path}")
            set_last_exit(0)

        elif target_type == "file":
            path = resolve_path(args[1])
            content = " ".join(args[2:]) if len(args) > 2 else ""
            existed = path.exists()
            backup = None

            if existed:
                backup = UndoManager.backup_contents(path)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            UndoManager.push({
                "op": "mk_file",
                "path": str(path),
                "existed": existed,
                "backup": str(backup) if backup else None
            })
            print(f"✓ Created file: {path}")
            set_last_exit(0)
        else:
            print("⚠ Unknown target type (use 'dir' or 'file')")
            set_last_exit(1)

    @staticmethod
    def cpy(args: List[str]) -> None:
        """Copy file or directory"""
        if len(args) < 2:
            print(Commands.HELP_TEXT["cpy"])
            set_last_exit(1)
            return

        src = resolve_path(args[0])
        dst = resolve_path(args[1])

        if not src.exists():
            print(f"⚠ Source does not exist: {src}")
            set_last_exit(1)
            return

        dst_existed = dst.exists()
        dst_backup = None

        if dst_existed:
            if dst.is_dir():
                dst_backup = UndoManager.backup_path(dst)
            else:
                dst_backup = UndoManager.backup_contents(dst)

        try:
            if src.is_dir():
                if dst.exists():
                    print(f"⚠ Destination already exists: {dst}")
                    set_last_exit(1)
                    return
                shutil.copytree(str(src), str(dst))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))

            UndoManager.push({
                "op": "cpy",
                "src": str(src),
                "dst": str(dst),
                "dst_existed": dst_existed,
                "dst_backup": str(dst_backup) if dst_backup else None
            })

            print(f"✓ Copied: {src} → {dst}")
            set_last_exit(0)

        except Exception as e:
            print(f"⚠ Copy failed: {e}")
            set_last_exit(1)

    @staticmethod
    def dlt(args: List[str]) -> None:
        """Delete file or directory"""
        if not args:
            print(Commands.HELP_TEXT["dlt"])
            set_last_exit(1)
            return

        path = resolve_path(args[0])

        if not path.exists():
            print(f"⚠ Path does not exist: {path}")
            set_last_exit(1)
            return

        backup = UndoManager.backup_path(path)

        UndoManager.push({
            "op": "dlt",
            "path": str(path),
            "backup": str(backup) if backup else None
        })

        print(f"✓ Deleted: {path}")
        set_last_exit(0)

    @staticmethod
    def move(args: List[str]) -> None:
        """Move/rename file"""
        if len(args) < 3 or args[0] != "file":
            print(Commands.HELP_TEXT["move"])
            set_last_exit(1)
            return

        src = resolve_path(args[1])
        dst = resolve_path(args[2])

        if not src.exists():
            print(f"⚠ Source does not exist: {src}")
            set_last_exit(1)
            return

        dst_existed = dst.exists()
        dst_backup = None

        if dst_existed:
            if dst.is_dir():
                dst_backup = UndoManager.backup_path(dst)
            else:
                dst_backup = UndoManager.backup_contents(dst)

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

            UndoManager.push({
                "op": "move",
                "src": str(src),
                "dst": str(dst),
                "dst_existed": dst_existed,
                "dst_backup": str(dst_backup) if dst_backup else None
            })

            print(f"✓ Moved: {src} → {dst}")
            set_last_exit(0)

        except Exception as e:
            print(f"⚠ Move failed: {e}")
            set_last_exit(1)

    @staticmethod
    def cd(args: List[str]) -> None:
        """Change directory"""
        if not args:
            print(State.current_dir)
            set_last_exit(0)
            return

        path = resolve_path(args[0])

        if path.is_dir():
            State.current_dir = path
            print(f"📁 {State.current_dir}")
            set_last_exit(0)
        else:
            print(f"⚠ Not a directory: {path}")
            set_last_exit(1)

    @staticmethod
    def pwd(args: List[str]) -> None:
        """Print working directory"""
        print(State.current_dir)
        set_last_exit(0)

    @staticmethod
    def dirlook(args: List[str]) -> None:
        """List directory contents"""
        print(f"\n📁 {State.current_dir}\n")
        try:
            items = sorted(State.current_dir.iterdir())
            for item in items:
                if item.is_dir():
                    print(f"  📂 {item.name}/")
                else:
                    size = item.stat().st_size
                    size_str = f"{size:,}" if size < 1024 else f"{size/1024:.1f}K"
                    print(f"  📄 {item.name:40} {size_str:>10}")
            set_last_exit(0)
        except PermissionError:
            print("⚠ Permission denied")
            set_last_exit(1)

    @staticmethod
    def opnlnk(args: List[str]) -> None:
        """Open URL in browser"""
        if not args:
            print(Commands.HELP_TEXT["opnlnk"])
            set_last_exit(1)
            return

        try:
            webbrowser.open(args[0])
            print(f"✓ Opened: {args[0]}")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Failed to open URL: {e}")
            set_last_exit(1)

    @staticmethod
    def opn(args: List[str]) -> None:
        """Open file with default application"""
        if not args:
            print(Commands.HELP_TEXT["opn"])
            set_last_exit(1)
            return

        path = resolve_path(args[0])

        if not path.exists():
            print(f"⚠ Path does not exist: {path}")
            set_last_exit(1)
            return

        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)])
            else:
                subprocess.run(["xdg-open", str(path)])

            print(f"✓ Opened: {path}")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Failed to open: {e}")
            set_last_exit(1)

    @staticmethod
    def ex(args: List[str]) -> None:
        """Open file explorer"""
        if os.name == "nt":
            subprocess.Popen(["explorer", str(State.current_dir)])
            print(f"✓ Opened explorer: {State.current_dir}")
            set_last_exit(0)
        else:
            print("⚠ Explorer only supported on Windows")
            set_last_exit(1)

    @staticmethod
    def task(args: List[str]) -> None:
        """List running processes"""
        try:
            if os.name == "nt":
                result = subprocess.run(["tasklist"], capture_output=True, text=True)
            else:
                result = subprocess.run(["ps", "-e"], capture_output=True, text=True)

            print(result.stdout)
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Failed to list tasks: {e}")
            set_last_exit(1)

    @staticmethod
    def kill(args: List[str]) -> None:
        """Kill process"""
        if len(args) < 2 or args[0] != "task":
            print(Commands.HELP_TEXT["kill"])
            set_last_exit(1)
            return

        name = args[1]
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/IM", name, "/F"], check=True)
            else:
                subprocess.run(["pkill", "-9", name], check=True)

            print(f"✓ Killed: {name}")
            set_last_exit(0)
        except subprocess.CalledProcessError:
            print(f"⚠ Failed to kill: {name}")
            set_last_exit(1)

    @staticmethod
    def clo(args: List[str]) -> None:
        """Close process gracefully"""
        if len(args) < 2 or args[0] != "task":
            print(Commands.HELP_TEXT["clo"])
            set_last_exit(1)
            return

        name = args[1]
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/IM", name], check=True)
            else:
                subprocess.run(["pkill", name], check=True)

            print(f"✓ Closed: {name}")
            set_last_exit(0)
        except subprocess.CalledProcessError:
            print(f"⚠ Failed to close: {name}")
            set_last_exit(1)

    @staticmethod
    def log(args: List[str]) -> None:
        """View or manage execution log"""
        if not args or args[0] == "show":
            # Show recent log entries
            try:
                if not ExecutionLogger.LOG_FILE.exists():
                    print("No execution log found")
                    set_last_exit(0)
                    return
                
                with open(ExecutionLogger.LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                if len(lines) <= 4:  # Header lines
                    print("Execution log is empty")
                    set_last_exit(0)
                    return
                
                # Show last 20 entries by default, or specific number
                count = 20
                if args and len(args) > 1 and args[0] == "show":
                    try:
                        count = int(args[1])
                    except (ValueError, TypeError):
                        pass
                
                print(f"\n📝 Execution Log (last {count} entries):")
                print("=" * 100)
                # Skip header (first 3 lines)
                entries = lines[3:]
                entries.reverse()  # Show newest first
                
                for i, entry in enumerate(entries[:count]):
                    if entry.strip() and not entry.startswith("#"):
                        print(f"{i+1:3}. {entry.strip()}")
                
                print("=" * 100)
                print(f"Log file: {ExecutionLogger.LOG_FILE}")
                set_last_exit(0)
                
            except Exception as e:
                print(f"⚠ Error reading log: {e}")
                set_last_exit(1)
        
        elif args[0] == "clear":
            # Clear the log
            if confirm_destructive_action("clear the execution log"):
                try:
                    ExecutionLogger.init_log_file()
                    print("✓ Execution log cleared")
                    set_last_exit(0)
                except Exception as e:
                    print(f"⚠ Error clearing log: {e}")
                    set_last_exit(1)
        
        elif args[0] == "tail":
            # Tail the log file
            try:
                import subprocess
                if os.name == "nt":
                    # Windows
                    subprocess.run(["powershell", "-Command", f"Get-Content {ExecutionLogger.LOG_FILE} -Wait -Tail 20"])
                else:
                    # Unix/Linux
                    subprocess.run(["tail", "-f", str(ExecutionLogger.LOG_FILE)])
                set_last_exit(0)
            except Exception as e:
                print(f"⚠ Error tailing log: {e}")
                set_last_exit(1)
        
        else:
            print("Usage: log [show [count] | clear | tail]")
            print("  show [count] - Show recent log entries (default: 20)")
            print("  clear        - Clear the execution log")
            print("  tail         - Follow the log file in real-time")
            set_last_exit(1)

    @staticmethod
    def say(args: List[str]) -> None:
        """Print text with variable expansion"""
        parts = []
        for token in args:
            if token.startswith("$") and token[1:] in State.variables:
                parts.append(str(State.variables[token[1:]]))
            elif token in State.variables:
                parts.append(str(State.variables[token]))
            else:
                parts.append(token)

        print(" ".join(parts))
        set_last_exit(0)

    @staticmethod
    def add(args: List[str]) -> None:
        """Add numbers"""
        if not args:
            print(Commands.HELP_TEXT["add"])
            set_last_exit(1)
            return

        try:
            numbers = parse_numbers(args)
            result = sum(numbers)
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            print(result)
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Error: {e}")
            set_last_exit(1)

    @staticmethod
    def sub(args: List[str]) -> None:
        """Subtract numbers"""
        if len(args) < 2:
            print(Commands.HELP_TEXT["sub"])
            set_last_exit(1)
            return

        try:
            numbers = parse_numbers(args)
            result = numbers[0]
            for num in numbers[1:]:
                result -= num
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            print(result)
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Error: {e}")
            set_last_exit(1)

    @staticmethod
    def mul(args: List[str]) -> None:
        """Multiply numbers"""
        if not args:
            print(Commands.HELP_TEXT["mul"])
            set_last_exit(1)
            return

        try:
            numbers = parse_numbers(args)
            result = 1
            for num in numbers:
                result *= num
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            print(result)
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Error: {e}")
            set_last_exit(1)

    @staticmethod
    def div(args: List[str]) -> None:
        """Divide numbers"""
        if len(args) < 2:
            print(Commands.HELP_TEXT["div"])
            set_last_exit(1)
            return

        try:
            numbers = parse_numbers(args)
            result = float(numbers[0])
            for num in numbers[1:]:
                if num == 0:
                    print("⚠ Division by zero")
                    set_last_exit(1)
                    return
                result /= num

            if result.is_integer():
                result = int(result)
            print(result)
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Error: {e}")
            set_last_exit(1)

    @staticmethod
    def alia(args: List[str]) -> None:
        """Manage aliases"""
        if not args:
            if not State.aliases:
                print("No aliases defined")
                set_last_exit(1)
                return

            print("\n📖 Aliases:\n")
            for name, cmd in sorted(State.aliases.items()):
                print(f"  {name:15} → {cmd}")
            print()
            set_last_exit(0)
            return

        if len(args) >= 2:
            name = args[0]
            cmd_str = " ".join(args[1:])
            State.aliases[name] = cmd_str

            if not State.loading_rc:
                RCManager.save()

            print(f"✓ Alias set: {name} → {cmd_str}")
            set_last_exit(0)
        else:
            print(Commands.HELP_TEXT["alia"])
            set_last_exit(1)

    @staticmethod
    def unalia(args: List[str]) -> None:
        """Remove alias"""
        if not args:
            print(Commands.HELP_TEXT["unalia"])
            set_last_exit(1)
            return

        name = args[0]
        if name in State.aliases:
            del State.aliases[name]
            if not State.loading_rc:
                RCManager.save()
            print(f"✓ Alias removed: {name}")
            set_last_exit(0)
        else:
            print(f"⚠ Alias not found: {name}")
            set_last_exit(1)

    @staticmethod
    def let(args: List[str]) -> None:
        """Set variable"""
        if not args:
            print(Commands.HELP_TEXT["let"])
            set_last_exit(1)
            return

        # Check for readonly flag
        readonly = False
        if args[0] == "-r":
            readonly = True
            args = args[1:]

        if not args:
            print(Commands.HELP_TEXT["let"])
            set_last_exit(1)
            return

        # Parse variable name and value
        if len(args) == 1:
            name = args[0]
            value = ""
        elif len(args) >= 3 and args[1] == "=":
            name = args[0]
            value = " ".join(args[2:])
        elif len(args) >= 2:
            name = args[0]
            value = " ".join(args[1:])
        else:
            print(Commands.HELP_TEXT["let"])
            set_last_exit(1)
            return

        # Check for readonly violation
        if name in State.readonly_vars and not readonly:
            print(f"⚠ Cannot modify readonly variable: {name}")
            set_last_exit(1)
            return

        # Process value
        tokens = TextProcessor.tokenize(value)

        # Handle 'ask' sugar: let x = ask "prompt"
        if tokens and tokens[0] == 'ask':
            prompt = " ".join(tokens[1:]) if len(tokens) > 1 else ""
            if prompt.startswith('"') and prompt.endswith('"'):
                prompt = prompt[1:-1]
            else:
                prompt = TextProcessor.expand_vars_in_string(prompt)

            try:
                entered = input(prompt + (" " if prompt else ""))
            except EOFError:
                entered = ""

            final_value = entered
        else:
            # Normal value processing
            if value.startswith('"') and value.endswith('"'):
                final_value = value[1:-1].replace('\\"', '"')
                final_value = TextProcessor.expand_vars_in_string(final_value)
            else:
                expanded = TextProcessor.expand_vars_in_string(value)
                # Try to parse as number
                try:
                    if "." in expanded or "e" in expanded.lower():
                        final_value = float(expanded)
                    else:
                        final_value = int(expanded)
                except (ValueError, TypeError):
                    final_value = expanded

        # Set variable
        State.variables[name] = final_value

        if readonly:
            State.readonly_vars.add(name)
        else:
            State.readonly_vars.discard(name)

        if not State.loading_rc:
            RCManager.save()

        print(f"✓ {name} = {final_value}")
        set_last_exit(0)

    @staticmethod
    def var(args: List[str]) -> None:
        """List variables"""
        if not State.variables:
            print("No variables defined")
            set_last_exit(1)
            return

        print("\n💾 Variables:\n")
        for name, value in sorted(State.variables.items()):
            flags = []
            if name in State.readonly_vars:
                flags.append("readonly")
            if name in State.exported_vars:
                flags.append("exported")

            flag_str = f" ({', '.join(flags)})" if flags else ""
            print(f"  {name:15} = {value}{flag_str}")
        print()
        set_last_exit(0)

    @staticmethod
    def unset(args: List[str]) -> None:
        """Remove variable"""
        if not args:
            print(Commands.HELP_TEXT["unset"])
            set_last_exit(1)
            return

        name = args[0]

        if name not in State.variables:
            print(f"⚠ Variable not found: {name}")
            set_last_exit(1)
            return

        if name in State.readonly_vars:
            print(f"⚠ Cannot unset readonly variable: {name}")
            set_last_exit(1)
            return

        del State.variables[name]
        State.exported_vars.discard(name)

        if not State.loading_rc:
            RCManager.save()

        print(f"✓ Unset: {name}")
        set_last_exit(0)

    @staticmethod
    def export(args: List[str]) -> None:
        """Export variable to environment"""
        if not args:
            print(Commands.HELP_TEXT["export"])
            set_last_exit(1)
            return

        name = args[0]

        if name not in State.variables:
            print(f"⚠ Variable not defined: {name}")
            set_last_exit(1)
            return

        State.exported_vars.add(name)
        os.environ[name] = str(State.variables[name])

        if not State.loading_rc:
            RCManager.save()

        print(f"✓ Exported: {name}")
        set_last_exit(0)

    @staticmethod
    def ask(args: List[str]) -> None:
        """Prompt for user input"""
        if not args:
            print(Commands.HELP_TEXT["ask"])
            set_last_exit(1)
            return

        # Parse: ask = <name> or ask <name> [prompt]
        if args[0] == "=":
            if len(args) < 2:
                print(Commands.HELP_TEXT["ask"])
                set_last_exit(1)
                return
            name = args[1]
            prompt = ""
        else:
            name = args[0]
            prompt = " ".join(args[1:]) if len(args) > 1 else ""
            if prompt.startswith('"') and prompt.endswith('"'):
                prompt = prompt[1:-1]

        try:
            value = input(prompt + (" " if prompt else ""))
        except EOFError:
            value = ""

        State.variables[name] = value
        set_last_exit(0)

    @staticmethod
    def wait(args: List[str]) -> None:
        """Pause execution"""
        if not args:
            print(Commands.HELP_TEXT["wait"])
            set_last_exit(1)
            return

        try:
            seconds = float(args[0])
            time.sleep(seconds)
            set_last_exit(0)
        except (ValueError, TypeError):
            print("⚠ Invalid number")
            set_last_exit(1)

    @staticmethod
    def pse(args: List[str]) -> None:
        """Pause execution and wait for any key press"""
        # Custom prompt if provided
        if args:
            prompt = " ".join(args)
            # Handle quoted prompts
            if prompt.startswith('"') and prompt.endswith('"'):
                prompt = prompt[1:-1]
            elif prompt.startswith("'") and prompt.endswith("'"):
                prompt = prompt[1:-1]
        else:
            prompt = "Press any key to continue . . ."
        
        wait_for_any_key(prompt)
        set_last_exit(0)

    @staticmethod
    def exists(args: List[str]) -> None:
        """Check if path exists"""
        if not args:
            print(Commands.HELP_TEXT["exists"])
            set_last_exit(1)
            return

        path = resolve_path(args[0])
        exists = path.exists()

        print("yes" if exists else "no")
        set_last_exit(0 if exists else 1)

    @staticmethod
    def arg(args: List[str]) -> None:
        """Get script argument"""
        if not args:
            print(Commands.HELP_TEXT["arg"])
            set_last_exit(1)
            return

        if args[0] == "count":
            print(len(State.script_args))
            set_last_exit(0)
        else:
            try:
                index = int(args[0])
                if 0 <= index < len(State.script_args):
                    print(State.script_args[index])
                    set_last_exit(0)
                else:
                    print(f"⚠ Index out of range: {index}")
                    set_last_exit(1)
            except (ValueError, TypeError):
                print("⚠ Invalid index")
                set_last_exit(1)

    @staticmethod
    def prof(args: List[str]) -> None:
        """Manage profiles"""
        if not args:
            # List profiles
            profiles = {"default"}
            try:
                for item in Config.CONFIG_DIR.iterdir():
                    if item.name.startswith(".sigilrc."):
                        name = item.name.replace(".sigilrc.", "")
                        if not name.endswith(".bak"):
                            profiles.add(name)
            except Exception:
                pass

            print("\n👤 Profiles:\n")
            for profile in sorted(profiles):
                current = " (current)" if profile == State.current_profile else ""
                print(f"  {profile}{current}")
            print()
            set_last_exit(0)
            return

        subcommand = args[0]

        if subcommand == "show":
            print(f"Current profile: {State.current_profile}")
            set_last_exit(0)
            return

        if subcommand == "new" and len(args) == 2:
            name = args[1]
            path = RCManager.get_rc_path(name)

            if path.exists():
                print(f"⚠ Profile already exists: {name}")
                set_last_exit(1)
                return

            path.write_text(f"# Sigil Profile: {name}\n", encoding="utf-8")
            print(f"✓ Created profile: {name}")
            set_last_exit(0)
            return

        if subcommand == "del" and len(args) == 2:
            name = args[1]

            if name == "default":
                print("⚠ Cannot delete default profile")
                set_last_exit(1)
                return

            path = RCManager.get_rc_path(name)

            if not path.exists():
                print(f"⚠ Profile not found: {name}")
                set_last_exit(1)
                return

            path.unlink()
            print(f"✓ Deleted profile: {name}")
            set_last_exit(0)
            return

        # Switch to profile
        name = subcommand
        State.current_profile = name
        State.aliases.clear()
        State.variables.clear()
        State.readonly_vars.clear()
        State.exported_vars.clear()
        State.functions.clear()

        path = RCManager.get_rc_path()
        if not path.exists():
            path.write_text(f"# Sigil Profile: {name}\n", encoding="utf-8")

        RCManager.load()
        print(f"✓ Switched to profile: {name}")
        set_last_exit(0)

    @staticmethod
    def run(args: List[str]) -> None:
        """Run script file"""
        if not args:
            print(Commands.HELP_TEXT["run"])
            set_last_exit(1)
            return

        path = resolve_path(args[0])

        if not path.exists():
            print(f"⚠ File not found: {path}")
            set_last_exit(1)
            return

        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Save context
            prev_file = State.script_file
            prev_dir = State.script_dir
            prev_args = State.script_args[:]

            try:
                State.script_file = str(path)
                State.script_dir = str(path.parent)
                State.script_args = args[1:] if len(args) > 1 else []

                Interpreter.run_lines(lines)
            finally:
                State.script_file = prev_file
                State.script_dir = prev_dir
                State.script_args = prev_args

        except Exception as e:
            print(f"⚠ Script error: {e}")
            set_last_exit(1)

    @staticmethod
    def inc(args: List[str]) -> None:
        """Include script file"""
        if not args:
            print(Commands.HELP_TEXT["inc"])
            set_last_exit(1)
            return

        path = resolve_path(args[0])

        if not path.exists():
            print(f"⚠ File not found: {path}")
            set_last_exit(1)
            return

        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            Interpreter.run_lines(lines)
        except Exception as e:
            print(f"⚠ Include error: {e}")
            set_last_exit(1)

    @staticmethod
    def wrt(args: List[str]) -> None:
        """Write to file"""
        if not args:
            print(Commands.HELP_TEXT["wrt"])
            set_last_exit(1)
            return

        mode = args[0]

        if mode == "line":
            if len(args) < 4:
                print(Commands.HELP_TEXT["wrt"])
                set_last_exit(1)
                return

            try:
                line_num = int(args[1])
            except (ValueError, TypeError):
                print("⚠ Invalid line number")
                set_last_exit(1)
                return

            text = args[2]
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1].replace('\\"', '"')

            path = resolve_path(args[3])

            try:
                lines = []
                if path.exists():
                    lines = path.read_text(encoding="utf-8").splitlines()

                # Ensure enough lines
                while len(lines) < line_num:
                    lines.append("")

                lines[line_num - 1] = text

                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

                print(f"✓ Wrote line {line_num} to {path}")
                set_last_exit(0)
            except Exception as e:
                print(f"⚠ Write failed: {e}")
                set_last_exit(1)

        elif mode == "json":
            if len(args) < 4:
                print(Commands.HELP_TEXT["wrt"])
                set_last_exit(1)
                return

            key_path = args[1]
            value_token = args[2]
            file_path = resolve_path(args[3])

            # Parse value
            if value_token.lower() == "true":
                value = True
            elif value_token.lower() == "false":
                value = False
            elif value_token.lower() == "null":
                value = None
            elif value_token.startswith('"') and value_token.endswith('"'):
                value = value_token[1:-1].replace('\\"', '"')
            else:
                try:
                    if "." in value_token or "e" in value_token.lower():
                        value = float(value_token)
                    else:
                        value = int(value_token)
                except (ValueError, TypeError):
                    value = value_token

            try:
                # Load existing JSON
                data = {}
                if file_path.exists():
                    try:
                        data = json.loads(file_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        data = {}

                # Navigate to nested key
                parts = key_path.split(".")
                current = data

                for part in parts[:-1]:
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]

                current[parts[-1]] = value

                # Write JSON
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

                print(f"✓ Wrote {key_path} = {value} to {file_path}")
                set_last_exit(0)
            except Exception as e:
                print(f"⚠ JSON write failed: {e}")
                set_last_exit(1)
        else:
            print(f"⚠ Unknown mode: {mode}")
            set_last_exit(1)

    @staticmethod
    def undo(args: List[str]) -> None:
        """Undo last file operation"""
        if not State.undo_stack:
            print("⚠ Nothing to undo")
            set_last_exit(1)
            return

        action = State.undo_stack.pop()
        State.redo_stack.append(action)

        op = action.get("op")
        try:
            if op == "mk_file":
                path = Path(action["path"])
                existed = action.get("existed", False)
                backup = action.get("backup")
                if existed and backup:
                    # restore previous contents
                    shutil.copy2(backup, str(path))
                else:
                    if path.exists():
                        if path.is_dir():
                            shutil.rmtree(str(path))
                        else:
                            path.unlink()
            elif op == "mk_dir":
                path = Path(action["path"])
                if path.exists() and path.is_dir():
                    shutil.rmtree(str(path))
            elif op == "dlt":
                backup = action.get("backup")
                if backup:
                    # move back
                    UndoManager.safe_move(Path(backup), Path(action["path"]))
            elif op in ("cpy", "move"):
                # best-effort restore
                dst = Path(action.get("dst", ""))
                src = Path(action.get("src", ""))
                dst_backup = action.get("dst_backup")
                if op == "cpy":
                    if dst.exists():
                        if dst.is_dir():
                            shutil.rmtree(str(dst))
                        else:
                            dst.unlink()
                    if dst_backup:
                        UndoManager.safe_move(Path(dst_backup), dst)
                elif op == "move":
                    # move back
                    if dst.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(dst), str(src))
                    if dst_backup:
                        UndoManager.safe_move(Path(dst_backup), dst)
            else:
                print(f"⚠ Unsupported undo operation: {op}")
                set_last_exit(1)
                return

            print("✓ Undone")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Undo failed: {e}")
            set_last_exit(1)

    @staticmethod
    def redo(args: List[str]) -> None:
        """Redo last undone operation"""
        if not State.redo_stack:
            print("⚠ Nothing to redo")
            set_last_exit(1)
            return

        action = State.redo_stack.pop()
        State.undo_stack.append(action)

        op = action.get("op")
        try:
            if op == "mk_file":
                path = Path(action["path"])
                existed = action.get("existed", False)
                # we can't perfectly redo content without stored content; best-effort create empty
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_text("", encoding="utf-8")
            elif op == "mk_dir":
                path = Path(action["path"])
                path.mkdir(parents=True, exist_ok=True)
            elif op == "dlt":
                path = Path(action["path"])
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(str(path))
                    else:
                        path.unlink()
            elif op == "cpy":
                src = Path(action["src"])
                dst = Path(action["dst"])
                if src.exists():
                    if src.is_dir():
                        shutil.copytree(str(src), str(dst))
                    else:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src), str(dst))
            elif op == "move":
                src = Path(action["src"])
                dst = Path(action["dst"])
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
            else:
                print(f"⚠ Unsupported redo operation: {op}")
                set_last_exit(1)
                return

            print("✓ Redone")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Redo failed: {e}")
            set_last_exit(1)

    @staticmethod
    def pin(args: List[str]) -> None:
        """Install plugin from path (copy to plugin dir)"""
        if not args:
            print(Commands.HELP_TEXT["pin"])
            set_last_exit(1)
            return

        src = resolve_path(args[0])
        if not src.exists():
            print(f"⚠ Plugin not found: {src}")
            set_last_exit(1)
            return

        dst = Config.PLUGIN_DIR / src.name
        try:
            if src.is_dir():
                if dst.exists():
                    print("⚠ Plugin already installed")
                    set_last_exit(1)
                    return
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
            State.plugin_registry[src.name] = str(dst)
            print(f"✓ Plugin installed: {src.name}")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Plugin install failed: {e}")
            set_last_exit(1)

    @staticmethod
    def prv(args: List[str]) -> None:
        """Remove plugin"""
        if not args:
            print(Commands.HELP_TEXT["prv"])
            set_last_exit(1)
            return

        name = args[0]
        dst = Config.PLUGIN_DIR / name
        if not dst.exists():
            print(f"⚠ Plugin not installed: {name}")
            set_last_exit(1)
            return

        try:
            if dst.is_dir():
                shutil.rmtree(str(dst))
            else:
                dst.unlink()
            State.plugin_registry.pop(name, None)
            print(f"✓ Plugin removed: {name}")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Plugin remove failed: {e}")
            set_last_exit(1)

    @staticmethod
    def gp(args: List[str]) -> None:
        """Graphical prompt with message and two fields (like in the image)"""
        if len(args) < 3:
            print("Usage: gp <message> <field1_label> <field2_label>")
            print("Example: gp \"Please enter your details:\" \"Name\" \"Email\"")
            set_last_exit(1)
            return
        
        # Extract message and field labels
        message = args[0]
        field1_label = args[1]
        field2_label = args[2]
        
        # Remove quotes if present
        if message.startswith('"') and message.endswith('"'):
            message = message[1:-1]
        elif message.startswith("'") and message.endswith("'"):
            message = message[1:-1]
        
        if field1_label.startswith('"') and field1_label.endswith('"'):
            field1_label = field1_label[1:-1]
        elif field1_label.startswith("'") and field1_label.endswith("'"):
            field1_label = field1_label[1:-1]
        
        if field2_label.startswith('"') and field2_label.endswith('"'):
            field2_label = field2_label[1:-1]
        elif field2_label.startswith("'") and field2_label.endswith("'"):
            field2_label = field2_label[1:-1]
        
        # Expand variables in the text
        message = TextProcessor.expand_vars_in_string(message)
        field1_label = TextProcessor.expand_vars_in_string(field1_label)
        field2_label = TextProcessor.expand_vars_in_string(field2_label)
        
        # Create the formatted box
        print()
        print("+" + "-" * 38 + "+")
        
        # Message line (centered)
        if message:
            print("|" + " " * 38 + "|")
            message_padding = 38 - len(message) - 2
            if message_padding < 0:
                # Message is too long, split it
                words = message.split()
                lines = []
                current_line = ""
                
                for word in words:
                    if len(current_line) + len(word) + 1 <= 36:
                        current_line += (" " if current_line else "") + word
                    else:
                        lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                
                for line in lines:
                    padding = 38 - len(line) - 2
                    left_pad = padding // 2
                    right_pad = padding - left_pad
                    print("|" + " " * left_pad + line + " " * right_pad + "|")
            else:
                left_pad = message_padding // 2
                right_pad = message_padding - left_pad
                print("|" + " " * left_pad + message + " " * right_pad + "|")
        
        # Separator line
        print("|" + " " * 38 + "|")
        print("|" + "-" * 38 + "|")
        
        # First field
        print("|" + " " * 38 + "|")
        field1_display = f"| {field1_label}:"
        print(field1_display + " " * (38 - len(field1_display)) + "|")
        
        # Second field
        print("|" + " " * 38 + "|")
        field2_display = f"| {field2_label}:"
        print(field2_display + " " * (38 - len(field2_display)) + "|")
        
        print("|" + " " * 38 + "|")
        print("+" + "-" * 38 + "+")
        print()
        
        # Get user input for both fields
        try:
            field1_input = input(f"{field1_label}: ").strip()
            field2_input = input(f"{field2_label}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            set_last_exit(1)
            return
        
        # Store in variables (using field labels as variable names, sanitized)
        var1_name = field1_label.lower().replace(" ", "_").replace(":", "")
        var2_name = field2_label.lower().replace(" ", "_").replace(":", "")
        
        State.variables[var1_name] = field1_input
        State.variables[var2_name] = field2_input
        
        print(f"✓ Saved: {var1_name} = '{field1_input}', {var2_name} = '{field2_input}'")
        set_last_exit(0)

    @staticmethod
    def ide(args: List[str]) -> None:
        """Open a simple terminal-based text editor for Sigil code"""
        # Default filename or use provided argument
        if args:
            filename = args[0]
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]
            elif filename.startswith("'") and filename.endswith("'"):
                filename = filename[1:-1]
        else:
            # Prompt for filename
            try:
                filename = input("Enter filename: ").strip()
                if not filename:
                    print("⚠ No filename provided")
                    set_last_exit(1)
                    return
            except (EOFError, KeyboardInterrupt):
                print()
                set_last_exit(1)
                return
        
        # Ensure .sig extension
        if not filename.endswith('.sig'):
            filename += '.sig'
        
        filepath = resolve_path(filename)
        
        # Load existing content if file exists
        content_lines = []
        if filepath.exists():
            try:
                content = filepath.read_text(encoding='utf-8')
                content_lines = content.splitlines()
                print(f"📄 Loaded existing file: {filepath}")
            except Exception as e:
                print(f"⚠ Error loading file: {e}")
                content_lines = []
        else:
            print(f"📝 Creating new file: {filepath}")
        
        # Editor state
        cursor_pos = 0  # Line number (0-indexed)
        cursor_col = 0  # Column position
        editing = True
        modified = False
        scroll_offset = 0
        status_msg = ""
        status_msg_time = 0
        
        def clear_screen():
            """Clear terminal screen"""
            os.system('cls' if os.name == 'nt' else 'clear')
        
        def display_editor():
            """Display editor interface"""
            nonlocal scroll_offset, status_msg, status_msg_time
            
            clear_screen()
            
            # Editor header
            print(f"Sigil IDE - {filepath.name} {'[MODIFIED]' if modified else ''}")
            print("=" * 80)
            print("Commands: Ctrl+S=Save, Ctrl+R=Run, Ctrl+Q=Quit, Ctrl+O=Open, Ctrl+F=Find")
            print("-" * 80)
            
            # Calculate visible lines (terminal height minus status area)
            term_height = 24  # Default
            visible_lines = term_height - 8
            
            # Adjust scroll offset if cursor is outside visible area
            if cursor_pos < scroll_offset:
                scroll_offset = cursor_pos
            elif cursor_pos >= scroll_offset + visible_lines:
                scroll_offset = cursor_pos - visible_lines + 1
            
            # Display lines
            start_line = scroll_offset
            end_line = min(start_line + visible_lines, len(content_lines))
            
            for i in range(start_line, end_line):
                line_num = i + 1
                line_prefix = f"{line_num:4d} | "
                
                # Show cursor on current line
                if i == cursor_pos:
                    # Build line with cursor marker
                    line_content = content_lines[i] if i < len(content_lines) else ""
                    
                    # Handle empty line
                    if not line_content:
                        print(f"> {line_prefix} \033[7m \033[0m")  # Inverted space for cursor
                    else:
                        # Truncate long lines
                        display_line = line_content[:76]
                        if cursor_col >= len(line_content):
                            # Cursor at end
                            print(f"> {line_prefix}{display_line}\033[7m \033[0m")
                        else:
                            # Cursor in middle
                            before_cursor = display_line[:cursor_col]
                            at_cursor = display_line[cursor_col] if cursor_col < len(display_line) else " "
                            after_cursor = display_line[cursor_col + 1:] if cursor_col + 1 < len(display_line) else ""
                            print(f"> {line_prefix}{before_cursor}\033[7m{at_cursor}\033[0m{after_cursor}")
                else:
                    # Normal line display
                    line_content = content_lines[i] if i < len(content_lines) else ""
                    display_line = line_content[:76]  # Truncate for display
                    print(f"  {line_prefix}{display_line}")
            
            # Fill remaining lines with tildes
            for _ in range(end_line - start_line, visible_lines):
                print("~")
            
            print("-" * 80)
            
            # Status line
            if status_msg and time.time() - status_msg_time < 3:
                print(f"\033[93m{status_msg}\033[0m")  # Yellow
            else:
                status_msg = ""
            
            print(f"Line {cursor_pos + 1}/{len(content_lines)}, Col {cursor_col + 1} | Modified: {modified}")
            print("_" * 80)
        
        def set_status(message: str):
            """Set status message"""
            nonlocal status_msg, status_msg_time
            status_msg = message
            status_msg_time = time.time()
        
        def save_file():
            """Save current content to file"""
            nonlocal modified
            try:
                # Ensure parent directory exists
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                # Write content
                filepath.write_text('\n'.join(content_lines), encoding='utf-8')
                modified = False
                set_status(f"✓ Saved to {filepath}")
                return True
            except Exception as e:
                set_status(f"✗ Save failed: {e}")
                return False
        
        def run_script():
            """Run the current script"""
            nonlocal modified, filepath, content_lines
            
            if modified:
                if not confirm_destructive_action("save before running (unsaved changes will be lost)"):
                    set_status("Run cancelled")
                    return
            
            # Save if needed
            if modified:
                save_file()
            
            set_status("Running script...")
            display_editor()
            
            try:
                # Run the script
                content = '\n'.join(content_lines)
                lines = content.splitlines()
                
                # Save context
                prev_file = State.script_file
                prev_dir = State.script_dir
                prev_args = State.script_args
                
                try:
                    State.script_file = str(filepath)
                    State.script_dir = str(filepath.parent)
                    State.script_args = []
                    
                    print("\n" + "="*80)
                    print(f"Running: {filepath.name}")
                    print("="*80 + "\n")
                    
                    Interpreter.run_lines(lines)
                finally:
                    State.script_file = prev_file
                    State.script_dir = prev_dir
                    State.script_args = prev_args
                
                wait_for_any_key("\nPress any key to return to editor...")
            except Exception as e:
                set_status(f"✗ Run failed: {e}")
                wait_for_any_key("Press any key to continue...")
        
        def handle_input():
            """Handle keyboard input"""
            nonlocal cursor_pos, cursor_col, content_lines, editing, modified, filepath, scroll_offset
            
            try:
                # For cross-platform key reading
                if HAS_MSVCRT:
                    # Windows
                    ch = msvcrt.getch()
                    if ch == b'\xe0':  # Extended key (arrows, etc.)
                        ch2 = msvcrt.getch()
                        if ch2 == b'H':  # Up arrow
                            cursor_pos = max(0, cursor_pos - 1)
                            cursor_col = min(cursor_col, len(content_lines[cursor_pos]) if cursor_pos < len(content_lines) else 0)
                        elif ch2 == b'P':  # Down arrow
                            cursor_pos = min(len(content_lines), cursor_pos + 1)
                            cursor_col = min(cursor_col, len(content_lines[cursor_pos]) if cursor_pos < len(content_lines) else 0)
                        elif ch2 == b'K':  # Left arrow
                            cursor_col = max(0, cursor_col - 1)
                        elif ch2 == b'M':  # Right arrow
                            current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                            cursor_col = min(len(current_line), cursor_col + 1)
                        return
                    elif ch == b'\r':  # Enter/Return
                        # Insert new line
                        current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                        before_cursor = current_line[:cursor_col]
                        after_cursor = current_line[cursor_col:]
                        
                        if cursor_pos >= len(content_lines):
                            content_lines.append(before_cursor)
                            content_lines.append(after_cursor)
                        else:
                            content_lines[cursor_pos] = before_cursor
                            content_lines.insert(cursor_pos + 1, after_cursor)
                        
                        cursor_pos += 1
                        cursor_col = 0
                        modified = True
                    elif ch == b'\x08' or ch == b'\x7f':  # Backspace
                        if cursor_col > 0:
                            # Delete character before cursor
                            current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                            content_lines[cursor_pos] = current_line[:cursor_col-1] + current_line[cursor_col:]
                            cursor_col -= 1
                            modified = True
                        elif cursor_pos > 0:
                            # Merge with previous line
                            prev_line = content_lines[cursor_pos - 1]
                            current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                            content_lines[cursor_pos - 1] = prev_line + current_line
                            del content_lines[cursor_pos]
                            cursor_pos -= 1
                            cursor_col = len(prev_line)
                            modified = True
                    elif ch == b'\x1b':  # Escape
                        # Check for Ctrl+ combinations
                        try:
                            ch2 = msvcrt.getch(timeout=0.1)
                            if ch2 == b'\x00':
                                ch3 = msvcrt.getch(timeout=0.1)
                                # Handle function keys if needed
                                pass
                        except:
                            pass
                    else:
                        # Regular character
                        char = ch.decode('utf-8', errors='ignore')
                        
                        # Check for Ctrl+key combinations
                        if ch == b'\x13':  # Ctrl+S (Save)
                            save_file()
                        elif ch == b'\x12':  # Ctrl+R (Run)
                            run_script()
                        elif ch == b'\x11':  # Ctrl+Q (Quit)
                            if modified:
                                if confirm_destructive_action("quit without saving"):
                                    editing = False
                            else:
                                editing = False
                        elif ch == b'\x0f':  # Ctrl+O (Open)
                            try:
                                termios_available = HAS_UNIX_TERM
                                if termios_available:
                                    fd = sys.stdin.fileno()
                                    old_settings = termios.tcgetattr(fd)
                                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                                
                                new_file = input("Open file: ").strip()
                                
                                if termios_available:
                                    tty.setraw(fd)
                                
                                if new_file:
                                    # Switch to new file
                                    filepath = resolve_path(new_file)
                                    if filepath.exists():
                                        content = filepath.read_text(encoding='utf-8')
                                        content_lines = content.splitlines()
                                        cursor_pos = 0
                                        cursor_col = 0
                                        scroll_offset = 0
                                        modified = False
                                        set_status(f"✓ Opened {filepath.name}")
                                    else:
                                        set_status(f"✗ File not found: {new_file}")
                            except Exception as e:
                                set_status(f"Error: {e}")
                        elif ch == b'\x06':  # Ctrl+F (Find)
                            try:
                                termios_available = HAS_UNIX_TERM
                                if termios_available:
                                    fd = sys.stdin.fileno()
                                    old_settings = termios.tcgetattr(fd)
                                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                                
                                search_term = input("Find: ").strip()
                                
                                if termios_available:
                                    tty.setraw(fd)
                                
                                if search_term:
                                    found = False
                                    for i in range(cursor_pos + 1, len(content_lines)):
                                        if search_term in content_lines[i]:
                                            cursor_pos = i
                                            cursor_col = content_lines[i].find(search_term)
                                            found = True
                                            break
                                    if not found:
                                        set_status(f"✗ '{search_term}' not found")
                            except Exception as e:
                                set_status(f"Error: {e}")
                        else:
                            # Insert character
                            if cursor_pos >= len(content_lines):
                                content_lines.append(char)
                            else:
                                current_line = content_lines[cursor_pos]
                                content_lines[cursor_pos] = current_line[:cursor_col] + char + current_line[cursor_col:]
                            cursor_col += 1
                            modified = True
                
                elif HAS_UNIX_TERM:
                    # Unix/Linux - simplified implementation
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        ch = sys.stdin.read(1)
                        
                        if ch == '\x1b':  # Escape sequence
                            # Check for arrow keys
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                ch3 = sys.stdin.read(1)
                                if ch3 == 'A':  # Up
                                    cursor_pos = max(0, cursor_pos - 1)
                                    cursor_col = min(cursor_col, len(content_lines[cursor_pos]) if cursor_pos < len(content_lines) else 0)
                                elif ch3 == 'B':  # Down
                                    cursor_pos = min(len(content_lines), cursor_pos + 1)
                                    cursor_col = min(cursor_col, len(content_lines[cursor_pos]) if cursor_pos < len(content_lines) else 0)
                                elif ch3 == 'C':  # Right
                                    current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                                    cursor_col = min(len(current_line), cursor_col + 1)
                                elif ch3 == 'D':  # Left
                                    cursor_col = max(0, cursor_col - 1)
                        elif ch == '\r' or ch == '\n':  # Enter
                            current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                            before_cursor = current_line[:cursor_col]
                            after_cursor = current_line[cursor_col:]
                            
                            if cursor_pos >= len(content_lines):
                                content_lines.append(before_cursor)
                                content_lines.append(after_cursor)
                            else:
                                content_lines[cursor_pos] = before_cursor
                                content_lines.insert(cursor_pos + 1, after_cursor)
                            
                            cursor_pos += 1
                            cursor_col = 0
                            modified = True
                        elif ch == '\x7f' or ch == '\x08':  # Backspace
                            if cursor_col > 0:
                                current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                                content_lines[cursor_pos] = current_line[:cursor_col-1] + current_line[cursor_col:]
                                cursor_col -= 1
                                modified = True
                            elif cursor_pos > 0:
                                prev_line = content_lines[cursor_pos - 1]
                                current_line = content_lines[cursor_pos] if cursor_pos < len(content_lines) else ""
                                content_lines[cursor_pos - 1] = prev_line + current_line
                                del content_lines[cursor_pos]
                                cursor_pos -= 1
                                cursor_col = len(prev_line)
                                modified = True
                        elif ch == '\x13':  # Ctrl+S
                            save_file()
                        elif ch == '\x12':  # Ctrl+R
                            run_script()
                        elif ch == '\x11':  # Ctrl+Q
                            if modified:
                                if confirm_destructive_action("quit without saving"):
                                    editing = False
                            else:
                                editing = False
                        elif ch == '\x0f':  # Ctrl+O
                            try:
                                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                                new_file = input("Open file: ").strip()
                                tty.setraw(fd)
                                if new_file:
                                    filepath = resolve_path(new_file)
                                    if filepath.exists():
                                        content = filepath.read_text(encoding='utf-8')
                                        content_lines = content.splitlines()
                                        cursor_pos = 0
                                        cursor_col = 0
                                        scroll_offset = 0
                                        modified = False
                                        set_status(f"✓ Opened {filepath.name}")
                                    else:
                                        set_status(f"✗ File not found: {new_file}")
                            except Exception as e:
                                set_status(f"Error: {e}")
                                tty.setraw(fd)
                        elif ch == '\x06':  # Ctrl+F
                            try:
                                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                                search_term = input("Find: ").strip()
                                tty.setraw(fd)
                                if search_term:
                                    found = False
                                    for i in range(cursor_pos + 1, len(content_lines)):
                                        if search_term in content_lines[i]:
                                            cursor_pos = i
                                            cursor_col = content_lines[i].find(search_term)
                                            found = True
                                            break
                                    if not found:
                                        set_status(f"✗ '{search_term}' not found")
                            except Exception as e:
                                set_status(f"Error: {e}")
                                tty.setraw(fd)
                        else:
                            # Insert character
                            if cursor_pos >= len(content_lines):
                                content_lines.append(ch)
                            else:
                                current_line = content_lines[cursor_pos]
                                content_lines[cursor_pos] = current_line[:cursor_col] + ch + current_line[cursor_col:]
                            cursor_col += 1
                            modified = True
                            
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
                else:
                    # Fallback: simple line-based editor
                    set_status(f"Advanced editor not available on this platform")
                    time.sleep(2)
                    editing = False
                    
            except KeyboardInterrupt:
                # Handle Ctrl+C
                if confirm_destructive_action("exit editor"):
                    editing = False
            except Exception as e:
                set_status(f"Input error: {e}")
        
        # Main editor loop
        try:
            while editing:
                display_editor()
                handle_input()
            
            # Save on exit if modified
            if modified:
                if confirm_destructive_action("save before exiting"):
                    save_file()
            
            print(f"\nExited editor. File: {filepath}")
            set_last_exit(0)
            
        except Exception as e:
            print(f"\n⚠ Editor error: {e}")
            set_last_exit(1)

    @staticmethod
    def case(args: List[str]) -> None:
        """Case is implemented in interpreter control flow; this function is present for completeness."""
        print("⚠ 'case' should be used as a block and is handled by the interpreter.")
        set_last_exit(1)

    @staticmethod
    def exit_cmd(args: List[str]) -> None:
        """Exit shell"""
        code = 0
        if args:
            try:
                code = int(args[0])
            except (ValueError, TypeError):
                code = 1

        set_last_exit(code)
        raise SystemExit(code)

    @staticmethod
    def sdow(args: List[str]) -> None:
        """Shutdown computer with confirmation"""
        Commands.shutdown(args)

    @staticmethod
    def shutdown(args: List[str]) -> None:
        """Shutdown computer with confirmation"""
        # Confirm destructive action
        if not confirm_destructive_action("shutdown"):
            print("✗ Shutdown cancelled")
            set_last_exit(1)
            return

        try:
            print("🔌 Shutting down system...")
            if os.name == "nt":
                # Windows
                subprocess.run(["shutdown", "/s", "/t", "60", "/c", "Sigil initiated shutdown"])
            elif sys.platform == "darwin":
                # macOS
                subprocess.run(["sudo", "shutdown", "-h", "+1"])
            else:
                # Linux/Unix
                subprocess.run(["sudo", "shutdown", "-h", "+1"])
            
            print("✓ Shutdown initiated (60 seconds)")
            set_last_exit(0)
        except Exception as e:
            print(f"⚠ Shutdown failed: {e}")
            set_last_exit(1)

    @staticmethod
    def brk(args: List[str]) -> None:
        """Break from loop/case by raising BreakException"""
        raise BreakException()

# Command registry
COMMAND_REGISTRY = {
    "help": Commands.help,
    "mk": Commands.mk,
    "cpy": Commands.cpy,
    "dlt": Commands.dlt,
    "move": Commands.move,
    "cd": Commands.cd,
    "pwd": Commands.pwd,
    "dirlook": Commands.dirlook,
    "opnlnk": Commands.opnlnk,
    "opn": Commands.opn,
    "ex": Commands.ex,
    "task": Commands.task,
    "kill": Commands.kill,
    "clo": Commands.clo,
    "say": Commands.say,
    "add": Commands.add,
    "sub": Commands.sub,
    "mul": Commands.mul,
    "div": Commands.div,
    "alia": Commands.alia,
    "unalia": Commands.unalia,
    "let": Commands.let,
    "var": Commands.var,
    "unset": Commands.unset,
    "export": Commands.export,
    "ask": Commands.ask,
    "wait": Commands.wait,
    "pse": Commands.pse,
    "pause": Commands.pse,
    "sleep": Commands.wait,
    "exists": Commands.exists,
    "arg": Commands.arg,
    "prof": Commands.prof,
    "run": Commands.run,
    "inc": Commands.inc,
    "include": Commands.inc,
    "wrt": Commands.wrt,
    "undo": Commands.undo,
    "redo": Commands.redo,
    "pin": Commands.pin,
    "prv": Commands.prv,
    "gp": Commands.gp,
    "ide": Commands.ide,
    "edit": Commands.ide,
    "case": Commands.case,
    "exit": Commands.exit_cmd,
    "quit": Commands.exit_cmd,
    "ps": ShellRunner.powershell,
    "cmd": ShellRunner.cmd,
    "cp": ShellRunner.cmd,
    "sh": ShellRunner.sh,
    "brk": Commands.brk,
    "sdow": Commands.sdow,
    "shutdown": Commands.shutdown,
    "log": Commands.log,
    "pth": PthCommands.pth,
    "update": UpdateChecker.update_command,
    "check-updates": UpdateChecker.update_command,
    "net": NetCommands.net,
    "zip": ArchiveCommands.zip,
    "uzip": ArchiveCommands.uzip,
    "unzip": ArchiveCommands.unzip,
    "sns": ScriptCommands.sns,
    "exec": ScriptCommands.sns,
    "gbc": GlobalCleaner.gbc,
    "clean": GlobalCleaner.gbc,
    "reset": GlobalCleaner.gbc,
    "cnf": GlobalCleaner.cnf,
    "fnc": FunctionCommands.fnc,
    "clf": FunctionCommands.clf,
    "fnlist": FunctionCommands.fnlist,
    "fnrm": FunctionCommands.fnrm,
}

# ============================================================================
# INTERPRETER
# ============================================================================

class Interpreter:
    """Script interpreter with control flow"""

    LABEL_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):')

    @staticmethod
    def _build_label_map(lines: List[str]) -> Dict[str, int]:
        """Scan lines for labels of form `name:` and return mapping to line index to jump to."""
        labels: Dict[str, int] = {}
        for idx, raw in enumerate(lines):
            line = raw.strip()
            m = Interpreter.LABEL_RE.match(line)
            if m:
                name = m.group(1)
                # label points to next line (so a goto jumps to the first line after label)
                labels[name] = idx + 1
        return labels

    @staticmethod
    def _execute_line(raw_line: str, from_script: bool = False) -> None:
        """Execute a single (non-empty) line after expansion."""
        # Expand aliases and variables before tokenizing for actual execution
        expanded_line = TextProcessor.expand_aliases_and_vars(raw_line)
        tokens = TextProcessor.tokenize(expanded_line)
        if not tokens:
            return

        cmd = tokens[0]
        args = tokens[1:]

        # Skip logging for certain commands
        skip_logging_commands = ['log', 'undo', 'redo', 'pse', 'wait']
        
        # direct registry command
        handler = COMMAND_REGISTRY.get(cmd)
        if handler:
            try:
                handler(args)
                # Log the execution
                if cmd not in skip_logging_commands and not State.loading_rc:
                    ExecutionLogger.log_execution(
                        "REPL" if not from_script else "CMD",
                        raw_line.strip(),
                        State.variables.get('last', 0)
                    )
            except SystemExit as e:
                # Log before exiting
                if cmd not in skip_logging_commands and not State.loading_rc:
                    ExecutionLogger.log_execution(
                        "REPL" if not from_script else "CMD",
                        raw_line.strip(),
                        e.code if isinstance(e.code, int) else 0
                    )
                raise
            except Exception as e:
                # Log even on error
                if cmd not in skip_logging_commands and not State.loading_rc:
                    ExecutionLogger.log_execution(
                        "REPL" if not from_script else "CMD",
                        raw_line.strip(),
                        State.variables.get('last', 1)
                    )
                raise
            return

        # fallback: try running as external command
        try:
            ShellRunner.run_and_print([cmd] + args)
            # Log external command execution
            if not State.loading_rc:
                ExecutionLogger.log_execution(
                    "EXT" if not from_script else "CMD",
                    raw_line.strip(),
                    State.variables.get('last', 0)
                )
        except Exception as e:
            print(f"⚠ Unknown command or failed to run: {cmd} ({e})")
            set_last_exit(1)
            # Log failed command
            if not State.loading_rc:
                ExecutionLogger.log_execution(
                    "ERR" if not from_script else "CMD",
                    raw_line.strip(),
                    1
                )

    @staticmethod
    def _collect_block(lines: List[str], start_index: int, start_kw: str, end_kw: str) -> Tuple[List[str], int]:
        """Collect block lines from start_index+1 until matching end_kw, handling nesting of same block type."""
        block = []
        depth = 0
        i = start_index + 1
        while i < len(lines):
            l = lines[i].strip()
            # detect nested start
            if l.startswith(start_kw):
                depth += 1
                block.append(lines[i])
            elif l == end_kw:
                if depth == 0:
                    # found matching end for this start
                    return block, i
                else:
                    depth -= 1
                    block.append(lines[i])
            else:
                block.append(lines[i])
            i += 1
        # if we get here, matching end not found
        raise SigilError(f"Missing {end_kw} for {start_kw} starting at line {start_index+1}")

    @staticmethod
    def run_lines(lines: List[str], from_rc: bool = False, script_name: str = "") -> None:
        """Run multiple lines with block support"""
        # Strip comments and keep original line structure
        in_block_comment = False
        cleaned_lines: List[str] = []
        for raw_line in lines:
            line = raw_line.rstrip("\n")
            stripped, in_block_comment = TextProcessor.strip_comments(line, in_block_comment)
            cleaned_lines.append(stripped)

        label_map = Interpreter._build_label_map(cleaned_lines)

        index = 0
        while index < len(cleaned_lines):
            raw_line = cleaned_lines[index]
            line = raw_line.strip()

            # Skip empty lines or label definitions
            if not line:
                index += 1
                continue
            if Interpreter.LABEL_RE.match(line):
                index += 1
                continue

            # Tokenize for control keywords
            tokens = TextProcessor.tokenize(line)
            if not tokens:
                index += 1
                continue

            cmd = tokens[0]

            # GOTO handling
            if cmd == "goto":
                if len(tokens) >= 2:
                    label = tokens[1]
                    if label in label_map:
                        index = label_map[label]
                        continue
                    else:
                        print(f"⚠ Label not found: {label}")
                        set_last_exit(1)
                else:
                    print("⚠ goto requires a label")
                    set_last_exit(1)
                index += 1
                continue

            # RPT handling (inline or block)
            if cmd == "rpt":
                # Inline form: rpt <count|inf> <command...>
                if len(tokens) >= 3:
                    count_tok = tokens[1]
                    try:
                        if count_tok == "inf":
                            count = None
                        else:
                            count = int(count_tok)
                    except Exception:
                        print("⚠ Invalid rpt count")
                        set_last_exit(1)
                        index += 1
                        continue

                    # inline command to repeat
                    inline_cmd = " ".join(tokens[2:])
                    # FIX: Create block_lines from inline command
                    block_lines = [inline_cmd]
                    try:
                        if count is None:
                            # infinite until brk or Ctrl-C
                            while True:
                                try:
                                    Interpreter.run_lines(block_lines, from_rc, script_name)
                                except BreakException:
                                    break
                        else:
                            for _ in range(count):
                                try:
                                    Interpreter.run_lines(block_lines, from_rc, script_name)
                                except BreakException:
                                    break
                        set_last_exit(0)
                    except KeyboardInterrupt:
                        set_last_exit(130)
                    index += 1
                    continue

                # Block form: rpt <count|inf> ... endrpt
                if len(tokens) >= 2:
                    count_tok = tokens[1]
                    try:
                        if count_tok == "inf":
                            count = None
                        else:
                            count = int(count_tok)
                    except Exception:
                        print("⚠ Invalid rpt count")
                        set_last_exit(1)
                        index += 1
                        continue

                    # collect block lines
                    try:
                        block_lines, end_idx = Interpreter._collect_block(cleaned_lines, index, "rpt", "endrpt")
                    except SigilError as e:
                        print(f"⚠ {e}")
                        set_last_exit(1)
                        return

                    try:
                        if count is None:
                            # infinite
                            while True:
                                try:
                                    Interpreter.run_lines(block_lines)
                                except BreakException:
                                    break
                        else:
                            for _ in range(count):
                                try:
                                    Interpreter.run_lines(block_lines)
                                except BreakException:
                                    break
                        set_last_exit(0)
                    except KeyboardInterrupt:
                        set_last_exit(130)

                    # jump past endrpt
                    index = end_idx + 1
                    continue

                # malformed rpt
                print("⚠ Malformed rpt")
                set_last_exit(1)
                index += 1
                continue

            # CASE handling
            if cmd == "case":
                if len(tokens) < 2:
                    print("⚠ case requires a variable")
                    set_last_exit(1)
                    index += 1
                    continue

                var_name = tokens[1]
                var_value = str(State.variables.get(var_name, os.environ.get(var_name, "")))

                # collect case block
                try:
                    block_lines, end_idx = Interpreter._collect_block(cleaned_lines, index, "case", "endcase")
                except SigilError as e:
                    print(f"⚠ {e}")
                    set_last_exit(1)
                    return

                # parse when / else blocks
                chosen_block: List[str] = []
                current_when_values = []
                collecting = False
                else_block: List[str] = []
                i = 0
                while i < len(block_lines):
                    l = block_lines[i].strip()
                    if l.startswith("when "):
                        # start of when
                        collecting = True
                        # parse values
                        vals = l[5:].split()
                        current_when_values = vals
                        # collect lines until next when/else/endcase
                        j = i + 1
                        buff = []
                        while j < len(block_lines):
                            lj = block_lines[j].strip()
                            if lj.startswith("when ") or lj == "else":
                                break
                            buff.append(block_lines[j])
                            j += 1
                        # if any match, choose this buff
                        if var_value in current_when_values:
                            chosen_block = buff
                            break
                        i = j
                        continue
                    elif l == "else":
                        # collect else block
                        j = i + 1
                        buff = []
                        while j < len(block_lines):
                            buff.append(block_lines[j])
                            j += 1
                        else_block = buff
                        break
                    else:
                        i += 1

                if not chosen_block and else_block:
                    chosen_block = else_block

                if chosen_block:
                    try:
                        Interpreter.run_lines(chosen_block)
                        set_last_exit(0)
                    except BreakException:
                        # silently handle break
                        pass

                index = end_idx + 1
                continue

            # 'if' inline handling: if <cond> then <command>
            if cmd == "if":
                # minimal if implementation supporting: if <left> <op> <right> then <command...>
                # Example: if $x == 5 then say "yes"
                # Tokenization already performed, so tokens[1:] includes condition and then 'then'
                if "then" not in tokens:
                    print("⚠ Malformed if: missing 'then'")
                    set_last_exit(1)
                    index += 1
                    continue
                then_idx = tokens.index("then")
                cond_tokens = tokens[1:then_idx]
                cmd_tokens = tokens[then_idx + 1:]
                # Evaluate simple condition: left op right
                cond_ok = False
                try:
                    if len(cond_tokens) == 1:
                        left = TextProcessor.expand_vars_in_string(cond_tokens[0].strip('"'))
                        cond_ok = bool(left)
                    elif len(cond_tokens) >= 3:
                        left = TextProcessor.expand_vars_in_string(cond_tokens[0].strip('"'))
                        op = cond_tokens[1]
                        right = TextProcessor.expand_vars_in_string(" ".join(cond_tokens[2:]).strip('"'))
                        if op == "==" or op == "=":
                            cond_ok = str(left) == str(right)
                        elif op == "!=":
                            cond_ok = str(left) != str(right)
                        elif op in ("<", ">", "<=", ">="):
                            try:
                                cond_ok = float(left) if "." in str(left) else int(left)
                                right_n = float(right) if "." in str(right) else int(right)
                                if op == "<":
                                    cond_ok = cond_ok < right_n
                                elif op == ">":
                                    cond_ok = cond_ok > right_n
                                elif op == "<=":
                                    cond_ok = cond_ok <= right_n
                                elif op == ">=":
                                    cond_ok = cond_ok >= right_n
                            except Exception:
                                cond_ok = False
                        else:
                            cond_ok = False
                    else:
                        cond_ok = False
                except Exception:
                    cond_ok = False

                if cond_ok:
                    try:
                        Interpreter._execute_line(" ".join(cmd_tokens))
                    except BreakException:
                        raise
                index += 1
                continue

            # Handle brk spelled as command (so 'brk' on a line behaves like BreakException)
            if cmd == "brk":
                # 'brk' executed outside of loop => raise BreakException for caller to handle
                raise BreakException()

            # Regular command execution — may raise BreakException from inside subcommands
            try:
                Interpreter._execute_line(line, from_script=bool(script_name))
            except BreakException:
                # If brk encountered outside a rpt block, propagate upward
                raise
            except SystemExit:
                # pass through exits
                raise
            except Exception as e:
                # don't crash entire interpreter for a single command; report and continue
                print(f"⚠ Error executing line '{line}': {e}")
                set_last_exit(1)

            index += 1

# ============================================================================
# REPL / MAIN
# ============================================================================

def repl():
    """Simple interactive read-eval-print loop for Sigil with logging"""
    RCManager.load()
    print(f"Sigil {Config.VERSION} — Type 'help' for commands. Ctrl-D or 'exit' to quit.")
    
    # Check for updates on startup (once per session)
    try:
        # Run update check in background to not block startup
        import threading
        update_thread = threading.Thread(
            target=UpdateChecker.check_for_updates,
            kwargs={'silent': True, 'force_check': False},
            daemon=True
        )
        update_thread.start()
    except Exception:
        # If threading fails, just skip the update check
        pass
    
    # Log REPL start
    ExecutionLogger.log_execution("REPL", "REPL started", 0)
    
    try:
        while True:
            try:
                raw = input("> ")
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue

            stripped, _ = TextProcessor.strip_comments(raw, False)
            if not stripped or not stripped.strip():
                continue

            try:
                Interpreter.run_lines([stripped])
            except BreakException:
                continue
            except SystemExit as e:
                # Log REPL exit
                exit_code = e.code if isinstance(e.code, int) else 0
                ExecutionLogger.log_execution("REPL", "REPL exited", exit_code)
                code = exit_code
                RCManager.save()
                sys.exit(code)
            except Exception as e:
                print(f"⚠ Interpreter error: {e}")

    finally:
        try:
            RCManager.save()
            # Log REPL normal exit
            ExecutionLogger.log_execution("REPL", "REPL session ended", 0)
        except Exception:
            pass

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point that handles both script files and REPL mode"""
    # Load RC profile
    RCManager.load()
    
    # Check for updates on startup (only in interactive mode)
    if len(sys.argv) <= 1:  # Only in REPL mode, not when running scripts
        try:
            import threading
            update_thread = threading.Thread(
                target=UpdateChecker.check_for_updates,
                kwargs={'silent': True, 'force_check': False},
                daemon=True
            )
            update_thread.start()
        except Exception:
            pass
    
    # Check if we were given a script file as argument
    if len(sys.argv) > 1:
        # First argument is the .sig file
        script_file = sys.argv[1]
        
        # Verify it's a .sig file
        if not script_file.endswith('.sig'):
            print(f"⚠ Expected .sig file, got: {script_file}")
            sys.exit(1)
        
        if not os.path.exists(script_file):
            print(f"⚠ Script file not found: {script_file}")
            sys.exit(1)
        
        # Set script context
        script_path = Path(script_file).resolve()
        State.script_file = str(script_path)
        State.script_dir = str(script_path.parent)
        State.script_args = sys.argv[2:]  # Additional arguments
        
        # Change to script's directory
        original_dir = State.current_dir
        State.current_dir = script_path.parent
        
        try:
            # Log script execution start
            ExecutionLogger.log_execution("SCRIPT", str(script_path), 0)
            
            # Read and execute the script
            content = script_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            print(f"🔮 Running: {script_path.name}")
            print("=" * 60)
            
            Interpreter.run_lines(lines, script_name=str(script_path))
            
            print("=" * 60)
            exit_code = State.variables.get('last', 0)
            print(f"✓ Script completed. Exit code: {exit_code}")
            
            # Log script execution completion
            ExecutionLogger.log_execution("SCRIPT", f"{script_path} completed", exit_code)
            
            sys.exit(exit_code)
            
        except SystemExit as e:
            # Log script exit
            exit_code = e.code if isinstance(e.code, int) else 0
            ExecutionLogger.log_execution("SCRIPT", f"{script_path} exited", exit_code)
            sys.exit(exit_code)
        except Exception as e:
            print(f"⚠ Script execution failed: {e}")
            # Log script failure
            ExecutionLogger.log_execution("SCRIPT", f"{script_path} failed", 1)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            # Restore original directory
            State.current_dir = original_dir
            
    else:
        # No arguments, start interactive REPL
        repl()

if __name__ == "__main__":
    main()
