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
from main_window import MainWindow



# ── Main window ───────────────────────────────────────────────────────────────

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "/"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(start_path=start)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()