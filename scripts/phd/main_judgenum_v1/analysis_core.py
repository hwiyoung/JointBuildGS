"""Explicit area-based calibration. Missing numerical inputs stay unavailable."""
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

T2=[.3,.5,.75,1.,1.5,2.,3.,5.,np.inf]

def components(x,radius):
    if not len(x):return np.empty(0,np.int32),0
    pairs=cKDTree(x).query_pairs(radius,output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs),np.int8),(pairs[:,0],pairs[:,1])),shape=(len(x),len(x)))
    count,labels=connected_components(graph,directed=False)
    return labels,count

def grouping(d,j,radius):
    labels=np.full(len(j),-1,np.int64);records=[];offset=0
    for bid in sorted(set(d['building'])):
        b=d['building']==bid
        for value in [0,1,2]:
            ids=np.flatnonzero(b&(j==value))
            if not len(ids):continue
            lab,nc=components(d['centre'][ids],radius);labels[ids]=lab+offset
            areas=np.bincount(lab,weights=d['area'][ids],minlength=nc)
            order=np.argsort(lab,kind='stable');starts=np.r_[0,np.cumsum(np.bincount(lab,minlength=nc))]
            for ci in range(nc):
                ii=ids[order[starts[ci]:starts[ci+1]]]
                records.append({'component':offset+ci,'building':str(bid),'judgment':value,
                    'area_m2':float(areas[ci]),'indices':ii,'kinds':np.unique(d['kind'][ii]).tolist()})
            offset+=nc
    return labels,records

def judgment(d,stats,z):
    n,mean,med,s,nmad,face,raw=stats.T
    a=np.asarray(d['mvs_a_a'],float);a0=np.where(np.isfinite(a),a,0.)
    sigma=d['sigma_p'];DL=np.full(len(n),np.nan)
    have=(n>=4)&np.isfinite(s)&np.isfinite(sigma)
    DL[have]=z*np.sqrt(s[have]**2/n[have]+a0[have]**2+.0275**2+sigma[have]**2)
    j=np.full(len(n),-1,np.int8);j[(n>=0)&(n<4)]=2
    j[have]=(np.abs(mean[have])>DL[have]).astype(np.int8)
    return j,DL

def radius_table(n_by_radius,kind,prior,rs):
    rows=[];chosen={}
    for k in [1,2]:
        m=(kind==k)&(n_by_radius[:,-1]>0)
        index=len(rs)-1;found=False
        for i,r in enumerate(rs):
            values=n_by_radius[m,i]
            qs=np.quantile(values,[.25,.5,.75]) if len(values) else [None]*3
            rows.append({'prior':prior,'kind':k,'radius_m':r,'eligible_cores':int(m.sum()),
              'q25_n':qs[0],'median_n':qs[1],'q75_n':qs[2],
              'fraction_n_lt4':float(np.mean(values<4)) if len(values) else None,
              'all_kind_cores':int((kind==k).sum()),'no_points_at_max_radius':int(((kind==k)&(n_by_radius[:,-1]==0)).sum())})
            if len(values) and qs[1]>=20 and not found:index=i;found=True
        chosen[k]={'radius_index':index,'radius_m':rs[index] if np.any(kind==k) else None,
                   'target_reached':found,'eligible_cores':int(m.sum())}
    return chosen,rows

def minimum_area(d,j,radius):
    result={};maxima=[];ratios=[]
    for kind in [1,2]:
        k=d['kind']==kind;null=k&(d['cell']==0);values=[]
        for bid in sorted(set(d['building'][null])):
            allnull=null&(d['building']==bid);total=float(d['area'][allnull].sum())
            if total<10:continue
            ids=np.flatnonzero(allnull&(j==1));lab,nc=components(d['centre'][ids],radius)
            aa=np.bincount(lab,weights=d['area'][ids],minlength=nc)
            largest=float(aa.max()) if nc else 0.
            values.append(largest)
            maxima.append({'kind':kind,'building':str(bid),'cell0_area_m2':total,'largest_false_component_m2':largest,
              'size_bin':'10~100' if total<=100 else ('100~500' if total<=500 else '>500'),
              'unavailable_area_m2':float(d['area'][allnull&(j<0)].sum())})
        A=float(np.quantile(values,.95,method='higher')) if values else None
        result[kind]=A
        area=float(d['area'][null].sum());different=float(d['area'][null&(j==1)].sum())
        ratios.append({'kind':kind,'cell0_patches':int(null.sum()),'cell0_area_m2':area,
          'false_different_area_m2':different,'false_different_fraction':different/area if area else None,
          'unavailable_area_m2':float(d['area'][null&(j<0)].sum()),
          'minimum_area_m2':A,'buildings_for_A':len(values),'A_gt_1m2':A>1 if A is not None else None,
          'fraction_buildings_above_A':float(np.mean(np.array(values)>A)) if values else None})
    return result,maxima,ratios

def smooth(d,j,A,radius):
    lab,recs=grouping(d,j,radius);after=j.copy();ambiguous=np.zeros(len(j),bool);islands=[]
    for bid in sorted(set(d['building'])):
        ids=np.flatnonzero(d['building']==bid);tree=cKDTree(d['centre'][ids])
        for rec in (r for r in recs if r['building']==bid and r['judgment'] in [0,1]):
            ii=rec['indices'];thresholds=[A[k] for k in rec['kinds']]
            if any(a is None for a in thresholds):
                if rec['judgment']==1:ambiguous[ii]=True;after[ii]=-1
                continue
            small=[rec['area_m2']<a for a in thresholds]
            if not any(small):continue
            if not all(small):
                # Never invent a cutoff for a component spanning roof and wall.
                if rec['judgment']==1:ambiguous[ii]=True;after[ii]=-1
                continue
            neighbours=set()
            for start in range(0,len(ii),1000):
                for q in tree.query_ball_point(d['centre'][ii[start:start+1000]],.36):neighbours.update(q)
            boundary=ids[np.fromiter(neighbours,np.int64)]
            boundary=boundary[lab[boundary]!=rec['component']]
            if rec['judgment']==1:
                boundary=boundary[np.isin(j[boundary],[0,2])]
                if len(boundary):
                    weights=[float(d['area'][boundary[j[boundary]==q]].sum()) for q in [0,2]]
                    after[ii]=[0,2][int(weights[1]>weights[0])]
            elif len(boundary) and np.all(j[boundary]==1):
                for cell in range(7):
                    mm=ii[d['cell'][ii]==cell]
                    if len(mm):islands.append({'building':bid,'component':rec['component'],'cell':cell,
                        'patch_count':len(mm),'area_m2':float(d['area'][mm].sum())})
    loss=[]
    for kind in [1,2]:
        for cell in range(7):
            lost=(d['kind']==kind)&(d['cell']==cell)&(j==1)&np.isin(after,[0,2])
            loss.append({'kind':kind,'cell':cell,'lost_patch_count':int(lost.sum()),'lost_area_m2':float(d['area'][lost].sum())})
    return after,lab,recs,loss,islands,ambiguous

def choice(photo,absolute,threshold):
    return np.where(photo==0,0,np.where(photo==1,1,(absolute>threshold).astype(np.int8))).astype(np.int8)

def best_combo(errors):
    return min(range(135),key=lambda i:(float(errors[i]),-T2[i%9],i//9))

def select(d,after,dist,mask,building_encoding=None):
    eligible=mask&(after==1)&np.isin(d['cell'],[0,1,2])
    bids,bi=np.unique(d['building'],return_inverse=True) if building_encoding is None else building_encoding
    nb=len(bids)
    den=np.bincount(bi[eligible],weights=d['area'][eligible],minlength=nb)
    err=np.zeros((135,nb));total=np.zeros(135);equal=np.full(135,np.nan)
    aa=d['area'][eligible];cells=d['cell'][eligible];bb=bi[eligible];absolute=np.abs(dist[eligible])
    photos=d['photo_judgments'][eligible]
    for pi in range(15):
        photo=photos[:,pi]
        for ti,t in enumerate(T2):
            cc=choice(photo,absolute,t)
            wrong=((cells==1)&(cc==0))|((cells==2)&(cc==1))
            index=pi*9+ti;err[index]=np.bincount(bb[wrong],weights=aa[wrong],minlength=nb)
            total[index]=float(aa[wrong].sum())
            if np.any(den>0):equal[index]=float(np.mean(err[index,den>0]/den[den>0]))
    best=best_combo(total);equal_best=best_combo(np.where(np.isfinite(equal),equal,np.inf))
    # Buildings eligible for leave-one-out are defined by all cell 1/2 area,
    # including cores that did not reach the different judgment.
    a1=np.bincount(bi[mask&(d['cell']==1)],weights=d['area'][mask&(d['cell']==1)],minlength=nb)
    a2=np.bincount(bi[mask&(d['cell']==2)],weights=d['area'][mask&(d['cell']==2)],minlength=nb)
    loo=[]
    for b in np.flatnonzero((a1>1)|(a2>1)):
        new=best_combo(np.maximum(total-err[:,b],0.))
        loo.append({'building':str(bids[b]),'choice_index':new,'changed':new!=best})
    return {'best':best,'building_equal_best':equal_best,'errors':total,'building_equal_errors':equal,
      'denominator_m2':float(d['area'][eligible].sum()),'leave_one_out':loo,
      'eligible_building_count':int((den>0).sum())}

def summaries(d,after,dist,index,mask):
    pi,ti=divmod(index,9);p=d['photo_judgments'][:,pi];pc=np.where(p<2,p,2)
    cc=choice(p,np.abs(dist),T2[ti]);cc[after!=1]=9
    different=mask&(after==1);evaluated=different&np.isin(d['cell'],[0,1,2])
    wrong=evaluated&(((d['cell']==1)&(cc==0))|((d['cell']==2)&(cc==1)))
    den=float(d['area'][evaluated].sum());err=float(d['area'][wrong].sum())
    cross=[]
    for cell in range(7):
        for photo in range(3):
            for select_choice in [0,1]:
                m=different&(d['cell']==cell)&(pc==photo)&(cc==select_choice)
                cross.append({'cell':cell,'photo_judgment':photo,'initial_choice':select_choice,
                  'patch_count':int(m.sum()),'area_m2':float(d['area'][m].sum())})
    buildings=[]
    for bid in sorted(set(d['building'][mask])):
        m=d['building']==bid;a=float(d['area'][evaluated&m].sum());w=float(d['area'][wrong&m].sum())
        buildings.append({'building':str(bid),'different_area_m2':float(d['area'][different&m].sum()),
          'evaluated_area_m2':a,'wrong_area_m2':w,'wrong_fraction':w/a if a else None})
    return cc,{'photo_index':pi,'threshold_index':ti,'threshold2_m':None if not np.isfinite(T2[ti]) else T2[ti],
      'different_area_m2':float(d['area'][different].sum()),'evaluated_area_m2':den,
      'wrong_area_m2':err,'wrong_fraction':err/den if den else None,
      'photo_area_m2':[float(d['area'][different&(pc==k)].sum()) for k in range(3)],
      'wrong_by_photo_m2':[float(d['area'][wrong&(pc==k)].sum()) for k in range(3)],
      'cross':cross,'buildings':buildings}
