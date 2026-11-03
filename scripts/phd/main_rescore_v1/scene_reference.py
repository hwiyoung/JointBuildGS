"""Recreate missing B173-only reference normals with unchanged AXES71 mathematics."""
from common import *
from geometry import SiteGT,inherit
from scipy.spatial import cKDTree
def main():
 import open3d as o3d
 cfg();start=time.monotonic();site='B173_b0';source='scripts/phd/main_axes71_v2/a1_normals.py';env=dict(np=np);functions=inherit(source,['covs','plane_of'],env);gt=SiteGT(site);out={};rows=[]
 for s,X in gt.X.items():
  name='gt_points' if s==0 else 'gt_primary';use=np.flatnonzero(gt.G['use_'+name]);P=X[use];count=cKDTree(P).query_ball_point(P,.5,workers=4,return_length=True);C=functions['covs'](P,o3d.geometry.KDTreeSearchParamRadius(.5));few=count<10
  if few.any():knn=functions['covs'](P,o3d.geometry.KDTreeSearchParamKNN(10));C[few]=knn[few];del knn
  normal,resid=functions['plane_of'](C);del C;out.update({f'use_{s}':use,f'normal_{s}':normal,f'resid_{s}':resid,f'count_{s}':count});rows.append(dict(source=name,n=len(use),knn_fallback=int(few.sum())))
 p=O/'reference'/f'normals_{site}.npz';savez(p,**out);dump(p.with_suffix('.json'),dict(site=site,source=str(R/source),source_sha256=sha(R/source),fields='same covs/plane_of and radius 0.5 m; <10 uses KNN 10; no change to reference use mask',old_normal_comparison='확인 불가: 이전 B173만 법선 파일 없음',rows=rows,output_sha256=sha(p),scientific_verdict=None));timing('reference_'+site,start)
if __name__=='__main__':main()
