"""Only new completion/health/error events, with bounded training-log summaries."""
from add2_host import *
q=O/'queue/addendum2';cursor=q/'summary_cursor.json';n=json.loads(cursor.read_text())['lines'] if cursor.exists() else 0
p=q/'events.jsonl';lines=p.read_text().splitlines() if p.exists() else []
for line in lines[n:]:
    v=json.loads(line)
    if v['event'] not in ['TRAINING_FINISHED','HEALTH_7000','POST_ERROR','CPU_ERROR','RENDER_ERROR','PACKAGE','CPU_COMPLETE','ALTERNATIVE_FINISHED']:continue
    if v['event']=='HEALTH_7000':
        h=v['value'];v=dict(at=v['at'],event=v['event'],path=v['path'],health={k:h.get(k) for k in ['iteration','status','loss','gaussians','prior_opacity_median']})
    print(json.dumps(v,ensure_ascii=False),flush=True)
dump(cursor,dict(lines=len(lines)))
