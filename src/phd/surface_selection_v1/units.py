"""Source-boundary common refinement. Grid indexes membership, not fitted geometry."""
from collections import defaultdict, deque
import numpy as np


def make_units(native, memberships, components, domain, spacing=.5):
    """Connected constant source-membership regions, including unknown/full ROI.

    Multiple surfaces at one XY location are explicit ambiguity; no topmost/closest
    source is silently chosen. Every input row has one spatial-unit identity.
    """
    low=np.array([domain['x'][0],domain['y'][0]],float)
    high=np.array([domain['x'][1],domain['y'][1]],float)
    shape=np.ceil((high-low)/spacing).astype(int)
    number=int(np.prod(shape));labels={};point_tiles={}
    for source in ('mvs','als'):
        xyz=np.asarray(native[source+'_xyz'])
        indices=np.floor((xyz[:,:2]-low)/spacing).astype(int)
        if ((indices<0)|(indices>=shape)).any():raise ValueError('Native rows outside domain')
        ids=indices[:,1]*shape[0]+indices[:,0];point_tiles[source]=ids
        values=defaultdict(set)
        for tile,member in np.unique(np.column_stack((ids,memberships[source])),axis=0):
            if member>=0:values[int(tile)].add(int(member))
        labels[source]=values
    signatures=[(tuple(sorted(labels['mvs'][i])),tuple(sorted(labels['als'][i]))) for i in range(number)]
    tile_unit=np.full(number,-1,np.int32);units=[]
    def neighbors(t):
        x,y=t%shape[0],t//shape[0]
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            if 0<=x+dx<shape[0] and 0<=y+dy<shape[1]:yield int(t+dy*shape[0]+dx)
    for seed in range(number):
        if tile_unit[seed]>=0:continue
        uid=len(units);todo=deque([seed]);tile_unit[seed]=uid;tiles=[];sig=signatures[seed]
        while todo:
            t=todo.popleft();tiles.append(t)
            for other in neighbors(t):
                if tile_unit[other]<0 and signatures[other]==sig:
                    tile_unit[other]=uid;todo.append(other)
        tiles.sort();ij=np.column_stack((np.asarray(tiles)%shape[0],np.asarray(tiles)//shape[0]))
        xy=low+(ij+.5)*spacing
        boundaries=[t for t in tiles if sum(signatures[n]==sig for n in neighbors(t))<4]
        area=sum(min(spacing,high[0]-(low[0]+int(t%shape[0])*spacing))*min(spacing,high[1]-(low[1]+int(t//shape[0])*spacing)) for t in tiles)
        units.append(dict(id=uid,mvs_ids=list(sig[0]),als_ids=list(sig[1]),tile_ids=tiles,
            footprint_xy=xy.tolist(),boundary_tile_ids=boundaries,
            boundary_xy=(low+(np.column_stack((np.asarray(boundaries)%shape[0],np.asarray(boundaries)//shape[0]))+.5)*spacing).tolist(),
            area_m2=float(area),center=xy.mean(0).tolist(),
            bbox=[*xy.min(0).tolist(),*xy.max(0).tolist()],
            ambiguous=any(len(s)>1 for s in sig),status='AMBIGUOUS_VERTICAL_OVERLAP' if any(len(s)>1 for s in sig) else 'NO_SEGMENTED_SUPPORT' if not any(sig) else 'SINGLE_SOURCE' if not all(sig) else 'PAIRED',
            spacing_m=spacing,native_counts={}))
    rows={s:tile_unit[point_tiles[s]] for s in ('mvs','als')}
    for source in ('mvs','als'):
        counts=np.bincount(rows[source],minlength=len(units))
        for i,n in enumerate(counts):units[i]['native_counts'][source]=int(n)
    edges=defaultdict(int)
    for t in range(number):
        for n in neighbors(t):
            a,b=int(tile_unit[t]),int(tile_unit[n])
            if a<b:edges[a,b]+=1
    graph=dict(nodes=list(range(len(units))),edges=[dict(a=a,b=b,boundary_length_m=count*spacing,
        same_mvs_surface=bool(units[a]['mvs_ids']) and units[a]['mvs_ids']==units[b]['mvs_ids'],
        same_als_surface=bool(units[a]['als_ids']) and units[a]['als_ids']==units[b]['als_ids'],
        aggregation_crossing_allowed=False) for (a,b),count in sorted(edges.items())],
        rule='Evidence aggregates inside connected common refinement only; no label diffusion across source boundaries.')
    return units,dict(**{s+'_unit':rows[s] for s in rows},tile_unit=tile_unit,shape=shape,low=low,spacing=np.array(spacing)),graph


def unit_candidates(unit,native,memberships,unit_memberships,components,contexts=None):
    """Preserve full-source fitted plane, clip only finite native support to unit."""
    result={}
    for source in ('mvs','als'):
        ids=unit[source+'_ids']
        if len(ids)!=1:
            result[source]=dict(valid=False,reason='AMBIGUOUS_OR_MISSING_COMPONENT',support_points=np.empty((0,3)))
            continue
        component=components[source][ids[0]]
        keep=(memberships[source]==ids[0])&(unit_memberships[source+'_unit']==unit['id'])
        points=native[source+'_xyz'][keep]
        result[source]=dict(component,support_points=points,valid=bool(component['valid'] and len(points)>=6),
            context_depths=contexts[source] if contexts else {},native_row_indices=np.flatnonzero(keep))
    return result
