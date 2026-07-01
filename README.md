# Lintree

A lightweight Linux GUI application for visualizing disk usage across your filesystem. Built with Python and PyQt6, it lets you browse any directory tree, see how much space each folder occupies, and understand what percentage of its host partition it represents — all without leaving a single window.



---

## Features

**Filesystem-aware size calculation**

- Each folder's size is calculated against the capacity of the partition it actually lives on, not its parent directory. This means btrfs subvolumes, secondary drives, and any other mount points all display accurate percentages (never above 100%).
- Cross-device mount points (e.g. a second drive mounted inside your home directory) are scanned on their own filesystem and show their own disk's capacity.
- Virtual and pseudo-filesystems (`/proc`, `/sys`, `tmpfs`, `cgroup`, devpts, etc.) are automatically detected via `/proc/self/mountinfo` and excluded from size calculations, preventing inflated sizes from virtual files like `/proc/kcore`.
- Symlinks to directories are followed once, with inode-based deduplication to avoid counting the same data twice when multiple symlinks point to the same target.

**Non-blocking background scanning**

- All directory scanning runs in a `QThread` worker, keeping the UI fully responsive during long scans.
- Lazy expansion: subdirectory contents are only scanned when you click the `[+]` expander, so the initial view appears quickly.

**Interactive tree view**

| Column | Description |
|--------|-------------|
| Path | Folder name (expandable) |
| Size | Space used, in the selected unit |
| % of mount | Percentage of the host partition's total capacity |
| Usage | Visual progress bar (color-coded: blue < 10%, amber < 30%, red ≥ 30%) |
| Disk | The device or partition the folder resides on (e.g. `/dev/nvme0n1p1`) |

**Sorting** — click any column header to sort ascending or descending. Size and % columns sort numerically (not alphabetically), so `9 GB` correctly sorts before `10 GB`.

**Unit selector** — switch between Auto, B, KB, MB, GB, and TB from the toolbar dropdown. All visible rows update instantly without rescanning.

**Editable path bar** — type any path directly, with filesystem autocompletion. Press Enter or click Go to navigate. The `↑ Up` button goes to the parent directory, and double-clicking any row navigates into it.

**Clipboard support**

- The `⧉` button on each row copies the full path to the clipboard.
- Right-click any row for a context menu with individual options: Copy path, Copy size, Copy %, Copy disk.

**Mount info bar** — the bottom of the window always shows the total capacity, used space, free space, and usage percentage of the currently viewed partition.

---

## Prerequisites

- **Linux** (uses `/proc/self/mountinfo` and `os.statvfs`; not compatible with macOS or Windows)
- **Python 3.10 or later** (uses `match`-free union type hints: `X | Y`)
- **PyQt6**

---

## Installation

**Via pip:**

```bash
pip install PyQt6
```

**Via pacman (Arch / CachyOS / Manjaro):**

```bash
sudo pacman -S python-pyqt6
```

**Via apt (Debian / Ubuntu):**

```bash
sudo apt install python3-pyqt6
```

---

## Usage

```bash
# Start from the filesystem root
python3 disk_explorer.py

# Start from a specific directory
python3 disk_explorer.py /home
python3 disk_explorer.py /var
```

### Navigation

| Action | Result |
|--------|--------|
| Click `[+]` on a row | Expand and scan subdirectories |
| Double-click a row | Navigate into that directory (rescan from there) |
| Edit the path bar + Enter | Jump to any path with autocompletion |
| `↑ Up` button | Go to the parent directory |
| `⟳ Refresh` button | Rescan the current directory |
| Click a column header | Sort ascending; click again for descending |
| Right-click a row | Copy path / size / % / disk to clipboard |

---

## Notes on reported sizes

Lintree intentionally reports sizes differently from some other tools:

- **vs. `du` (default):** `du` counts allocated blocks (`st_blocks × 512`); Lintree counts logical file sizes (`st_size`). Results can differ on compressed filesystems (btrfs with zstd) or sparse files.
- **vs. Dolphin / Nautilus:** File managers typically sum everything accessible under a path, including content on other drives mounted inside a directory. Lintree reports per-filesystem: a folder that is a mount point for a second drive shows the size of that drive's contents against *that drive's* capacity — not against the parent filesystem.
- **Symlinks to files** are not counted (only symlinks to directories are followed, with deduplication). This avoids double-counting files that are reachable both directly and via symlink.

---

## Known limitations

- Requires read access to directories being scanned. Folders with restricted permissions are silently skipped.
- Network filesystems (NFS, SMB/CIFS, sshfs) are scanned if mounted locally. Depending on network speed, this can be slow.
- The `Disk` column shows the raw source from `/proc/self/mountinfo`. For btrfs subvolumes this will be something like `/dev/nvme1n1p2[/@home]` rather than a simple device path.

---

## License

MIT : do whatever you want with it. Please mention the original project to respect my work :)
