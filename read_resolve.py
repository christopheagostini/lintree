from variable import _VIRTUAL_FS_TYPES, _UNIT_DIVISORS, _UNITS, COL_NAME, COL_BAR, COL_COPY, COL_DISK, COL_PCT, COL_SIZE


def _read_mount_table() -> list[tuple[str, str, str]]:
    """
    Parse /proc/self/mountinfo into a list of (mount_point, fstype, source).
    Used both to skip virtual filesystems and to resolve which physical
    device/partition a given path lives on.
    """
    table: list[tuple[str, str, str]] = []
    try:
        with open("/proc/self/mountinfo", "r") as f:
            for line in f:
                parts = line.split(" - ")
                if len(parts) != 2:
                    continue
                left = parts[0].split()
                right = parts[1].split()
                if len(left) >= 5 and len(right) >= 2:
                    mount_point = left[4]
                    fstype = right[0]
                    source = right[1]
                    table.append((mount_point, fstype, source))
    except OSError:
        pass
    return table


def _read_mount_fstypes() -> dict[str, str]:
    """Map mount point path -> filesystem type (derived from the full mount table)."""
    return {mp: fstype for mp, fstype, _src in _read_mount_table()}


def resolve_mount_source(path: str, mount_table: list[tuple[str, str, str]] | None = None) -> str:
    """
    Return the device/partition (e.g. '/dev/nvme0n1p1') that `path` resides on,
    by finding the longest matching mount point prefix. Falls back to the
    raw source string if it isn't a recognizable device path (e.g. for
    network shares or virtual filesystems), or '?' if nothing matches.
    """
    if mount_table is None:
        mount_table = _read_mount_table()

    best_match = ""
    best_source = "?"
    for mount_point, _fstype, source in mount_table:
        if path == mount_point or path.startswith(mount_point.rstrip("/") + "/") or mount_point == "/":
            if len(mount_point) >= len(best_match):
                best_match = mount_point
                best_source = source
    return best_source
