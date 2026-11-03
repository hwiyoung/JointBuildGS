"""One production-scorer validation: column boundaries and complete legacy replay."""
from common import *
from geometry import columns
from score_mesh import score

def main():
 start=time.monotonic()
 core=dict(centre=np.array([[0.,0.,0.],[0.,0.,1.],[2.,0.,0.]]),normal=np.array([[0.,0.,1.],[0.,0.,1.],[1.,0.,0.]]),tangent1=np.array([[1.,0.,0.],[1.,0.,0.],[0.,1.,0.]]),tangent2=np.array([[0.,1.,0.],[0.,1.,0.],[0.,0.,1.]]),kind=np.array([1,1,2]),prior=np.array(['LoD2']*3),prior_height_m=np.zeros(3))
 P=np.array([[0,0,.2],[0,0,.8],[0,0,.5],[.125,0,0],[.12500001,0,0],[0,0,11.01],[7,0,0],[7.000001,0,0]],float)
 own,hits=columns(P,core,O/'validation/columns');assert own.tolist()==[0,1,0,0,2,-1,2,-1],(own,hits)
 assert hits.tolist()==[2,2,2,3,1,0,1,0],hits
 rows=[]
 for key,expected in [('r8_ALS_30000',[88.5,72.6,9.9,17.2]),('base_ALS_30000',[86.8,78.2,11.5,14.3])]:
  part='r8' if key.startswith('r8') else 'r7_continue';binding=json.loads((TG/part/'scoring'/key/'current/binding.json').read_text());mesh=Path(binding['mesh'].replace('/ph/',str(PH)+'/').replace('/target/',str(TG)+'/'));assert sha(mesh)==binding['mesh_sha256']
  v=score('B173nb_b10','ALS','legacy_replay_'+key,mesh,legacy=True)['scene'];actual=[v['completeness']*100,v['accuracy']*100,v['gt_mean_m']*100,v['result_mean_m']*100];delta=[a-b for a,b in zip(actual,expected)]
  rows.append(dict(key=key,actual=actual,expected=expected,delta=delta,pass_tolerance=all(abs(d)<=.1 for d in delta),source='complete geometric replay from bound legacy training mesh',source_tag='[이 발주에서 냄]'))
 table('reproduction_full_replay',rows);dump(O/'validation/scorer.json',dict(columns='PASS_BOUNDARIES_OVERLAP_TIE',reproduction=rows,scientific_verdict=None));timing('scorer_validation',start)
if __name__=='__main__':main()
