_VIRTUAL_FS_TYPES = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
    "pstore", "bpf", "tracefs", "debugfs", "securityfs", "configfs",
    "fusectl", "mqueue", "hugetlbfs", "autofs", "binfmt_misc", "rpc_pipefs",
}

_UNITS = ["Auto", "B", "KB", "MB", "GB", "TB"]

_UNIT_DIVISORS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


# ── Tree item with inline progress bar ────────────────────────────────────────

COL_NAME = 0
COL_SIZE = 1
COL_PCT  = 2
COL_BAR  = 3
COL_DISK = 4
COL_COPY = 5