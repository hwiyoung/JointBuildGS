"""17:00 user amendment: stage-1 rules, C.5 edge and C.4 optima.

Pure array functions; the rule for edge distance is deliberately independent
of UNCERT's historical (different-surface-centre) edge field.
"""
import numpy as np
from scipy.ndimage import binary_closing, maximum_filter, minimum_filter, distance_transform_edt

RULES = dict(
    revision='direct_stage1_v2', authority='user supplied 2026-10-26 17:00 amendment, sections 5, 6.4, C.5',
    normal_source='retain UNCERT normals; zero-tangent loc_extra patches read the exact owning prior surface normal from the stage-1 source table; no GT or nearest-surface substitution',
    source='PHD-MAIN-UNCERT-v1/patch_values; R1.5; mvs_a',
    coordinate='EPSG:25832 minus [690953, 5336071, 604] m; registered stage-1 patch centres',
    floor_m=.0275, sigma_lod2_m={'1000':.166113,'2100':.098442,'3100':.222725,
        '3200':.113508,'3900':.238359,'other':.110188,'wall':.143818},
    mvs_u_edges_cm=[3,5,10,20,40],
    v_mvs={'LoD2':[.98,.921922,.889803,.900378,.956689,.974928],
           'ALS':[.98,.974468,.952001,.908804,.878294,.866188]},
    v_prior_now={'LoD2':[.849780,.918237,.852455,.955338,.918365,.979117,.915068],
        'ALS':[.98,.975461,.726890,.98,.98,.564979,.98,.978882,.599285]},
    edge=dict(cell_m=.5,origin_xy_m=[-170,-237],height_jump_m=1.,neighbourhood=3,
        closing_iterations=1,subtract_m=.25,roof_max_angle_degrees=45,
        empty_grid_padding_cells=3,negative_distance='retain -0.25 m at edge cells, as specified'),
    edge_bins_m=[.5,1.5],als_u_bins_m=[.01,.03],
    prior_tau_m={'LoD2':.2,'ALS':.1266},
    oracle=dict(right_cells=[0,2,4],wrong_cells=[1,3,5],gt=[.999,.001],soft=[.98,.85],
        cell6='use now; excluded from scoring'),
    missing=dict(mvs='no MVS term when p_M or u_M missing, or u_M <= 0',
        als_prior='independent medians of sigma_prior and v_prior_now from known u_prior in same unit; exclude scoring',
        outside_uncert='LoD2 prior from geometry, MVS sigma/V unit medians; ALS all four unit medians; oracle uses now; exclude scoring',
        no_pixel_patch='no depth term'),
    gates=dict(coverage_min_area_fraction=.95,coverage_denominator='stage-1 in_eval area',
        coverage_numerator='prior sigma and stratum from rule without missing-ALS/outside-UNCERT median fallback',
        lod2_max_nearest_m=.01,lod2_sigma_tolerance_m=.0001,lod2_validity_tolerance=.0001,
        lod2_min_pair_agreement=.90,lod2_denominator='whole-scene nearest pairs within 1 cm; each of three units',
        mvs='distribution only; not a stop gate'),
    legacy_connections='5 cm and 18 cm records remain historical; unused for training or scoring',
    scientific_verdict=None)

def edge_distance(centre, normal):
    """C.5 on this prior's complete scene; padded empty cells are true edges."""
    c=np.asarray(centre,np.float64);n=np.asarray(normal,np.float64)
    ij=np.floor((c[:,:2]-np.array(RULES['edge']['origin_xy_m']))/.5).astype(np.int64)
    low=ij.min(0)-3;hi=ij.max(0)+3
    q=ij-low;shape=tuple(hi-low+1)
    roof=np.isfinite(n).all(1)&(np.abs(n[:,2])>=np.cos(np.pi/4))
    H=np.full(shape,-np.inf);L=np.full(shape,np.inf);occ=np.zeros(shape,bool)
    qr=q[roof];z=c[roof,2]
    np.maximum.at(H,(qr[:,0],qr[:,1]),z);np.minimum.at(L,(qr[:,0],qr[:,1]),z)
    occ[qr[:,0],qr[:,1]]=True
    hmax=maximum_filter(H,size=3,mode='constant',cval=-np.inf)
    hmin=minimum_filter(L,size=3,mode='constant',cval=np.inf)
    occ2=binary_closing(occ,structure=np.ones((3,3),bool),iterations=1)|occ
    edge=(~occ2)|((hmax-hmin)>1.)
    d=distance_transform_edt(~edge)*.5-.25
    return d[q[:,0],q[:,1]],roof

def prior_values(prior, edge, roof, roof_type, up):
    e=np.searchsorted([.5,1.5],edge,side='right')
    if prior=='LoD2':
        rt=np.asarray(roof_type,str)
        sigma=np.array([RULES['sigma_lod2_m'].get(x,RULES['sigma_lod2_m']['other']) for x in rt])
        sigma[~roof]=RULES['sigma_lod2_m']['wall']
        strata=np.where(roof,2*e+(rt=='1000'),6).astype(np.int8)
    else:
        sigma=np.sqrt(up**2+RULES['floor_m']**2)
        q=np.searchsorted([.01,.03],up,side='right')
        strata=(3*e+q).astype(np.int8)
    validity=np.asarray(RULES['v_prior_now'][prior])[strata]
    return sigma,validity,strata,e.astype(np.int8)

def mixloss(z,zi,s,v):
    return -np.logaddexp(np.log(v)-np.log(s)-.5*np.log(2*np.pi)-.5*((z-zi)/s)**2,np.log1p(-v)+np.log(.1))

def irls(D,sp,sm,Vp,Vm,z,it=40):
    for _ in range(it):
        Np=np.exp(-z**2/(2*sp**2))/(sp*np.sqrt(2*np.pi))
        Nm=np.exp(-(z-D)**2/(2*sm**2))/(sm*np.sqrt(2*np.pi))
        rp=Vp*Np/(Vp*Np+(1-Vp)*.1);rm=Vm*Nm/(Vm*Nm+(1-Vm)*.1)
        z=(rm/sm**2*D)/(rp/sp**2+rm/sm**2+1e-300)
    return z

def optimum(mode,D,sp,sm,Vp,Vm):
    if mode=='fixed':return (Vm/sm**2)/(Vm/sm**2+Vp/sp**2)*D
    z1=irls(D,sp,sm,Vp,Vm,np.zeros_like(D));z2=irls(D,sp,sm,Vp,Vm,D.copy())
    L1=mixloss(z1,0,sp,Vp)+mixloss(z1,D,sm,Vm)
    L2=mixloss(z2,0,sp,Vp)+mixloss(z2,D,sm,Vm)
    return np.where(L1<=L2,z1,z2)
