#!/usr/bin/env python3

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDir
from PyQt6.QtGui import QFont, QGuiApplication, QFileSystemModel
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QHeaderView, QStatusBar, QSizePolicy,
    QLineEdit, QCompleter, QComboBox, QMenu
)

from Helpers import get_mount_total
from read_resolve import _read_mount_fstypes, _read_mount_table, resolve_mount_source
from scanner import human_size, dir_size, make_tree_item, ScanWorker , SortableTreeItem , DiskTree
from variable import _VIRTUAL_FS_TYPES, _UNIT_DIVISORS, _UNITS, COL_NAME, COL_BAR, COL_COPY, COL_DISK, COL_PCT, COL_SIZE

class MainWindow(QMainWindow):
    def __init__(self, start_path: str = "/"):
        super().__init__()
        self.setWindowTitle("Lintree")
        self.resize(960, 620)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)

        # Editable path field with filesystem autocomplete.
        self.path_edit = QLineEdit(start_path)
        self.path_edit.setFont(QFont("monospace", 10))
        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath("")
        self._fs_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        completer = QCompleter(self._fs_model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.path_edit.setCompleter(completer)
        self.path_edit.returnPressed.connect(self._on_path_entered)

        go_btn = QPushButton("Go")
        go_btn.setFixedWidth(50)
        go_btn.clicked.connect(self._on_path_entered)

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setFixedWidth(90)
        refresh_btn.clicked.connect(lambda: self.tree.load_root(self.current_path))

        root_btn = QPushButton("↑ Up")
        root_btn.setFixedWidth(70)
        root_btn.clicked.connect(self._go_up)

        # Unit dropdown
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(_UNITS)
        self.unit_combo.setFixedWidth(80)
        self.unit_combo.currentTextChanged.connect(self._on_unit_changed)

        toolbar_layout.addWidget(QLabel("Path:"))
        toolbar_layout.addWidget(self.path_edit, stretch=1)
        toolbar_layout.addWidget(go_btn)
        toolbar_layout.addWidget(root_btn)
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addWidget(QLabel("Unit:"))
        toolbar_layout.addWidget(self.unit_combo)

        # ── Tree ──────────────────────────────────────────────────────────────
        self.tree = DiskTree()
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.scan_done.connect(self.statusBar().showMessage)

        # ── Mount info bar ────────────────────────────────────────────────────
        self.mount_label = QLabel()
        self._update_mount_info(start_path)

        # ── Layout ───────────────────────────────────────────────────────────
        central = QWidget()
        layout  = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar_widget)
        layout.addWidget(self.tree)
        layout.addWidget(self.mount_label)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Scanning…")
        self.current_path = start_path
        self.tree.load_root(start_path)

    def _on_path_entered(self):
        """Triggered by pressing Enter in the path field or clicking Go."""
        path = self.path_edit.text().strip()
        if not path:
            return
        if not os.path.isdir(path):
            self.statusBar().showMessage(f"Not a valid directory: {path}", 4000)
            return
        self.current_path = path
        self._update_mount_info(path)
        self.statusBar().showMessage(f"Scanning {path}…")
        self.tree.load_root(path)

    def _on_unit_changed(self, unit: str):
        self.tree.set_unit(unit)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        """Double-clicking a row navigates into that directory."""
        path = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if path and os.path.isdir(path):
            self.current_path = path
            self.path_edit.setText(path)
            self._update_mount_info(path)
            self.statusBar().showMessage(f"Scanning {path}…")
            self.tree.load_root(path)

    def _go_up(self):
        parent = str(Path(self.current_path).parent)
        if parent != self.current_path:
            self.current_path = parent
            self.path_edit.setText(parent)
            self._update_mount_info(parent)
            self.statusBar().showMessage(f"Scanning {parent}…")
            self.tree.load_root(parent)

    def _update_mount_info(self, path: str):
        try:
            st = os.statvfs(path)
            total = st.f_blocks * st.f_frsize
            free  = st.f_bavail * st.f_frsize
            used  = total - free
            pct   = used / total * 100 if total else 0
            unit  = self.tree.current_unit
            self.mount_label.setText(
                f"  Mount: {human_size(used, unit)} used / {human_size(total, unit)} total "
                f"({pct:.1f}% used)  —  {human_size(free, unit)} free"
            )
        except OSError:
            self.mount_label.setText("  Mount info unavailable")

