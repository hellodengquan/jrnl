# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import atexit
import logging
import os
import platform
import signal
import sys
import time
from contextlib import contextmanager
from typing import Any
from typing import Optional

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.os_compat import on_windows
from jrnl.output import print_msg


class JournalLock:
    """Cross-process journal lock using fcntl (Unix) / msvcrt (Windows) + PID lockfile.

    Double-lock strategy:
    1. Advisory file-level lock on the journal file (fcntl.LOCK_EX / msvcrt.locking)
    2. PID-based lock file next to the journal, with stale-detection

    The lock is released automatically via context manager exit, atexit handler,
    SIGINT/SIGTERM handlers, or explicit release().
    """

    _LOCKED_RESOURCES: dict[str, "JournalLock"] = {}
    _SIGNAL_HANDLERS_INSTALLED = False

    def __init__(
        self,
        journal_name: str,
        journal_path: str,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> None:
        self.journal_name = journal_name
        self.journal_path = os.path.abspath(journal_path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._lock_file: Optional[int] = None
        self._lock_file_path: Optional[str] = None
        self._acquired = False
        self._on_windows = on_windows()
        self._lock_count = 0

        self._install_signal_handlers()

    @classmethod
    def _install_signal_handlers(cls) -> None:
        if cls._SIGNAL_HANDLERS_INSTALLED:
            return
        cls._SIGNAL_HANDLERS_INSTALLED = True

        def _signal_cleanup(signum: Any, frame: Any) -> None:
            for lock in list(cls._LOCKED_RESOURCES.values()):
                try:
                    lock.release()
                except Exception:
                    pass
            sys.exit(128 + signum)

        if not on_windows():
            try:
                signal.signal(signal.SIGTERM, _signal_cleanup)
                signal.signal(signal.SIGINT, _signal_cleanup)
            except ValueError:
                pass

        atexit.register(cls._atexit_cleanup)

    @classmethod
    def _atexit_cleanup(cls) -> None:
        for lock in list(cls._LOCKED_RESOURCES.values()):
            try:
                lock.release()
            except Exception:
                pass
            try:
                if lock._lock_file_path and os.path.exists(lock._lock_file_path):
                    os.unlink(lock._lock_file_path)
            except Exception:
                pass

    def _pid_lock_path(self) -> str:
        """Compute path for the PID lock file."""
        if os.path.isdir(self.journal_path):
            base_dir = self.journal_path
            base_name = ".jrnl"
        else:
            base_dir = os.path.dirname(self.journal_path)
            base_name = os.path.basename(self.journal_path)
        return os.path.join(base_dir, f".{base_name}.lock")

    @staticmethod
    def _process_exists(pid: int) -> bool:
        """Check if a process with given PID is running."""
        if pid <= 0:
            return False
        if on_windows():
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            return True

    def _read_lock_file(self, path: str) -> tuple[int, str, float]:
        """Return (pid, owner, timestamp) from a lock file."""
        try:
            with open(path, "r") as f:
                content = f.read().strip()
                if not content:
                    return (0, "", 0.0)
                parts = content.split("|", 2)
                pid = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                owner = parts[1] if len(parts) > 1 else ""
                tstamp = float(parts[2]) if len(parts) > 2 else 0.0
                return (pid, owner, tstamp)
        except (OSError, ValueError):
            return (0, "", 0.0)

    def _write_lock_file(self, path: str) -> None:
        """Write our PID + metadata to the lock file atomically."""
        import tempfile

        dir_name = os.path.dirname(path) or "."
        os.makedirs(dir_name, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".lock_", dir=dir_name)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(
                    f"{os.getpid()}|{platform.node()}|{time.time()}"
                )
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise

    def _remove_lock_file(self) -> None:
        if self._lock_file_path and os.path.exists(self._lock_file_path):
            try:
                pid, _, _ = self._read_lock_file(self._lock_file_path)
                if pid == os.getpid():
                    os.unlink(self._lock_file_path)
            except OSError:
                pass

    def _try_fcntl_lock(self) -> bool:
        """Try to acquire advisory fcntl lock on the journal file or a sentinel."""
        if self._on_windows:
            return self._try_msvcrt_lock()

        try:
            import fcntl

            if os.path.isfile(self.journal_path):
                target_path = self.journal_path
            else:
                target_path = self._pid_lock_path() + ".fcntl"
                if not os.path.exists(target_path):
                    parent = os.path.dirname(target_path)
                    if parent and not os.path.isdir(parent):
                        os.makedirs(parent, exist_ok=True)
                    open(target_path, "a").close()

            self._lock_file = os.open(target_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                os.close(self._lock_file)
                self._lock_file = None
                return False
        except Exception as e:
            logging.debug(f"fcntl lock failed: {e}")
            if self._lock_file is not None:
                try:
                    os.close(self._lock_file)
                except Exception:
                    pass
                self._lock_file = None
            return False

    def _try_msvcrt_lock(self) -> bool:
        """Windows msvcrt locking fallback."""
        try:
            import msvcrt

            if os.path.isfile(self.journal_path):
                target_path = self.journal_path
            else:
                target_path = self._pid_lock_path() + ".fcntl"
                parent = os.path.dirname(target_path)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                open(target_path, "a").close()

            self._lock_file = os.open(target_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                os.lseek(self._lock_file, 0, 0)
                msvcrt.locking(self._lock_file, msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                os.close(self._lock_file)
                self._lock_file = None
                return False
        except Exception as e:
            logging.debug(f"msvcrt lock failed: {e}")
            if self._lock_file is not None:
                try:
                    os.close(self._lock_file)
                except Exception:
                    pass
                self._lock_file = None
            return False

    def _release_fcntl_lock(self) -> None:
        if self._lock_file is None:
            return
        try:
            if self._on_windows:
                import msvcrt

                os.lseek(self._lock_file, 0, 0)
                msvcrt.locking(self._lock_file, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        except Exception as e:
            logging.debug(f"Unlock advisory lock failed: {e}")
        try:
            os.close(self._lock_file)
        except Exception:
            pass
        self._lock_file = None

    def acquire(self) -> bool:
        """Acquire the journal lock, with timeout + stale detection.

        Returns True on success, False on failure (warning already printed).
        """
        if self._acquired:
            self._lock_count += 1
            return True

        self._lock_file_path = self._pid_lock_path()
        deadline = time.time() + self.timeout
        warned_waiting = False
        first_pass = True

        while time.time() < deadline:
            if self._try_fcntl_lock():
                try:
                    if os.path.exists(self._lock_file_path):
                        pid, owner, tstamp = self._read_lock_file(self._lock_file_path)
                        if pid != 0 and pid != os.getpid():
                            if self._process_exists(pid):
                                if not warned_waiting and not first_pass:
                                    print_msg(
                                        Message(
                                            MsgText.JournalLockWaiting,
                                            MsgStyle.WARNING,
                                            {
                                                "journal_name": self.journal_name,
                                                "pid": pid,
                                                "owner": owner or "unknown",
                                                "timeout": max(
                                                    0.0, deadline - time.time()
                                                ),
                                            },
                                        )
                                    )
                                    warned_waiting = True
                                self._release_fcntl_lock()
                                time.sleep(self.poll_interval)
                                first_pass = False
                                continue
                            else:
                                print_msg(
                                    Message(
                                        MsgText.JournalLockStale,
                                        MsgStyle.WARNING,
                                        {
                                            "journal_name": self.journal_name,
                                            "pid": pid,
                                        },
                                    )
                                )
                                try:
                                    os.unlink(self._lock_file_path)
                                except OSError:
                                    pass

                    self._write_lock_file(self._lock_file_path)
                    self._acquired = True
                    self._lock_count = 1
                    JournalLock._LOCKED_RESOURCES[self.journal_path] = self
                    logging.debug(f"Lock acquired: {self.journal_name}")
                    print_msg(
                        Message(
                            MsgText.JournalLockAcquired,
                            MsgStyle.NORMAL,
                            {"journal_name": self.journal_name},
                        )
                    )
                    return True
                except Exception as e:
                    logging.error(f"Lock acquire error: {e}")
                    self._release_fcntl_lock()
                    return False
            else:
                time.sleep(self.poll_interval)
                first_pass = False

        if os.path.exists(self._lock_file_path):
            pid, owner, _ = self._read_lock_file(self._lock_file_path)
        else:
            pid, owner = 0, "unknown"

        print_msg(
            Message(
                MsgText.JournalLockTimeout,
                MsgStyle.WARNING,
                {
                    "journal_name": self.journal_name,
                    "timeout": self.timeout,
                    "pid": pid or "unknown",
                    "lock_path": self._lock_file_path,
                },
            )
        )
        return False

    def release(self) -> None:
        """Release the lock (ref-counted)."""
        if not self._acquired:
            return

        self._lock_count = max(0, self._lock_count - 1)
        if self._lock_count > 0:
            return

        self._acquired = False
        try:
            self._remove_lock_file()
        except Exception:
            pass
        try:
            self._release_fcntl_lock()
        except Exception:
            pass

        try:
            del JournalLock._LOCKED_RESOURCES[self.journal_path]
        except KeyError:
            pass

        logging.debug(f"Lock released: {self.journal_name}")
        print_msg(
            Message(
                MsgText.JournalLockReleased,
                MsgStyle.NORMAL,
                {"journal_name": self.journal_name},
            )
        )

    def __enter__(self) -> "JournalLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


@contextmanager
def locked_journal(journal_name: str, journal_path: str, timeout: float = 30.0):
    """Context manager that acquires a JournalLock and yields it.

    If the lock cannot be acquired, it yields None so the caller can decide
    whether to proceed without a lock (with a warning).
    """
    lock = JournalLock(journal_name, journal_path, timeout)
    acquired = lock.acquire()
    if not acquired:
        print_msg(
            Message(
                MsgText.JournalLockWarning,
                MsgStyle.WARNING,
                {"journal_name": journal_name},
            )
        )
        yield None
        return

    try:
        yield lock
    finally:
        lock.release()
