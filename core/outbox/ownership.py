"""OS-released per-operation ownership. Never expires or unlinks a live lock."""
from contextlib import contextmanager
import os
from core.vault.vault import safe_path
from .model import OperationId, Failure, Error


@contextmanager
def worker_lock(vault_path, account, operation):
    if type(operation) is not OperationId: raise Failure(Error.INVALID)
    directory = safe_path(vault_path.parent / (vault_path.name+'.m4-workers'))
    directory.mkdir(exist_ok=True)
    path = safe_path(directory / (account.value+'-'+operation.value+'.lock'))
    # Stable inode/file; do not delete on unlock (another process may hold a handle).
    with path.open('a+b') as file:
        file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: raise Failure(Error.BUSY) from None
        try: yield
        finally:
            file.seek(0)
            if os.name == 'nt': msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(file, fcntl.LOCK_UN)
