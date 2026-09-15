"""Build dense center decisions in isolated CPU Docker from sealed raw sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
import numpy as np
from PIL import Image
from matplotlib import colormaps

from src.phd import mvs_evidence_v1 as geo
from src.phd import irregular_source_masks_v1 as core
from scripts.phd.mvs_evidence_v1.build import Builder, clean, patch_uv, sha


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(clean(value), ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    temporary.replace(path)


class Inputs(Builder):
    """Reuse the parent hash-bound loaders without creating parent viewer output."""
    def __init__(self, args, cfg):
        self.a = args; self.cfg = cfg; self.bound = {}; self.regional = {}; self.cache = {}
        self.receipt = json.loads(self.bind(args.mvs/'receipt.json', cfg['input_receipt_sha256']).read_text())
        if self.receipt['status'] != 'PASS':
            raise ValueError('MVS binding receipt not PASS')


class DenseBuilder:
    def __init__(self, args):
        self.a = args; self.cfg = json.loads(args.config.read_text()); self.started = time.time()
        if not 1 <= self.cfg['chunk_size'] <= 1024:
            raise ValueError('Center chunk_size must be between 1 and 1024')
        if self.cfg['native_grid_step'] != 1 or self.cfg['profile_excess_cost'] != .03:
            raise ValueError('Native grid and inherited profile excess convention must be preserved')
        if not os.environ.get('JBGS_GIT_COMMIT'):
            raise ValueError('Snapshot runtime requires JBGS_GIT_COMMIT lineage')
        self.out = args.output; self.out.mkdir(parents=True, exist_ok=False)
        self.loader = Inputs(args, self.cfg)
        self.loader.bind(args.config)
        base_config = json.loads(self.loader.bind(Path(self.cfg['source_config_path']),self.cfg['source_config_sha256']).read_text())
        for region,domain in self.cfg['domains'].items():
            if any(domain[axis] != base_config['regions'][region]['domain'][axis] for axis in ('x','y')):
                raise ValueError('Configured XY domain does not equal sealed source configuration')
        parent = json.loads(self.loader.bind(args.parent/'receipt.json', self.cfg['parent_evidence_receipt_sha256']).read_text())
        self.parent_seals = {x['path']: x['sha256'] for x in parent['outputs']}
        self.parent = json.loads(self.checked_parent('manifest.json').read_text())
        self.data = dict(task_id=self.cfg['task_id'], title='픽셀별 비정형 Prior–MVS 판정 후보',
                         status='RUNNING', scientific_verdict=None, config=self.cfg,
                         regions=[dict(id=r,cameras=[]) for r in self.cfg['regions']],
                         limitations=self.cfg['limitations'], created_at=datetime.now(timezone.utc).isoformat(),
                         decision_labels=core.DECISIONS,
                         decision_colors={str(k): '#'+''.join(f'{int(x):02x}' for x in core.COLORS[k,:3]) for k in core.DECISIONS})
        snapshot = self.out/'source_snapshot'; snapshot.mkdir()
        for file in [args.config, Path(__file__), Path(core.__file__), Path(geo.__file__),
                     Path('/repo/scripts/phd/mvs_evidence_v1/build.py'),
                     Path('/repo/src/phd/mvs_surface_update_v1.py'),
                     Path('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py')]:
            self.loader.bind(file)
            relative = Path(str(file).lstrip('/'))
            dest = snapshot/relative; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,dest)
        self.progress(stage='STARTING')

    def checked_parent(self, relative):
        return self.loader.bind(self.a.parent/relative, self.parent_seals[relative])

    def progress(self, **state):
        self.data['progress'] = dict(elapsed_seconds=round(time.time()-self.started, 2), **state)
        write_json(self.out/'data.json', self.data)
        write_json(self.out.parent/'status.txt', dict(status=self.data['status'], task_id=self.cfg['task_id'],
                                                     scientific_verdict=None, **self.data['progress']))
        print(json.dumps(self.data['progress'], ensure_ascii=False), flush=True)

    def publish(self, camera, arrays):
        folder = self.out/camera['folder']
        target = folder/'arrays.npz'; temporary = folder/'arrays.npz.tmp'
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, **arrays)
        temporary.replace(target)
        layers = []
        def layer(key, label, values, cmap='viridis', low=0, high=1, valid=None, categorical=False, palette=None, categories=None):
            if categorical:
                palette = core.COLORS if palette is None else palette
                categories = core.DECISIONS if categories is None else categories
                rgba = palette[values]
            else:
                finite = np.isfinite(values) if valid is None else (valid & np.isfinite(values))
                rgba = (255*colormaps[cmap](np.clip((np.nan_to_num(values)-low)/(high-low),0,1))).astype(np.uint8)
                rgba[...,3] = finite.astype(np.uint8)*195
            path = folder/(key+'.png'); tmp = folder/(key+'.tmp.png')
            Image.fromarray(rgba, 'RGBA').save(tmp); tmp.replace(path)
            legend = ([dict(value=int(k),label=v,color='#'+''.join(f'{int(x):02x}' for x in palette[k,:3]))
                       for k,v in categories.items()] if categorical else
                      [dict(value=v,label=str(v),color='#'+''.join(f'{int(x):02x}' for x in (255*np.asarray(colormaps[cmap](t))[:3]).astype(int)))
                       for t,v in [(0,low),(.5,(low+high)/2),(1,high)]])
            descriptions = {
                'delta':'같은 정수 RGB 광선의 Prior−MVS camera-Z 깊이차. 시간 변화 확정 아님.',
                'prior_depth':'기구축 Prior camera-Z 깊이. MVS와 동일한 색상 범위이며 raw ray 관례를 보존.',
                'mvs_depth':'현재 영상 MVS camera-Z 깊이. Prior와 동일한 색상 범위이며 native MVS nearest 조회.',
                'validity':'0 둘 다 없음 / 1 Prior만 / 2 MVS만 / 3 둘 다. 존재는 정확성이나 현재성을 뜻하지 않음.',
                'candidate':'두 깊이가 존재하고 절대 깊이차가 0.5m를 넘는 픽셀. 영역 경계 정답 아님.',
                'roi':'두 원시 소스 중 하나 이상이 고정된 지역 XY 범위에 들어오는 픽셀. Z/평가 정답 미사용.',
                'decision':'각 픽셀 자체의 관측 근거로 판정. 7×7 창은 비용 계산에만 쓰며 이웃 픽셀로 판정을 퍼뜨리지 않음.',
                'mvs_support':'곡선 검사 전, 같은 이웃의 두 깊이 호환성·시차·사진 비용이 MVS를 지지하는 수.',
                'prior_support':'곡선 검사 전, 같은 이웃의 두 깊이 호환성·시차·사진 비용이 Prior를 지지하는 수.',
                'profile_mvs_support':'전체 깊이곡선의 공통 지지 조건까지 통과한 이웃 중 MVS 지지 수. 최종 판정용.',
                'profile_prior_support':'전체 깊이곡선의 공통 지지 조건까지 통과한 이웃 중 Prior 지지 수. 최종 판정용.',
                'admitted_neighbors':'두 깊이 가설 모두 자기 소스 깊이와 호환되고 시차·공통 사진 비용이 유효한 같은 이웃 수. 실제 가시성 정답 아님.',
                'dissent':'같은 픽셀에 MVS 지지와 Prior 지지가 함께 존재함. 다수결 통과에도 반대는 보존됨.',
                'profile_width':'최저 비용+0.03 이하인 이산 깊이 구간 폭. 0은 한 격자점이며 불확실성 0이 아님.',
                'profile_cost':'반대·중립을 포함한 모든 허용 이웃으로 집계한 깊이곡선 최저 비용.',
                'profile_boundary':'저비용 깊이 구간이 탐색 끝에 닿으면 1. 이 경우 최종 소스 판정 유보.',
                'profile_spacing':'최저 비용점 주변의 이산 깊이 간격. 0.25m를 넘으면 최종 판정 유보.',
                'profile_support':'두 normal 분기와 33 깊이 가설 전체에서 완전한 공통 패치를 갖는 허용 이웃 수.',
                'profiled':'이 픽셀 자체의 깊이곡선 계산을 수행했음. 정확한 대응이라는 뜻은 아님.'}
            layers.append(dict(id=key,label=label,path=str(path.relative_to(self.out)),legend=legend,
                               description=descriptions.get(key,''),
                               vmin=low,vmax=high,units='camera-Z m' if 'depth' in key or key=='delta' else 'diagnostic'))
        layer('delta', '1 · 전체 깊이 불일치', arrays['delta'], 'PuOr_r', -5, 5)
        depth_low,depth_high = camera['depth_display_range_m']
        layer('prior_depth','1 · Prior 깊이',arrays['prior_depth'],'viridis',depth_low,depth_high)
        layer('mvs_depth','1 · MVS 깊이',arrays['mvs_depth'],'viridis',depth_low,depth_high)
        layer('validity','1 · 입력 존재 영역',arrays['prior_valid'].astype(np.uint8)+2*arrays['mvs_valid'].astype(np.uint8),categorical=True,
              palette=np.array([[90,99,112,120],[58,129,234,175],[244,145,46,175],[126,84,180,175]],np.uint8),
              categories={0:'둘 다 없음',1:'Prior만 존재',2:'MVS만 존재',3:'두 깊이 모두 존재'})
        layer('candidate', '1 · 전체 불일치 후보', arrays['candidate'], 'Oranges', valid=arrays['both_valid']&arrays['candidate'])
        layer('roi', '검사할 고정 XY 범위', arrays['roi'], 'Blues', valid=arrays['roi'])
        layer('decision', '4 · 픽셀별 소스 판정', arrays['decision'], categorical=True)
        for key,label,cmap,hi in [('mvs_support','3 · MVS 지지 이웃 수','YlOrBr',8),
                                  ('prior_support','3 · Prior 지지 이웃 수','Blues',8),
                                  ('dissent','3 · 지지·반대 공존','Reds',1),
                                  ('admitted_neighbors','2 · 비교 가능한 이웃 수','viridis',8),
                                  ('profile_width','3 · 깊이 비용구간 폭','magma',2),
                                  ('profile_cost','3 · 깊이 최저 비용','magma',.4),
                                  ('profile_boundary','3 · 깊이 탐색경계 접촉','Reds',1),
                                  ('profile_spacing','3 · 최저점 주변 깊이 간격','magma',.5),
                                  ('profile_support','3 · 곡선 완전지지 이웃 수','viridis',8),
                                  ('profile_mvs_support','3 · 최종 MVS 지지 이웃 수','YlOrBr',8),
                                  ('profile_prior_support','3 · 최종 Prior 지지 이웃 수','Blues',8),
                                  ('profiled','비용곡선 검사 완료','Greens',1)]:
            valid = arrays['photo_examined'] if key in ('mvs_support','prior_support','dissent','admitted_neighbors') else arrays['profiled']
            layer(key,label,arrays[key],cmap,0,hi,valid)
        camera['layers'] = layers
        camera['counts'] = {name:int((arrays['decision']==code).sum()) for code,name in core.DECISIONS.items()}
        camera['counts'].update(full_pixels=int(arrays['decision'].size), both_valid=int(arrays['both_valid'].sum()),
                                candidate_full=int(arrays['candidate'].sum()), roi=int(arrays['roi'].sum()),
                                candidate_roi=int((arrays['candidate']&arrays['roi']).sum()),
                                photo_examined=int(arrays['photo_examined'].sum()), profiled=int(arrays['profiled'].sum()),
                                disagreement=int(arrays['dissent'].sum()))
        write_json(folder/'camera.json', camera)

    def camera(self, region, parent_camera, ordinal, region_row):
        cfg = self.cfg; loader = self.loader
        parent_path = f'{region}/view_{ordinal:02d}/camera.json'
        pc = json.loads(self.checked_parent(parent_path).read_text())
        if pc['name'] != parent_camera['name']:
            raise ValueError('Parent camera membership mismatch')
        ref = loader.load(region, pc['name']); view = ref['view']; w,h = view['width'],view['height']
        neighbor_names = pc['neighbors'][:cfg['maximum_neighbors']]
        bound_names = loader.regional[region]['binding']['neighbor_graph']['graph'][pc['name']]['selected'][:cfg['maximum_neighbors']]
        if neighbor_names != bound_names:
            raise ValueError('Parent neighbor membership differs from bound graph')
        neighbors = [loader.load(region,n) for n in neighbor_names]
        for item in [ref]+neighbors:
            if not np.isfinite(item['gray']).all() or np.any((item['gray']<0)|(item['gray']>1)):
                raise ValueError('Input grayscale outside finite [0,1]')
        relative = f'{region}/view_{ordinal:03d}'; folder = self.out/relative; folder.mkdir(parents=True)
        shutil.copy2(ref['photo'], folder/'rgb.jpg')
        camera = dict(id=f'view_{ordinal:03d}',original_id=pc['id'],observation_label=pc['id'],name=pc['name'],width=w,height=h,folder=relative,
                      rgb=relative+'/rgb.jpg',arrays=relative+'/arrays.npz',status='RUNNING',layers=[],counts={},
                      neighbors=neighbor_names,scientific_verdict=None,domain=cfg['domains'][region],
                      native_grid_step=1,patch_is_measurement_support_only=True,reference_gt_used=False,
                      crs=loader.regional[region]['manifest']['crs'])
        region_row['cameras'].append(camera)
        yy,xx = np.mgrid[:h,:w]; uv = np.stack([xx,yy],-1)
        pd,pv = geo.sample_prior(ref['prior'],uv); md,mv = geo.sample_mvs(ref['mvs'],uv,view)
        finite_depths = np.concatenate([pd[pv],md[mv]])
        camera['depth_display_range_m'] = ([float(finite_depths.min()),float(finite_depths.max())]
                                           if len(finite_depths) and np.ptp(finite_depths)>0 else [0.,1.])
        xp = geo.project(uv,pd,view,view)[2]; roi_p = core.inside_xy(xp,cfg['domains'][region]); del xp
        xm = geo.project(uv,md,view,view)[2]; roi_m = core.inside_xy(xm,cfg['domains'][region]); del xm
        roi = roi_p|roi_m; decision,candidate = core.initial_decisions(pd,md,roi,cfg['candidate_threshold_m'])
        roi_y,roi_x = np.nonzero(roi)
        camera['roi_bbox'] = ([int(roi_x.min()),int(roi_y.min()),int(roi_x.max()+1),int(roi_y.max()+1)]
                              if len(roi_x) else [0,0,w,h])
        arrays = dict(prior_depth=pd.astype(np.float32),mvs_depth=md.astype(np.float32),delta=(pd-md).astype(np.float32),
                      both_valid=pv&mv,prior_valid=pv,mvs_valid=mv,candidate=candidate,roi=roi,
                      prior_in_roi=roi_p,mvs_in_roi=roi_m,decision=decision,
                      photo_examined=np.zeros((h,w),bool),profiled=np.zeros((h,w),bool),
                      mvs_support=np.zeros((h,w),np.uint8),prior_support=np.zeros((h,w),np.uint8),
                      admitted_neighbors=np.zeros((h,w),np.uint8),profile_support=np.zeros((h,w),np.uint8),
                      profile_mvs_support=np.zeros((h,w),np.uint8),profile_prior_support=np.zeros((h,w),np.uint8),
                      dissent=np.zeros((h,w),bool))
        for key in ('width','cost','boundary','edge','spacing','best','modes'):
            arrays['profile_'+key] = np.full((h,w),np.nan,np.float32)
        for key,dtype in [('prior_self_status',np.uint8),('mvs_self_status',np.uint8),
                          ('prior_to_mvs_status',np.uint8),('photo_common_count',np.uint8)]:
            arrays[key] = np.zeros((len(neighbors),h,w),dtype)
        for key in ('photo_margin','parallax_min_deg','mvs_roundtrip_px'):
            arrays[key] = np.full((len(neighbors),h,w),np.nan,np.float64 if key=='photo_margin' else np.float32)
        arrays['neighbor_admitted'] = np.zeros((len(neighbors),h,w),bool)
        arrays['neighbor_profile_admitted'] = np.zeros((len(neighbors),h,w),bool)
        rows,cols = np.nonzero(candidate&roi); centers = np.stack([cols,rows],-1).astype(float)
        self.publish(camera,arrays); self.progress(region=region,camera=camera['id'],stage='DENSE_PHOTOMETRY',processed=0,total=len(rows))
        chunk = cfg['chunk_size']; last_publish = time.time(); profile_positions = []
        for start in range(0,len(rows),chunk):
            stop = min(start+chunk,len(rows)); c = centers[start:stop]; ry,rx = rows[start:stop],cols[start:stop]
            p,m = pd[ry,rx],md[ry,rx]; puv = patch_uv(c,cfg['patch_radius'])
            pp = geo.sample_prior(ref['prior'],puv)[0]; mp = geo.sample_mvs(ref['mvs'],puv,view)[0]
            margins=[]; admitted=[]
            for ni,nb in enumerate(neighbors):
                vp = geo.visibility(c,p,view,nb['view'],nb['prior'],cfg['depth_tolerance_m'],neighbor_kind='prior')
                vm = geo.visibility(c,m,view,nb['view'],nb['mvs'],cfg['depth_tolerance_m'])
                cross = geo.visibility(c,p,view,nb['view'],nb['mvs'],cfg['depth_tolerance_m'])
                pair = core.paired_costs(c,p,m,pp,mp,ref,nb,cfg)
                margin = pair['costs'][:,0]-pair['costs'][:,1]
                angle = np.minimum(vp['parallax_deg'],vm['parallax_deg'])
                allowed = ((vp['status']==3)&(vm['status']==3)&np.isfinite(margin)
                           &np.isfinite(angle)&(angle>=cfg['minimum_patch_parallax_degrees']))
                for key,val in [('prior_self_status',vp['status']),('mvs_self_status',vm['status']),
                                ('prior_to_mvs_status',cross['status']),('photo_common_count',pair['common_count']),
                                ('photo_margin',margin),('parallax_min_deg',angle),
                                ('mvs_roundtrip_px',vm['roundtrip_px']),('neighbor_admitted',allowed)]:
                    arrays[key][ni,ry,rx] = val
                margins.append(margin); admitted.append(allowed)
            vote = core.votes(np.stack(margins),np.stack(admitted),cfg['minimum_photo_margin'],cfg['minimum_joint_views'])
            arrays['mvs_support'][ry,rx] = vote['mvs']; arrays['prior_support'][ry,rx] = vote['prior']
            arrays['admitted_neighbors'][ry,rx] = vote['admitted']; arrays['dissent'][ry,rx] = vote['dissent']
            arrays['photo_examined'][ry,rx] = True
            pre = vote['profile_candidate']
            arrays['decision'][ry[~pre],rx[~pre]] = 4
            profile_positions.extend((np.flatnonzero(pre)+start).tolist())
            if time.time()-last_publish > 60 or stop==len(rows):
                self.publish(camera,arrays); self.progress(region=region,camera=camera['id'],stage='DENSE_PHOTOMETRY',processed=stop,total=len(rows),profile_candidates=len(profile_positions)); last_publish=time.time()
        profile_positions = np.asarray(profile_positions,int)
        self.progress(region=region,camera=camera['id'],stage='DENSE_AMBIGUITY',processed=0,total=len(profile_positions))
        for start in range(0,len(profile_positions),chunk):
            positions = profile_positions[start:start+chunk]; c = centers[positions]
            ry,rx = rows[positions],cols[positions]; p,m = pd[ry,rx],md[ry,rx]
            puv = patch_uv(c,cfg['patch_radius']); pp = geo.sample_prior(ref['prior'],puv)[0]; mp = geo.sample_mvs(ref['mvs'],puv,view)[0]
            eligible = arrays['neighbor_admitted'][:,ry,rx]
            depths,raw = core.source_profiles(c,p,m,pp,mp,ref,neighbors,eligible,cfg)
            assessed = core.decide_profiles(p,m,arrays['photo_margin'][:,ry,rx],eligible,depths,raw,cfg)
            arrays['decision'][ry,rx] = assessed['decision']; arrays['profiled'][ry,rx] = True
            arrays['neighbor_profile_admitted'][:,ry,rx] = assessed['admitted']
            arrays['profile_support'][ry,rx] = assessed['votes']['admitted']
            arrays['profile_mvs_support'][ry,rx] = assessed['votes']['mvs']
            arrays['profile_prior_support'][ry,rx] = assessed['votes']['prior']
            for key,val in assessed['stats'].items(): arrays['profile_'+key][ry,rx] = val
            stop = min(start+chunk,len(profile_positions))
            if time.time()-last_publish > 60 or stop==len(profile_positions):
                self.publish(camera,arrays); self.progress(region=region,camera=camera['id'],stage='DENSE_AMBIGUITY',processed=stop,total=len(profile_positions)); last_publish=time.time()
        if np.any(arrays['decision']==3):
            raise ValueError('Unassessed candidate pixels remain at camera completion')
        camera['status']='COMPLETE_DIAGNOSTIC'; self.publish(camera,arrays)
        self.progress(region=region,camera=camera['id'],stage='CAMERA_COMPLETE',counts=camera['counts'])
        loader.cache.clear()

    def run(self):
        for region in self.cfg['regions']:
            self.loader.setup_region(region)
            if self.loader.regional[region]['manifest']['config_sha256'] != self.cfg['source_config_sha256']:
                raise ValueError('Frozen XY source configuration lineage mismatch')
            parent_region = next(r for r in self.parent['regions'] if r['id']==region)
            if len(parent_region['cameras']) != 3:
                raise ValueError('Expected exactly three sealed parent reference cameras')
            row=next(r for r in self.data['regions'] if r['id']==region)
            for index,camera in enumerate(parent_region['cameras'],1):
                self.camera(region,camera,index,row)
        for item in self.loader.bound.values():
            if sha(item['path']) != item['sha256']:
                raise ValueError('Bound source changed during run: '+item['path'])
        self.data['status']='COMPLETE_DIAGNOSTIC'; self.progress(stage='COMPLETE_DIAGNOSTIC')
        outputs=[dict(path=str(p.relative_to(self.out)),sha256=sha(p),bytes=p.stat().st_size)
                 for p in sorted(self.out.rglob('*')) if p.is_file()]
        write_json(self.out/'receipt.json',dict(task_id=self.cfg['task_id'],status='PASS_DENSE_CENTER_DIAGNOSTIC',
                   scientific_verdict=None,elapsed_seconds=time.time()-self.started,inputs=list(self.loader.bound.values()),
                   outputs=outputs,gt_accessed=False,training_started=False,gaussians_modified=False,
                   native_grid_step=1,patch_labels_propagated=False,source_selection_accuracy_validated=False,
                   runtime=dict(image_id=self.cfg['runtime_image_id'],numpy=np.__version__),
                   git_commit=os.environ.get('JBGS_GIT_COMMIT','UNKNOWN_SNAPSHOT_COMMIT')))


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker CPU execution required')
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('config','inputs','mvs','parent','output'): ap.add_argument('--'+key,type=Path,required=True)
    args=ap.parse_args()
    try:
        DenseBuilder(args).run()
    except Exception as exc:
        if args.output.exists():
            write_json(args.output/'failure.json',dict(error=type(exc).__name__,message=str(exc),scientific_verdict=None))
            write_json(args.output.parent/'status.txt',dict(status='FAILED',error=type(exc).__name__,message=str(exc),scientific_verdict=None))
        raise


if __name__=='__main__': main()
