#!/usr/bin/env python3
r"""
Sigil IDE — PySide6 single-file application.

Patched to make Run reliable even for unsaved files, and to show process output.
"""

from __future__ import annotations

import os
import re
import sys
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QSize
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QSyntaxHighlighter,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# -------------------------
# Config
# -------------------------
SIGIL_EXE_CANDIDATES = [
    r"C:\Sigil\sigil.exe",
    "sigil",
]

SIGIL_CONFIG_DIR = Path(r"C:\Sigil")
DEFAULT_FONT_FAMILY = "Consolas" if os.name == "nt" else "DejaVu Sans Mono"

NEON_COLORS = {
    "background": "#0b0f14aa",
    "accent": "#8be9fd",
    "string": "#50fa7b",
    "number": "#f1fa8c",
    "keyword": "#ff79c6",
    "command": "#8be9fd",
    "variable": "#bd93f9",
    "comment": "#6272a4",
    "text": "#e6e6e6",
    "error": "#ff5555",
}

# -------------------------
# Syntax Highlighter
# -------------------------
class SigilHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.rules: list[tuple[re.Pattern, QTextCharFormat, int]] = []
        self._build_rules()

    @staticmethod
    def _format(color: str, *, bold=False, italic=False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        font = QFont()
        font.setBold(bold)
        font.setItalic(italic)
        fmt.setFont(font)
        return fmt

    def _add_rule(self, pattern: str, fmt: QTextCharFormat, flags=re.IGNORECASE, group: int = 0):
        self.rules.append((re.compile(pattern, flags), fmt, group))

    def _build_rules(self):
        self._add_rule(
            r"\b(mk|cpy|dlt|move|renm|cd|pwd|run|let|unset|var|if|fmt|schk)\b",
            self._format(NEON_COLORS["command"], bold=True),
        )
        self._add_rule(r'"([^"\\]|\\.)*"', self._format(NEON_COLORS["string"]))
        self._add_rule(r"\b\d+(\.\d+)?\b", self._format(NEON_COLORS["number"]))
        self._add_rule(r"\$[A-Za-z_]\w*", self._format(NEON_COLORS["variable"], bold=True))
        # avoid variable-width lookbehind by matching 'let NAME' and highlighting group 1
        self._add_rule(r"\blet\s+([A-Za-z_]\w*)", self._format(NEON_COLORS["variable"], bold=True), group=1)
        self._add_rule(r"//.*|#.*", self._format(NEON_COLORS["comment"]))
        self._add_rule(r"(==|!=|>=|<=|=|>|<|\+|\-|\*|/)", self._format(NEON_COLORS["accent"]))

    def highlightBlock(self, text: str):
        for regex, fmt, group in self.rules:
            for m in regex.finditer(text):
                if group and m.lastindex and group <= m.lastindex:
                    start, end = m.span(group)
                else:
                    start, end = m.span()
                if start >= 0 and end > start:
                    self.setFormat(start, end - start, fmt)


# -------------------------
# Main Window
# -------------------------
class SigilIDE(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sigil IDE — Neon Terminal")
        self.resize(1100, 700)

        self.current_file: Path | None = None
        self.process: QProcess | None = None
        self._temp_run_file: Path | None = None  # if we wrote a temp file for run

        self._build_ui()
        self._apply_theme()
        self._load_profiles()

    def _build_ui(self):
        toolbar = QToolBar()
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        self.act_new = QAction("New", self, shortcut=QKeySequence.New)
        self.act_open = QAction("Open", self, shortcut=QKeySequence.Open)
        self.act_save = QAction("Save", self, shortcut=QKeySequence.Save)
        self.act_save_as = QAction("Save As", self, shortcut="Ctrl+Shift+S")

        toolbar.addActions([self.act_new, self.act_open, self.act_save, self.act_save_as])
        toolbar.addSeparator()

        self.act_run = QAction("Run", self, shortcut="F5")
        self.act_stop = QAction("Stop", self)
        self.act_fmt = QAction("Format", self)
        self.act_schk = QAction("Syntax Check", self)

        toolbar.addActions([self.act_run, self.act_stop, self.act_fmt, self.act_schk])
        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Profile: "))
        self.profile_combo = QComboBox()
        toolbar.addWidget(self.profile_combo)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont(DEFAULT_FONT_FAMILY, 11))
        SigilHighlighter(self.editor.document())
        splitter.addWidget(self.editor)

        self.output = QTextEdit(readOnly=True)
        self.output.setFont(QFont(DEFAULT_FONT_FAMILY, 11))
        self.output.setFixedHeight(220)
        splitter.addWidget(self.output)

        bottom = QHBoxLayout()
        self.sigil_path_edit = QLineEdit()
        self.sigil_path_edit.setPlaceholderText(r"Sigil executable (optional) — falls back to C:\Sigil\sigil.exe or PATH")
        bottom.addWidget(self.sigil_path_edit)

        self.btn_choose_sigil = QPushButton("Choose Sigil EXE")
        self.btn_clear = QPushButton("Clear Output")
        bottom.addWidget(self.btn_choose_sigil)
        bottom.addWidget(self.btn_clear)

        layout.addLayout(bottom)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # wire actions
        self.act_new.triggered.connect(self.file_new)
        self.act_open.triggered.connect(self.file_open)
        self.act_save.triggered.connect(self.file_save)
        self.act_save_as.triggered.connect(self.file_save_as)
        self.act_run.triggered.connect(self.run_current)
        self.act_stop.triggered.connect(self.stop_current)
        self.act_fmt.triggered.connect(lambda: self._run_tool("fmt"))
        self.act_schk.triggered.connect(lambda: self._run_tool("schk"))
        self.btn_choose_sigil.clicked.connect(self.choose_sigil_path)
        self.btn_clear.clicked.connect(lambda: self.output.clear())

    def _apply_theme(self):
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {NEON_COLORS['background']};
            }}
            QToolBar {{
                background: rgba(6,8,10,0.35);
                border-bottom: 1px solid rgba(139,233,253,0.06);
            }}
            QToolButton {{
                color: {NEON_COLORS['text']};
                background: rgba(255,255,255,0.02);
                border-radius: 6px;
                padding: 6px 8px;
                margin: 2px;
            }}
            QToolButton:hover {{
                background: rgba(189,147,249,0.10);
            }}
            QPlainTextEdit, QTextEdit {{
                background: rgba(8,10,12,0.75);
                color: {NEON_COLORS['text']};
                padding: 6px;
            }}
            QPushButton {{
                background: rgba(189,147,249,0.06);
                color: {NEON_COLORS['text']};
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QLabel {{
                color: {NEON_COLORS['accent']};
            }}
            """
        )

    # -------------------------
    # File ops
    # -------------------------
    def file_new(self):
        if not self.maybe_save():
            return
        self.editor.clear()
        self.current_file = None
        self.setWindowTitle("Sigil IDE — Untitled")

    def file_open(self):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Sigil Files (*.sig *.txt);;All Files (*)")
        if path:
            self._load_file(Path(path))

    def file_save(self) -> bool:
        if self.current_file is None:
            return self.file_save_as()
        try:
            self.current_file.write_text(self.editor.toPlainText(), encoding="utf-8")
            self.editor.document().setModified(False)
            self.status.showMessage(f"Saved {self.current_file}", 3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False

    def file_save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Sigil Files (*.sig *.txt);;All Files (*)")
        if not path:
            return False
        self.current_file = Path(path)
        return self.file_save()

    def maybe_save(self) -> bool:
        if self.editor.document().isModified():
            resp = QMessageBox.question(self, "Save changes?", "Save changes before continuing?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if resp == QMessageBox.Yes:
                return self.file_save()
            if resp == QMessageBox.Cancel:
                return False
        return True

    def _load_file(self, path: Path):
        try:
            self.editor.setPlainText(path.read_text(encoding="utf-8"))
            self.current_file = path
            self.editor.document().setModified(False)
            self.setWindowTitle(f"Sigil IDE — {path.name}")
            self.status.showMessage(f"Loaded {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    # -------------------------
    # Profiles
    # -------------------------
    def _load_profiles(self):
        self.profile_combo.clear()
        self.profile_combo.addItem("default")
        try:
            if SIGIL_CONFIG_DIR.exists():
                for file in sorted(SIGIL_CONFIG_DIR.iterdir()):
                    if file.is_file() and file.name.startswith(".sigilrc."):
                        self.profile_combo.addItem(file.name.removeprefix(".sigilrc."))
            self.status.showMessage("Profiles loaded", 2000)
        except Exception as e:
            self.status.showMessage(f"Profile load error: {e}", 4000)

    # -------------------------
    # Sigil runtime helpers
    # -------------------------
    def find_sigil_exe(self) -> str | None:
        # explicit override
        path_text = self.sigil_path_edit.text().strip()
        if path_text:
            if Path(path_text).exists():
                return path_text
            # allow command name like "sigil"
            if shutil.which(path_text):
                return path_text
            return None
        # check candidates
        for cand in SIGIL_EXE_CANDIDATES:
            if Path(cand).exists():
                return str(Path(cand))
            if shutil.which(cand):
                return cand
        # not found
        return None

    def append_output(self, text: str, error: bool = False):
        color = NEON_COLORS["error"] if error else NEON_COLORS["text"]
        self.output.moveCursor(QTextCursor.End)
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.output.insertHtml(f'<pre style="color:{color}; margin:0;">{safe}</pre>')
        self.output.ensureCursorVisible()

    # -------------------------
    # Running scripts (QProcess)
    # -------------------------
    def run_current(self):
        # If unsaved/untitled, save editor contents to a temp file for running
        temp_used = False
        run_path = None

        if self.current_file is None:
            # create temp file
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".sig", prefix="sigil_run_")
            tf.write(self.editor.toPlainText().encode("utf-8"))
            tf.flush()
            tf.close()
            run_path = Path(tf.name)
            self._temp_run_file = run_path
            temp_used = True
            self.append_output(f"Saved editor to temporary file: {run_path}\n")
        else:
            # if modified, save current file first
            if self.editor.document().isModified():
                saved = self.file_save()
                if not saved:
                    return
            run_path = self.current_file

        exe = self.find_sigil_exe()
        if not exe:
            self.append_output("Sigil executable not found. Set path or install Sigil and/or provide path.\n", error=True)
            QMessageBox.critical(self, "Sigil not found", "Could not find sigil executable. Set path or install to C:\\Sigil\\sigil.exe or add 'sigil' to PATH.")
            # cleanup temp if used
            if temp_used and self._temp_run_file and self._temp_run_file.exists():
                try:
                    self._temp_run_file.unlink()
                except Exception:
                    pass
                self._temp_run_file = None
            return

        # clear output and show running header
        self.output.clear()
        self.append_output(f"Running: {exe} {run_path}\n")

        # prepare QProcess
        if self.process:
            # kill previous, just in case
            try:
                if self.process.state() == QProcess.Running:
                    self.process.kill()
            except Exception:
                pass
            self.process = None

        self.process = QProcess(self)
        self.process.setProgram(exe)
        self.process.setArguments([str(run_path)])

        # connect outputs
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.started.connect(lambda: self.status.showMessage("Process started", 2000))
        self.process.finished.connect(self._on_finished)

        try:
            self.process.start()
            started = self.process.waitForStarted(3000)
            if not started:
                self.append_output("Failed to start process.\n", error=True)
                QMessageBox.critical(self, "Run failed", "Process failed to start.")
                # cleanup temp file if created
                if temp_used and self._temp_run_file and self._temp_run_file.exists():
                    try:
                        self._temp_run_file.unlink()
                    except Exception:
                        pass
                    self._temp_run_file = None
        except Exception as e:
            self.append_output(f"Run exception: {e}\n", error=True)
            QMessageBox.critical(self, "Run failed", str(e))
            if temp_used and self._temp_run_file and self._temp_run_file.exists():
                try:
                    self._temp_run_file.unlink()
                except Exception:
                    pass
                self._temp_run_file = None

    def stop_current(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
            self.append_output("\nProcess killed by user\n", error=True)
            self.status.showMessage("Process killed", 2000)

    def _on_stdout(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode(errors="ignore")
        if data:
            self.append_output(data)

    def _on_stderr(self):
        if not self.process:
            return
        data = self.process.readAllStandardError().data().decode(errors="ignore")
        if data:
            self.append_output(data, error=True)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        self.append_output(f"\nProcess finished (exit={exit_code})\n")
        self.status.showMessage(f"Process finished (exit={exit_code})", 3000)
        # cleanup temp file if used
        if self._temp_run_file:
            try:
                self._temp_run_file.unlink()
            except Exception:
                pass
            self._temp_run_file = None
        self.process = None

    # -------------------------
    # Run fmt and schk using sigil runtime
    # -------------------------
    def _run_tool(self, verb: str):
        if self.current_file is None:
            QMessageBox.information(self, "No file", "Open or save a file first.")
            return
        exe = self.find_sigil_exe()
        if not exe:
            QMessageBox.critical(self, "Sigil not found", "Could not find sigil executable.")
            return
        self.output.clear()
        self.append_output(f"{verb} {self.current_file}\n")
        proc = QProcess(self)
        proc.setProgram(exe)
        proc.setArguments([verb, str(self.current_file)])
        proc.readyReadStandardOutput.connect(lambda: self.append_output(proc.readAllStandardOutput().data().decode(errors="ignore")))
        proc.readyReadStandardError.connect(lambda: self.append_output(proc.readAllStandardError().data().decode(errors="ignore"), True))
        proc.start()
        proc.waitForFinished()
        self.append_output(f"\n{verb} finished (exit={proc.exitCode()})\n")

    # -------------------------
    # Choose sigil exe path
    # -------------------------
    def choose_sigil_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Sigil executable", "", "Executable Files (*.exe);;All Files (*)")
        if path:
            self.sigil_path_edit.setText(path)

# -------------------------
# Run app
# -------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sigil IDE")
    win = SigilIDE()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
