"""Bind chapter-6 cuts to earlier named places; no learned surface is consulted."""
from common import *
def main():
 wing=json.loads((C/'representatives_v1.json').read_text())['rows'][0];rows=[]
 for prior in ['LoD2','ALS']:rows.append(dict(wing,site='B173nb_b10',prior=prior,title='B173 날개 · '+prior))
 source=PH/'main_fill_v1/PHD-MAIN-FILL-v1/work/fig61/notes.json';notes=json.loads(source.read_text());cluster=max(notes['B0_wrong']['clusters'],key=lambda r:r['area_m2']);u=cluster['u_range'];v=np.mean(cluster['v_range']);angle=np.deg2rad(json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text())['frame']['u_axis_angle_degrees_ccw_from_easting']);B=np.array([[np.cos(angle),np.sin(angle)],[np.sin(angle),-np.cos(angle)]]);ends=np.array([[u[0]-3,v],[u[1]+9,v]])@B
 rows.append(dict(id='B0',site='B0_b10',prior='LoD2',title='B0 모임지붕 끝 · LoD2',start=ends[0].tolist(),end=ends[1].tolist(),half_width=.25,source=str(source),source_sha256=sha(source),selection='fixed largest B0_wrong cluster of prior work, centre-v cut extending 3m before and 9m after its u range',cluster=cluster))
 source=R/'configs/phd/main_stage1_v1/sections_v1.json';old=json.loads(source.read_text())['sections']['R1_low_roof'];c=np.array(old['centre'][:2]);t=np.array(old['t']);rows.append(dict(id='R1',site=old['site'],prior='LoD2',title='R1 지붕 · LoD2',start=(c-old['L']/2*t).tolist(),end=(c+old['L']/2*t).tolist(),half_width=old['half_width_m'],source=str(source),source_sha256=sha(source),selection='unchanged original R1_low_roof section'))
 dump(C/'input_sections_v1.json',dict(rows=rows,learned_results_used=False,scientific_verdict=None))
if __name__=='__main__':main()
