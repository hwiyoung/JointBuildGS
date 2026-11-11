"""Lock trainlog_v1.json once, before the first computation (order 1.3)."""
from common import *
def main():
    p = C/'trainlog_v1.json'; lock = C/'trainlog_v1.lock.json'
    assert not lock.exists(), 'lock exists; refuse to re-lock'
    c = json.loads(p.read_text()); assert c['task_id'] == 'PHD-MAIN-TRAINLOG-v1'
    dump(lock, dict(locked_at=now(), config_sha256=sha(p), config='configs/phd/main_trainlog_v1/trainlog_v1.json',
        order_sha256=c['order']['sha256'], reference_code_sha256=c['reference_code']['sha256'], runtime_lock='trainlog_v1.runtime.lock.json is written separately before stage 2 (fork r27 + scripts)', scientific_verdict=None))
    print('LOCKED', sha(p))
if __name__ == '__main__': main()
