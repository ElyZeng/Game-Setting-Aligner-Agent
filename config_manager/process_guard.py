"""Detect whether a game is still running before its config is written.

A running game keeps its settings in memory and usually writes them back when
it exits, silently undoing (or half-undoing) anything Game Tuner wrote in the
meantime.  Writes are therefore refused while any process whose executable
lives inside the game's install folder is running.

On Windows the process list comes from the Win32 API through ``ctypes`` (no
extra dependency, no PowerShell start-up delay).  On other platforms it falls
back to ``/proc`` so the logic can be unit-tested; it returns an empty list
where neither is available.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set

ProcessLister = Callable[[], Iterable[str]]


def _windows_executables() -> List[str]:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]

    count = 4096
    while True:
        pids = (wintypes.DWORD * count)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(needed)):
            raise OSError(ctypes.get_last_error(), "EnumProcesses failed")
        if needed.value < ctypes.sizeof(pids):
            break
        count *= 2
    total = needed.value // ctypes.sizeof(wintypes.DWORD)

    paths: List[str] = []
    buffer = ctypes.create_unicode_buffer(32768)
    for pid in pids[:total]:
        if not pid:
            continue
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            continue  # protected/system process, or it exited meanwhile
        try:
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                paths.append(buffer.value)
        finally:
            kernel32.CloseHandle(handle)
    return paths


def _proc_executables() -> List[str]:
    root = Path("/proc")
    paths: List[str] = []
    if not root.is_dir():
        return paths
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            paths.append(os.readlink(entry / "exe"))
        except OSError:
            continue
    return paths


def list_running_executables() -> List[str]:
    """Full executable paths of the processes this user can see."""
    if sys.platform == "win32":
        return _windows_executables()
    return _proc_executables()


def _normalise(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def running_processes_in(
    install_path: str,
    lister: Optional[ProcessLister] = None,
    ignore: Optional[Iterable[str]] = None,
) -> List[str]:
    """Running executables located inside *install_path* (sorted, unique).

    *ignore* is an optional list of executable basenames (matched
    case-insensitively, e.g. ``"EpicWebHelper.exe"``) that are never reported
    as "the game is running" even though they live under *install_path* —
    some games launch auxiliary/helper processes from inside their own
    install folder that are not the game itself and should not block a
    write. This is additive to the general folder-prefix check, never a
    replacement for it: anything not explicitly ignored is still reported.
    """
    if not install_path or not Path(install_path).is_dir():
        return []
    root = _normalise(install_path)
    prefix = root.rstrip("\\/") + os.sep
    ignore_names: Set[str] = {name.casefold() for name in (ignore or ())}
    found = set()
    for executable in (lister or list_running_executables)():
        if not executable:
            continue
        if ignore_names and Path(executable).name.casefold() in ignore_names:
            continue
        normalised = _normalise(executable)
        if normalised == root or normalised.startswith(prefix):
            found.add(executable)
    return sorted(found)
