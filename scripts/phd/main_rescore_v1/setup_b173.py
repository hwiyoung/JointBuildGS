from common import *
def main():
 cfg();rows=json.loads((O/'inventory.json').read_text())['rows'];chosen={}
 for r in rows:
  if r['site']!='B173nb_b10' or r['family']=='r7':continue
  k=(r['prior'],r['family'])
  if r['iteration']==30000 or r['iteration']==7000 and k not in chosen:chosen[k]=r
 box=json.loads((O/'meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json').read_text())['box'];jobs=[]
 for r in chosen.values():
  j=dict(r);j['key']=f"{r['site']}__{r['prior']}__{r['family']}_{r['iteration']}";j['box']=box
  if r['family']=='r8':j['cache']=str(TG/'r8/meshes'/f"r8_{r['prior']}_{r['iteration']}"/'render')
  j['renderer']=j['renderer'].replace('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp','/repo').replace('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts','/art')
  dump(O/'jobs'/f"{j['key']}.json",j);jobs.append(j)
 dump(O/'jobs/B173nb_index.json',dict(jobs=jobs,scientific_verdict=None))
 print('JOBS',len(jobs))
if __name__=='__main__':main()
