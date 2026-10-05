"""Serialize task-local CPU-heavy extraction without changing native settings."""
import fcntl
import hashlib
from pathlib import Path
import time

HELPER_SOURCE = Path(__file__).read_bytes()
HELPER_SHA256 = hashlib.sha256(HELPER_SOURCE).hexdigest()
LOCK_PATH = Path('/weights/.geogs_extraction.lock')


def acquire_extraction_lock(phase, lock_path=LOCK_PATH):
    if phase not in ('render', 'auxiliary'):
        return None, {'serialized_extraction': False, 'wait_seconds': 0.0}
    started = time.monotonic()
    handle = Path(lock_path).open('rb')
    # flock operates on the shared host inode even through read-only bind mounts.
    # The parent keeps this descriptor until its phase exits; Popen closes it in
    # the native child, and the auxiliary helper does not acquire it again.
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle, {'serialized_extraction': True,
                    'policy': 'ONE_REGIONAL_RENDER_OR_AUXILIARY_PHASE_AT_A_TIME',
                    'lock_path': str(lock_path), 'lock_open_mode': 'rb',
                    'wait_seconds': time.monotonic() - started,
                    'wait_excluded_from_native_phase_wall_seconds': True,
                    'helper_sha256': HELPER_SHA256}
