"""Prevent two personal-app processes from sharing an active library."""
from contextlib import contextmanager
import os
import library


@contextmanager
def library_lock():
    path = library.db_path().with_suffix(".db.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another ListenFlow process is using this library. Close it before switching modes.") from exc
        yield
    finally:
        handle.close()  # Closing releases the OS lock, including after process termination.
