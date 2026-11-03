"""Bind available checkpoints at the requested iteration; preserve missing states."""
import sys
from common import *
def main(site):
 cfg();chosen={}
 for r in json.loads((O/'inventory.json').read_text())['rows']:
  if r['site']!=site or r['family']=='r7':continue
  k=(r['prior'],r['family'])
  if r['iteration']==30000 or r['iteration']==7000 and k not in chosen:chosen[k]=r
 jobs=[]
 for r in chosen.values():
  j=dict(r);j['key']=f"{site}__{r['prior']}__{r['family']}_{r['iteration']}";root=Path(r['model']).parent;post=root/'post/post.json'
  assert post.exists(),post;j['box']=json.loads(post.read_text())['box'];j['renderer']=j['renderer'].replace('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp','/repo').replace('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts','/art');dump(O/'jobs'/f"{j['key']}.json",j);jobs.append(j)
 viewjob=dict(next((j for j in jobs if j['family']=='baseline'),jobs[0]));viewjob.update(renderer='/repo/src/phd/forks/GeoGS-conf-guided-v1-r22',image='jointbuildgs:geogs-conf-guided-v1',key=site+'__freeze_views');dump(O/'jobs'/f'{site}__views.json',viewjob);dump(O/'jobs'/f'{site}_index.json',dict(jobs=jobs,scientific_verdict=None))
if __name__=='__main__':main(sys.argv[1])
