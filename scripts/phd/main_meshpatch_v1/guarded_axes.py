"""Keep AXES definitions unchanged while guarding its worker process memory."""
import sys
from pathlib import Path
from mesh_common import D, dump, now
from mesh_staged import policy, supervise

policy()
key=sys.argv[2] if len(sys.argv)>2 else 'baseline'
receipt=supervise([sys.executable,*sys.argv[1:]])
dump(D/'tables/axes_memory'/f'{key}.json',dict(key=key,**receipt))
if receipt['exit_code']:
    with (D/'issues.md').open('a') as stream:
        stream.write(f'\n- {now()}: 추가 지표 {key} 프로세스 중단. 메모리·OOM·종료 기록: tables/axes_memory/{key}.json. 완료 수치로 처리하지 않는다.\n')
    raise SystemExit(1)
