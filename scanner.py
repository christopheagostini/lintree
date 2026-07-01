import os
from variable import _VIRTUAL_FS_TYPES
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDir
from PyQt6.QtGui import QFont, QGuiApplication, QFileSystemModel
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QHeaderView, QStatusBar, QSizePolicy,
    QLineEdit, QCompleter, QComboBox, QMenu
)
from read_resolve import _read_mount_fstypes, _read_mount_table, resolve_mount_source
from variable import _VIRTUAL_FS_TYPES, _UNIT_DIVISORS, _UNITS, COL_NAME, COL_BAR, COL_COPY, COL_DISK, COL_PCT, COL_SIZE
from Helpers import get_mount_total

def human_size(n: int, unit: str = "Auto") -> str:
    """
    Convert bytes to a human-readable string.
    If `unit` is "Auto", picks the largest unit where the value is >= 1.
    Otherwise forces the given unit (B, KB, MB, GB, TB).
    """
    if unit != "Auto" and unit in _UNIT_DIVISORS:
        value = n / _UNIT_DIVISORS[unit]
        return f"{value:.2f} {unit}" if unit != "B" else f"{value:.0f} {unit}"

    val = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024:
            return f"{val:.1f} {u}"
        val /= 1024
    return f"{val:.1f} PB"


def dir_size(path: str, virtual_mounts: dict[str, str] | None = None) -> int:
    """
    Return the total byte size of all content reachable from `path`,
    with the following properties:

    - Follows symlinks to DIRECTORIES (so ~/.steam/root → ~/.local/share/Steam
      is counted once, not zero times as before).
    - Deduplicates via (st_dev, st_ino) set: if multiple symlinks point to the
      same inode (e.g. .steam/root and .steam/steam both → Steam dir), the
      content is counted exactly once.
    - Symlinks to FILES are NOT followed (their target may already be reachable
      directly; following them would risk double-counting without an inode check
      on every file, which would be too slow).
    - Does NOT cross mount point boundaries (different physical devices).
    - Skips virtual/pseudo filesystems (/proc, /sys, tmpfs…) by mount table.
    - Fully iterative (no recursion): immune to Python recursion limits on
      very deep trees (node_modules, Wine prefixes, etc.).
    """
    if virtual_mounts is None:
        virtual_mounts = _read_mount_fstypes()

    # Inode set prevents counting the same directory content twice when
    # multiple symlinks resolve to the same target directory.
    visited: set[tuple[int, int]] = set()

    try:
        root_stat = os.stat(path)   # follows symlink if path itself is one
        root_dev  = root_stat.st_dev
    except OSError:
        return 0

    visited.add((root_stat.st_dev, root_stat.st_ino))
    stack = [path]
    total = 0

    while stack:
        current = stack.pop()

        try:
            it = os.scandir(current)
        except (PermissionError, OSError):
            continue

        try:
            for entry in it:
                try:
                    # Virtual filesystem mount point → skip
                    if entry.path in virtual_mounts and virtual_mounts[entry.path] in _VIRTUAL_FS_TYPES:
                        continue

                    is_link = entry.is_symlink()

                    if is_link and entry.is_dir():
                        # Symlink to a directory: resolve and check if we
                        # should follow it (same device, not yet visited).
                        try:
                            target_stat = os.stat(entry.path)   # follows link
                        except OSError:
                            continue
                        if target_stat.st_dev != root_dev:
                            continue
                        key = (target_stat.st_dev, target_stat.st_ino)
                        if key in visited:
                            continue
                        visited.add(key)
                        stack.append(entry.path)

                    elif entry.is_dir(follow_symlinks=False):
                        # Real directory: check device boundary
                        try:
                            st = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if st.st_dev != root_dev:
                            continue
                        key = (st.st_dev, st.st_ino)
                        if key in visited:
                            continue
                        visited.add(key)
                        stack.append(entry.path)

                    elif entry.is_file(follow_symlinks=False) and not is_link:
                        # Regular file (not a symlink): count its size
                        try:
                            total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass

                except (PermissionError, OSError):
                    continue

        except OSError:
            pass
        finally:
            it.close()

    return total


def make_tree_item(name: str, path: str, size: int, mount_total: int,
                    source: str = "?", unit: str = "Auto") -> QTreeWidgetItem:
    pct = (size / mount_total * 100) if mount_total > 0 else 0.0
    item = SortableTreeItem(["", human_size(size, unit), f"{pct:.2f}%", "", source, ""])
    item.setText(COL_NAME, name)
    item.setData(COL_NAME, Qt.ItemDataRole.UserRole, path)         # full path
    item.setData(COL_SIZE, Qt.ItemDataRole.UserRole, size)         # raw bytes
    item.setData(COL_PCT,  Qt.ItemDataRole.UserRole, mount_total)  # raw mount total
    item.setChildIndicatorPolicy(
        QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    return item


class ScanWorker(QObject):
    """
    Scans subdirectories of `root_path` in a background thread.
    Emits one signal per directory with (name, path, size_bytes, mount_total, source_device).
    Emits scan_done with a summary message when the scan finishes.
    """
    # NOTE: size/mount_total use 'object' (not 'int') because PyQt marshals
    # 'int' as a C++ 32-bit signed int, which silently overflows/wraps to
    # negative for any directory at or above ~2.0 GB. 'object' passes the
    # underlying Python int through untouched, regardless of size.
    result    = pyqtSignal(str, str, object, object, str)  # name, path, size, mount_total, source
    scan_done = pyqtSignal(str)                  # summary message for status bar
    finished  = pyqtSignal()

    def __init__(self, root_path: str):
        super().__init__()
        self.root_path  = root_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        mount_table = _read_mount_table()
        virtual_mounts = {mp: ft for mp, ft, _src in mount_table}

        try:
            entries = sorted(
                (e for e in os.scandir(self.root_path)
                 if e.is_dir(follow_symlinks=False) and not e.is_symlink()),
                key=lambda e: e.name
            )
        except (PermissionError, OSError):
            entries = []

    def run(self):
        mount_table = _read_mount_table()
        virtual_mounts = {mp: ft for mp, ft, _src in mount_table}

        try:
            root_dev = os.stat(self.root_path).st_dev
        except OSError:
            root_dev = None

        try:
            entries = sorted(
                (e for e in os.scandir(self.root_path)
                 if e.is_dir(follow_symlinks=False) and not e.is_symlink()),
                key=lambda e: e.name
            )
        except (PermissionError, OSError):
            entries = []

        count = 0
        for entry in entries:
            if self._cancelled:
                break

            if entry.path in virtual_mounts and virtual_mounts[entry.path] in _VIRTUAL_FS_TYPES:
                # Virtual/pseudo filesystem (proc, sysfs, tmpfs…): show 0, no scan.
                size = 0
            else:
                # Scan the entry on whatever filesystem it lives on.
                # dir_size() will not cross further device boundaries inside it.
                # Cross-device mount points (e.g. a second drive mounted under
                # the home dir) are scanned on their own filesystem and compared
                # against their own mount_total below, so they show a correct
                # size and % instead of 0B.
                size = dir_size(entry.path, virtual_mounts)

            # Per-entry mount_total: each entry is compared against the capacity
            # of the filesystem it actually lives on, not the parent's filesystem.
            # This is what prevents btrfs subvolumes and cross-device mount points
            # from showing percentages > 100%.
            mount_total = get_mount_total(entry.path)
            source = resolve_mount_source(entry.path, mount_table)
            self.result.emit(entry.name, entry.path, size, mount_total, source)
            count += 1

        if not self._cancelled:
            self.scan_done.emit(
                f"Scan complete — {count} director{'y' if count == 1 else 'ies'} in {self.root_path}"
            )
        self.finished.emit()


class SortableTreeItem(QTreeWidgetItem):
    """
    QTreeWidgetItem that sorts Size and % columns numerically (using the
    raw byte/percentage values stored in UserRole) instead of doing a
    plain string comparison, which would otherwise sort "9 GB" after
    "10 MB" alphabetically. Other columns fall back to default text sort.
    """

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column == COL_SIZE:
            a = self.data(COL_SIZE, Qt.ItemDataRole.UserRole)
            b = other.data(COL_SIZE, Qt.ItemDataRole.UserRole)
            if a is not None and b is not None:
                return a < b
        elif column == COL_PCT:
            a_size = self.data(COL_SIZE, Qt.ItemDataRole.UserRole)
            a_total = self.data(COL_PCT, Qt.ItemDataRole.UserRole)
            b_size = other.data(COL_SIZE, Qt.ItemDataRole.UserRole)
            b_total = other.data(COL_PCT, Qt.ItemDataRole.UserRole)
            if a_size is not None and a_total:
                a_pct = a_size / a_total
            else:
                a_pct = 0
            if b_size is not None and b_total:
                b_pct = b_size / b_total
            else:
                b_pct = 0
            return a_pct < b_pct
        return self.text(column) < other.text(column)


class DiskTree(QTreeWidget):
    """
    A QTreeWidget that:
    - Shows a progress bar in the % column for each row
    - Lazily scans subdirectories when an item is expanded
    - Emits scan_done(msg) when a top-level scan finishes
    - Supports switching the displayed size unit (Auto/B/KB/MB/GB/TB)
    - Lets the user copy a row's path, size, or percentage via a button
      in the last column or a right-click context menu
    """

    scan_done = pyqtSignal(str)  # forwarded from ScanWorker for the status bar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_unit = "Auto"
        self.setColumnCount(6)
        self.setHeaderLabels(["Path", "Size", "% of mount", "Usage", "Disk", ""])
        self.header().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(COL_PCT,  QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(COL_BAR,  QHeaderView.ResizeMode.Fixed)
        self.header().setSectionResizeMode(COL_DISK, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(COL_COPY, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(COL_BAR, 160)
        self.setColumnWidth(COL_COPY, 36)
        self.setAlternatingRowColors(True)
        # Native ascending/descending sort by clicking column headers.
        # SortableTreeItem.__lt__ handles numeric sort for Size/% columns.
        self.setSortingEnabled(True)
        self.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        self.itemExpanded.connect(self._on_expand)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._workers: list[tuple[QThread, ScanWorker]] = []

    # ── Public ────────────────────────────────────────────────────────────────

    def load_root(self, path: str):
        """Start scanning from `path` and populate the top level."""
        self.clear()
        self._cancel_all_workers()
        self._scan(path, parent_item=None)

    def set_unit(self, unit: str):
        """Switch the displayed unit for every row currently in the tree."""
        self.current_unit = unit
        self._reformat_all_items()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_expand(self, item: QTreeWidgetItem):
        """Triggered when the user clicks [+]. Scan children lazily."""
        if item.childCount() == 0:
            path = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if path:
                self._scan(path, parent_item=item)

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("Copy path", lambda: self._copy_field(item, "path"))
        menu.addAction("Copy size", lambda: self._copy_field(item, "size"))
        menu.addAction("Copy %", lambda: self._copy_field(item, "pct"))
        menu.addAction("Copy disk", lambda: self._copy_field(item, "disk"))
        menu.exec(self.viewport().mapToGlobal(pos))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _copy_field(self, item: QTreeWidgetItem, field: str):
        clipboard = QGuiApplication.clipboard()
        if field == "path":
            clipboard.setText(item.data(COL_NAME, Qt.ItemDataRole.UserRole) or "")
        elif field == "size":
            clipboard.setText(item.text(COL_SIZE))
        elif field == "pct":
            clipboard.setText(item.text(COL_PCT))
        elif field == "disk":
            clipboard.setText(item.text(COL_DISK))

    def _reformat_all_items(self):
        def walk(item: QTreeWidgetItem):
            size = item.data(COL_SIZE, Qt.ItemDataRole.UserRole)
            if size is not None:
                item.setText(COL_SIZE, human_size(size, self.current_unit))
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))

    def _scan(self, path: str, parent_item: QTreeWidgetItem | None):
        worker = ScanWorker(path)
        thread = QThread()
        worker.moveToThread(thread)

        # Disable live re-sorting while rows stream in (avoids jumpy
        # insertion order), then restore the sort once the scan finishes.
        self.setSortingEnabled(False)

        worker.result.connect(
            lambda name, fpath, size, mt, source, _parent=parent_item:
                self._add_row(_parent, name, fpath, size, mt, source)
        )
        worker.finished.connect(lambda: self.setSortingEnabled(True))
        # Forward the completion message only for top-level scans
        if parent_item is None:
            worker.scan_done.connect(self.scan_done)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(lambda: self._cleanup_worker(thread, worker))

        self._workers.append((thread, worker))
        thread.start()

    def _add_row(self, parent: QTreeWidgetItem | None,
                 name: str, path: str, size: int, mount_total: int, source: str = "?"):
        item = make_tree_item(name, path, size, mount_total, source, self.current_unit)

        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)

        # Inject a QProgressBar into the Bar column
        bar = QProgressBar()
        bar.setRange(0, 100)
        pct_int = int((size / mount_total * 100)) if mount_total > 0 else 0
        bar.setValue(min(pct_int, 100))
        bar.setTextVisible(False)
        bar.setFixedHeight(14)
        bar.setStyleSheet(self._bar_style(pct_int))
        self.setItemWidget(item, COL_BAR, bar)

        # Inline copy button — copies the full path to the clipboard.
        # Right-click on the row for path/size/% options individually.
        copy_btn = QPushButton("⧉")
        copy_btn.setFixedSize(24, 20)
        copy_btn.setToolTip("Copy path (right-click row for more options)")
        copy_btn.clicked.connect(lambda _, p=path: QGuiApplication.clipboard().setText(p))
        self.setItemWidget(item, COL_COPY, copy_btn)

    @staticmethod
    def _bar_style(pct: int) -> str:
        if pct >= 30:
            color = "#e05050"
        elif pct >= 10:
            color = "#e09040"
        else:
            color = "#5090d0"
        return (
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
            "QProgressBar { border: 1px solid #888; border-radius: 3px; background: transparent; }"
        )

    def _cancel_all_workers(self):
        for thread, worker in self._workers:
            worker.cancel()
            thread.quit()
        self._workers.clear()

    def _cleanup_worker(self, thread: QThread, worker: ScanWorker):
        self._workers = [(t, w) for t, w in self._workers if t is not thread]

