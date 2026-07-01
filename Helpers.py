import os

def get_mount_total(path: str) -> int:
    """Return total bytes of the filesystem that contains `path`."""
    try:
        stat = os.statvfs(path)
        return stat.f_blocks * stat.f_frsize
    except (PermissionError, OSError):
        return 0