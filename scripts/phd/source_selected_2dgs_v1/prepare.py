"""Freeze source-selected observations and paired raw surface seeds, CPU only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time

import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from src.phd import mvs_evidence_v1 as sampling
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import read_colmap_depth
from src.phd.source_selected_2dgs_v1 import evidence as ev


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, np.ndarray): return clean(x.tolist())
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, (float, np.floating)): return float(x) if np.isfinite(x) else None
    return x


def write(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n')


class BoundInputs:
    def __init__(self, args, cfg):
        self.a, self.cfg, self.bound, self.regions = args, cfg, {}, {}
        self.bind(args.config)
        self.bind(args.base_config)
        technical = args.primary.parent/'technical_result_manifest_v1.json'
        self.bind(technical, cfg['inputs']['parent_technical_manifest_sha256'])
        self.mreceipt = json.loads(self.bind(args.mvs/'receipt.json').read_text())
        if self.mreceipt['status'] != 'PASS': raise ValueError('MVS inputs are not sealed PASS')
        self.ereceipt = json.loads(self.bind(args.evidence/'receipt.json').read_text())
        self.eseals = {x['path']: x['sha256'] for x in self.ereceipt['outputs']}
        self.cases = []
        for tag, folder in [('primary', args.primary), ('screen', args.screen)]:
            receipt = json.loads(self.bind(folder/'receipt.json').read_text())
            if receipt['status'] != 'PASS_PREPARED_CASES': raise ValueError('Parent cases not prepared')
            self.bind(folder/'config.json', receipt['config_sha256'])
            parent_cfg = json.loads((folder/'config.json').read_text())
            if sha(args.evidence/'receipt.json') != parent_cfg['parent_evidence_receipt_sha256']:
                raise ValueError('Observation evidence receipt mismatch')
            cases = json.loads(self.bind(folder/'cases.json', receipt['cases_sha256']).read_text())
            self.cases.append((tag, cases))
        expected_mvs = json.loads(self.bind(args.evidence/'config.json').read_text())['input_receipt_sha256']
        self.bind(args.mvs/'receipt.json', expected_mvs)

    def bind(self, path, expected=None):
        path = Path(path); digest = sha(path)
        if expected is not None and expected != digest: raise ValueError('SHA mismatch: '+str(path))
        self.bound[str(path)] = dict(path=str(path), sha256=digest, bytes=path.stat().st_size)
        return path

    def observation_file(self, path):
        return self.bind(path, self.eseals[str(path.relative_to(self.a.evidence))])

    def setup(self, region):
        binding = json.loads(self.bind(self.a.mvs/region/'bindings.json', self.mreceipt['regions'][region]['binding_sha256']).read_text())
        manifest = json.loads(self.bind(self.a.inputs/region/'input_manifest.json', binding['parent_input_manifest_sha256']).read_text())
        if manifest['config_sha256'] != sha(self.a.base_config): raise ValueError('Frozen XY/base config mismatch')
        if manifest['source_role'] != self.cfg['inputs']['prior_role']: raise ValueError('Prior input role mismatch')
        views = {v['name']: v for v in binding['train']}
        if set(views) & set(binding['evaluation_names']): raise ValueError('Train/evaluation binding overlap')
        seals = {x['path']: x['sha256'] for x in manifest['files']}
        self.regions[region] = dict(binding=binding, manifest=manifest, views=views, seals=seals)
        return views

    def load(self, region, name):
        reg = self.regions[region]; cam = reg['views'][name]
        rgbrel = 'scene/images/'+name; priorrel = 'prior/raw_depth/'+Path(name).stem+'.npy'
        if reg['seals'][rgbrel] != cam['sha256']: raise ValueError('RGB binding differs')
        rgbpath = self.bind(self.a.inputs/region/rgbrel, cam['sha256'])
        rgb = np.asarray(Image.open(rgbpath).convert('RGB'), dtype=np.uint8)
        prior = np.load(self.bind(self.a.inputs/region/priorrel, reg['seals'][priorrel]), allow_pickle=False)
        native = read_colmap_depth(self.bind(self.a.mvs/region/cam['local_depth'], cam['maps']['depth']['sha256']), cam['maps']['depth'])
        h, w = int(cam['height']), int(cam['width'])
        if rgb.shape != (h, w, 3): raise ValueError('RGB dimensions differ')
        yy, xx = np.mgrid[:h, :w]; uv = np.stack((xx, yy), -1)
        pd = sampling.sample_prior(prior, uv)[0].astype(np.float32)
        md = sampling.sample_mvs(native, uv, cam)[0].astype(np.float32)
        pn, pnv = ev.normals_from_depth(cam, pd); mn, mnv = ev.normals_from_depth(cam, md)
        return dict(camera=cam, rgb=rgb, uv=uv, prior_depth=pd, mvs_depth=md,
                    prior_normal=pn, mvs_normal=mn, prior_normal_valid=pnv, mvs_normal_valid=mnv,
                    prior_xyz=ev.world_points(cam, uv, pd), mvs_xyz=ev.world_points(cam, uv, md))


def unique_cases(tagged, region):
    """Duplicate primary/screen examples share the same immutable observation ID."""
    result = {}
    for tag, document in tagged:
        for rr in document['regions']:
            if rr['id'] != region: continue
            for original in rr['cases']:
                c = dict(original); s = c['selection']; key = (s['camera'], int(s['point']))
                if key in result:
                    if result[key]['decision'] != c['decision'] or result[key]['bbox'] != c['bbox']:
                        raise ValueError('Repeated observation has different source decision')
                    result[key]['parents'].append(dict(set=tag, case_id=c['case_id']))
                else:
                    c['observation_id'] = f'{s["camera"]}_point_{s["point"]}'
                    c['parents'] = [dict(set=tag, case_id=c['case_id'])]
                    result[key] = c
    return [result[k] for k in sorted(result)]


def source_samples(data, region, kind, mask, exact):
    prefix = 'prior' if kind == 0 else 'mvs'; cam = data['camera']
    good = mask & data[prefix+'_normal_valid'] & np.isfinite(data[prefix+'_depth']) & (data[prefix+'_depth'] > 0)
    uv = data['uv'][good]; z = data[prefix+'_depth'][good]
    # Frozen geometric-mean spacing on the constant-camera-Z sample plane.
    spacing = z/np.sqrt(float(cam['K'][0][0])*float(cam['K'][1][1]))
    stride = np.where(exact[good], 1., 8.)
    return dict(xyz=data[prefix+'_xyz'][good].astype(np.float32), rgb=data['rgb'][good].astype(np.float32)/255.,
                normal=data[prefix+'_normal'][good], scale=(.5*spacing*stride).astype(np.float32),
                source_kind=np.full(int(good.sum()), kind, dtype=np.uint8),
                stable_source_id=ev.stable_ids(int(region[1:]), int(cam['image_id']), int(cam['width']), uv, kind)), good


def concatenate(parts):
    return {k: np.concatenate([p[k] for p in parts], axis=0) for k in parts[0]}


def crop_for(mask):
    y, x = np.where(mask)
    if not len(x): return np.s_[:, :]
    return np.s_[max(0, y.min()-8):y.max()+9, max(0, x.min()-8):x.max()+9]


def plot_stages(out, region, reference_data, observations, prior, selected, replacement, summaries):
    n = len(reference_data)
    fig, axes = plt.subplots(n, 3, figsize=(12, 4*n), squeeze=False)
    for row, (name, d) in enumerate(reference_data.items()):
        crop = crop_for(d['photo_mask']); finite = np.r_[d['prior_depth'][d['photo_mask']], d['mvs_depth'][d['photo_mask']]]
        finite = finite[np.isfinite(finite)]; lo, hi = np.percentile(finite, [2, 98]) if len(finite) else (0, 1)
        for ax, arr, title in zip(axes[row], [d['rgb'], d['prior_depth'], d['mvs_depth']], ['Current RGB', 'Prior camera-Z (m)', 'MVS camera-Z (m)']):
            im = ax.imshow(arr[crop], **({} if arr.ndim == 3 else dict(vmin=lo, vmax=hi, cmap='viridis')))
            if arr.ndim == 2: fig.colorbar(im, ax=ax, fraction=.04)
            ax.set_title(title); ax.axis('off')
        axes[row, 0].text(0, -.06, name, transform=axes[row, 0].transAxes, fontsize=8)
    fig.suptitle(region+' | 01 Raw inputs on identical integer RGB rays; XY crop only'); fig.tight_layout(); fig.savefig(out/'01_inputs.png', dpi=130); plt.close(fig)
    fig, axes = plt.subplots(n, 2, figsize=(9, 4*n), squeeze=False)
    for row, (name, d) in enumerate(reference_data.items()):
        crop = crop_for(d['photo_mask']); delta = np.where(d['photo_mask'], d['prior_depth']-d['mvs_depth'], np.nan)
        im = axes[row, 0].imshow(delta[crop], vmin=-2, vmax=2, cmap='coolwarm'); fig.colorbar(im, ax=axes[row, 0], fraction=.04)
        axes[row, 0].set_title('Prior - MVS (m), saturated at +/-2')
        axes[row, 1].imshow((np.abs(delta) > .5)[crop], vmin=0, vmax=1, cmap='Greys'); axes[row, 1].set_title('|Difference| > 0.5 m: candidate only')
        for ax in axes[row]: ax.axis('off')
    fig.suptitle(region+' | 02 Disagreement does not identify temporal change or authority'); fig.tight_layout(); fig.savefig(out/'02_conflict.png', dpi=130); plt.close(fig)
    rows = []
    for c in observations:
        ns = c['neighbor_evidence']; ps = c['profile_stats']
        fmt = lambda x: '-' if x is None else f'{x:.3f}'
        rows.append([c['observation_id'], c['decision'].replace('IMAGE_SUPPORTED_LOCAL_PROBE', 'MVS selected'),
                     str(sum(bool(x['admitted']) for x in ns)), str(sum(bool(x['supports_mvs']) for x in ns)),
                     str(sum(bool(x['opposes_mvs']) for x in ns)), fmt(ps.get('minimum_cost', ps.get('cost'))),
                     fmt(ps.get('width')), str(ps.get('modes'))])
    fig, ax = plt.subplots(figsize=(13, max(3, len(rows)*.42+1.5))); ax.axis('off')
    tab = ax.table(cellText=rows, colLabels=['Frozen observation', 'Decision', 'Admitted\nviews', 'MVS +\nviews', 'Opposing\nviews', 'Min cost', 'Width m', 'Modes'], loc='center', cellLoc='left', colWidths=[.24,.24,.085,.08,.08,.09,.09,.07]); tab.auto_set_font_size(False); tab.set_fontsize(8); tab.scale(1, 1.65)
    fig.suptitle(region+' | 03 Frozen joint visibility/photo/profile checks; all opposing evidence retained'); fig.tight_layout(); fig.savefig(out/'03_evidence.png', dpi=135); plt.close(fig)
    cmap = ListedColormap(['#555555','#2563eb','#f59e0b','#16a34a','#a855f7','#ec4899'])
    fig, axes = plt.subplots(n, 2, figsize=(9, 4*n), squeeze=False)
    for row, (name, d) in enumerate(reference_data.items()):
        crop = crop_for(d['photo_mask']); axes[row, 0].imshow(d['decision_mask'][crop], vmin=0, vmax=5, cmap=cmap); axes[row, 0].set_title('Regional fixed source decision')
        matching = [c for c in observations if c['reference_camera']['image_name'] == name]
        picked = next((c for c in matching if c['decision'] == 'IMAGE_SUPPORTED_LOCAL_PROBE'), matching[0] if matching else None)
        if picked:
            box = picked['display_bbox']; zoom = np.s_[box[1]:box[3], box[0]:box[2]]
            axes[row, 1].imshow(d['rgb'][zoom]); mask = d['decision_mask'][zoom]
            axes[row, 1].imshow(np.ma.masked_where(mask < 2, mask), vmin=0, vmax=5, cmap=cmap, alpha=.75, interpolation='nearest')
            axes[row, 1].set_title(picked['observation_id'], fontsize=9)
        for ax in axes[row]: ax.axis('off')
    fig.suptitle(region+' | 04 Blue prior / orange MVS / green agree / purple abstain / pink projected abstain\nExact authority pixels only; larger crops are display context', fontsize=10); fig.tight_layout(); fig.savefig(out/'04_masks.png', dpi=140); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    for column, (label, cloud) in enumerate([('PRIOR_CONTROL assembly', prior), ('SELECTED_SOURCE assembly', selected)]):
        for row, dims in enumerate([(0, 1), (0, 2)]):
            ax = axes[row, column]; fixed = ~cloud['trainable_geometry']; movable = ~fixed
            ax.scatter(cloud['xyz'][fixed, dims[0]], cloud['xyz'][fixed, dims[1]], s=.5, c='#64748b', label='Frozen prior context')
            ax.scatter(cloud['xyz'][movable, dims[0]], cloud['xyz'][movable, dims[1]], s=9, c='#f59e0b' if column else '#2563eb', label='Selected trainable source')
            ax.set(xlabel='local X (m)', ylabel='local '+('Y' if row == 0 else 'Z')+' (m)', title=label); ax.set_aspect('equal'); ax.legend(fontsize=7)
            union = np.concatenate([prior['xyz'], selected['xyz']]); ax.set_xlim(union[:, dims[0]].min(), union[:, dims[0]].max()); ax.set_ylim(union[:, dims[1]].min(), union[:, dims[1]].max())
    fig.suptitle(f'{region} | 05 Direct raw source assembly: prior {len(prior["xyz"]):,}; selected {len(selected["xyz"]):,}\nRemoved prior IDs {int(replacement.sum())}; added MVS {int((selected["source_kind"] == 1).sum())}; no GS optimization yet'); fig.tight_layout(); fig.savefig(out/'05_assembly.png', dpi=140); plt.close(fig)


def prepare_region(loader, region, cfg, basecfg, output):
    out = output/region; (out/'views').mkdir(parents=True); (out/'images').mkdir()
    views = loader.setup(region); domain = basecfg['regions'][region]['domain']; observations = unique_cases(loader.cases, region)
    admitted = [c for c in observations if c['decision'] == 'IMAGE_SUPPORTED_LOCAL_PROBE']
    expected = {'P1': 0, 'P2': 11, 'P3': 2}[region]
    if len(admitted) != expected: raise ValueError(f'Frozen admitted count changed: {region}')
    refs = {}; selected_names = set(); priorparts = []; mvsparts = []; sampling_counts = []
    for folder in sorted((loader.a.evidence/region).glob('view_*')):
        camera = json.loads(loader.observation_file(folder/'camera.json').read_text()); name = camera['name']
        d = loader.load(region, name); refs[name] = d; selected_names.add(name)
        with np.load(loader.observation_file(folder/'arrays.npz'), allow_pickle=False) as raw:
            for key, source in [('prior_depth','prior_common_ray'), ('mvs_depth','mvs_common_ray')]:
                if not np.allclose(d[key], raw[source], rtol=0, atol=1e-4, equal_nan=True): raise ValueError('Common RGB ray evidence differs')
        boxes = [c['bbox'] for c in observations if c['reference_camera']['image_name'] == name]
        mask, exact = ev.seed_pixel_mask(d['prior_depth'].shape, cfg['preparation']['seed_stride_px'], boxes)
        pmask = mask & ev.inside_xy(d['prior_xyz'], domain)
        part, good = source_samples(d, region, 0, pmask, exact); priorparts.append(part)
        amask = np.zeros_like(mask)
        for c in admitted:
            if c['reference_camera']['image_name'] == name:
                amask |= ev.patch_mask(mask.shape, c['bbox'])
                for prefix in ['prior', 'mvs']:
                    x0,y0,x1,y1 = c['bbox']; points = d[prefix+'_xyz'][y0:y1,x0:x1].reshape(-1,3)
                    expected_points = np.array([[np.nan if z is None else z for z in row] for row in c[prefix+'_patch_world']])
                    if not np.allclose(points, expected_points, rtol=0, atol=2e-5, equal_nan=True): raise ValueError('Exact admitted source patch changed')
        mmask = amask & ev.inside_xy(d['mvs_xyz'], domain) & ev.inside_xy(d['prior_xyz'], domain)
        mpart, mgood = source_samples(d, region, 1, mmask, amask); mvsparts.append(mpart)
        sampling_counts.append(dict(image_name=name, sampled_prior_pixels=int(pmask.sum()), prior_seeds=int(good.sum()), prior_invalid_normal_omitted=int((pmask & ~good).sum()), admitted_pixels=int(amask.sum()), admitted_mvs_seeds=int(mgood.sum()), admitted_mvs_invalid_or_outside_omitted=int((amask & ~mgood).sum())))
    if len(refs) != 3: raise ValueError('Exactly three original reference cameras required')
    for c in observations:
        selected_names.add(c['reference_camera']['image_name'])
        selected_names.update(n['image_name'] for n in c['neighbors'])
    if not selected_names.issubset(views): raise ValueError('Selected camera is outside bound training membership')
    prior = concatenate(priorparts); mvs = concatenate(mvsparts); replacement = np.zeros(len(prior['xyz']), bool); links = []
    raw_hypotheses = {k: [] for k in ['prior','mvs']}; raw_ids = {k: [] for k in raw_hypotheses}
    for ci, c in enumerate(admitted):
        name = c['reference_camera']['image_name']; d = refs[name]
        can_assemble = d['mvs_normal_valid'] & ev.inside_xy(d['mvs_xyz'], domain) & ev.inside_xy(d['prior_xyz'], domain)
        replacement_depth = np.where(can_assemble, d['prior_depth'], np.nan)
        hit = ev.prior_replacement_membership(prior['xyz'], d['camera'], c['bbox'], replacement_depth, cfg['preparation']['prior_replacement_depth_tolerance_m'])
        replacement |= hit
        for index in np.flatnonzero(hit): links.append((int(index), int(prior['stable_source_id'][index]), ci))
        patch = ev.patch_mask(d['prior_depth'].shape, c['bbox'])
        for kind, key in enumerate(['prior','mvs']):
            keep = patch & ev.inside_xy(d[key+'_xyz'], domain) & np.isfinite(d[key+'_depth']) & (d[key+'_depth'] > 0)
            raw_hypotheses[key].append(d[key+'_xyz'][keep]); raw_ids[key].append(ev.stable_ids(int(region[1:]), int(d['camera']['image_id']), int(d['camera']['width']), d['uv'][keep], kind))
    prior_arm, selected_arm = ev.assemble_source_arms(prior, replacement, mvs)
    if max(len(prior_arm['xyz']), len(selected_arm['xyz'])) > cfg['preparation']['maximum_seed_points']: raise ValueError('Seed cap exceeded')
    for key in raw_hypotheses:
        raw_hypotheses[key] = np.concatenate(raw_hypotheses[key]) if raw_hypotheses[key] else np.empty((0,3))
        raw_ids[key] = np.concatenate(raw_ids[key]) if raw_ids[key] else np.empty(0,np.int64)
    for key, cloud in [('prior_only', prior_arm), ('source_selected', selected_arm)]: np.savez_compressed(out/(key+'.npz'), **cloud)
    np.savez_compressed(out/'replacement_links.npz', rows=np.asarray(links,dtype=np.int64).reshape(-1,3), prior_stable_source_ids=prior['stable_source_id'], replacement_mask=replacement)
    np.savez_compressed(out/'raw_selected_hypotheses.npz', **{k+'_xyz':v for k,v in raw_hypotheses.items()}, **{k+'_stable_source_id':v for k,v in raw_ids.items()})
    write(out/'observations.json', dict(observations=observations, admitted_order=[c['observation_id'] for c in admitted], evaluation_accessed=False))
    viewrows = []; summaries = []
    for vi, name in enumerate(sorted(selected_names)):
        print(json.dumps(dict(region=region, stage='view_targets', index=vi+1, total=len(selected_names), image=name)), flush=True)
        d = refs[name] if name in refs else loader.load(region, name); cam = d['camera']; shape = d['prior_depth'].shape
        pin = ev.inside_xy(d['prior_xyz'], domain); min_ = ev.inside_xy(d['mvs_xyz'], domain); photomask = pin | min_
        auth = np.zeros(shape,bool); agree = auth.copy(); abstain = auth.copy()
        for c in observations:
            if c['reference_camera']['image_name'] != name: continue
            patch = ev.patch_mask(shape, c['bbox'])
            if c['decision'] == 'IMAGE_SUPPORTED_LOCAL_PROBE': auth |= patch
            elif c['decision'] == 'AGREE_NO_UPDATE': agree |= patch
            else: abstain |= patch
        projection = np.zeros(shape,bool); projection_arrays = {}
        for key in raw_hypotheses:
            result = ev.point_projection_support(cam, raw_hypotheses[key], d[key+'_depth'], cfg['preparation']['projection_depth_tolerance_m'])
            projection |= result['compatible_mask']
            for k in ['point_indices','pixel_xy','depth','observed_residual','compatible']: projection_arrays[key+'_'+k] = result[k]
            projection_arrays[key+'_stable_source_id'] = raw_ids[key][result['point_indices']]
        arrays = ev.view_targets(d['prior_depth'], d['mvs_depth'], d['prior_normal'], d['mvs_normal'], photomask, auth, projection, agree, abstain, prior_domain_mask=pin, mvs_domain_mask=min_)
        stem = f'view_{vi:03d}'; arraypath = out/'views'/(stem+'.npz'); projectionpath = out/'views'/(stem+'_links.npz')
        np.savez_compressed(arraypath, **arrays); np.savez_compressed(projectionpath, **projection_arrays)
        shutil.copy2(loader.a.inputs/region/'scene/images'/name, out/'images'/name)
        if sha(out/'images'/name) != cam['sha256']: raise ValueError('Copied RGB differs')
        viewrows.append(dict(id=stem, image_name=name, K=cam['K'], R=cam['R'], t=cam['t'], width=cam['width'], height=cam['height'], rgb_path='images/'+name, rgb_sha256=cam['sha256'], arrays_path='views/'+arraypath.name, arrays_sha256=sha(arraypath), projection_links_path='views/'+projectionpath.name, projection_links_sha256=sha(projectionpath), split='train', original_reference=name in refs, normal_frame='world', pixel_centers='integer', depth_axis='camera_Z_m'))
        summaries.append(dict(image_name=name, **{k:int(arrays[k].sum()) for k in ['photo_mask','authority_mask','depth_valid','normal_valid','projection_abstain_mask','target_mask','surrounding_mask','outside_mask']}))
        if name in refs:
            for k in ['photo_mask','decision_mask']: d[k] = arrays[k]
    plot_stages(out, region, refs, observations, prior_arm, selected_arm, replacement, summaries)
    manifest = dict(schema='jbgs.source_selected_2dgs.prepared_region.v1', task_id=cfg['task_id'], region=region, scientific_verdict=None,
        crs=cfg['crs'], world_shift=cfg['world_shift'], normal_frame='world', depth_axis='camera_Z_m', region_xy=domain, region_xy_source=dict(path=str(loader.a.base_config),sha256=sha(loader.a.base_config),uses_z=False),
        prior_role=cfg['inputs']['prior_role'], arms={k:k+'.npz' for k in cfg['arms']}, arm_sha256={k:sha(out/(k+'.npz')) for k in cfg['arms']}, views=viewrows,
        observations_path='observations.json', observations_sha256=sha(out/'observations.json'), replacement_links_path='replacement_links.npz', replacement_links_sha256=sha(out/'replacement_links.npz'),
        raw_hypotheses_path='raw_selected_hypotheses.npz', raw_hypotheses_sha256=sha(out/'raw_selected_hypotheses.npz'),
        counts=dict(frozen_admitted_patches=len(admitted), unique_observation_patches=len(observations), prior_points=len(prior_arm['xyz']), selected_points=len(selected_arm['xyz']), removed_prior_points=int(replacement.sum()), added_mvs_points=len(mvs['xyz']), prior_trainable_points=int(prior_arm['trainable_geometry'].sum()), selected_trainable_points=int(selected_arm['trainable_geometry'].sum())), sampling=sampling_counts, view_counts=summaries,
        stage_images=['01_inputs.png','02_conflict.png','03_evidence.png','04_masks.png','05_assembly.png'], source_decisions_reestimated=False, reference_accessed=False,
        limits=['Observation gate supports a local MVS source choice; it is not independently validated source authority or temporal-change classification.', 'Projected source samples are diagnostic links only and do not create new MVS authority.', 'Source samples from different cameras remain duplicate observations with explicit IDs; no voxel deduplication.', 'All cameras belong to the frozen training split; these are not independent held-out RGB measurements.', 'Normals use unfilled raw central differences, and scale is half geometric-mean constant-camera-Z pixel spacing times sample stride.', 'P1 has zero admitted patches and is a protected negative control; this does not establish general algorithm failure.', 'This payload is direct raw source assembly. Gaussian optimization and evaluation occur later.'])
    write(out/'manifest.json', manifest)
    return dict(region=region, path=region+'/manifest.json', sha256=sha(out/'manifest.json'), counts=manifest['counts'])


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    ap = argparse.ArgumentParser()
    for key in ['config','primary','screen','evidence','inputs','mvs','base-config','output']: ap.add_argument('--'+key, type=Path, required=True)
    a = ap.parse_args(); start = time.time(); cfg = json.loads(a.config.read_text())
    if cfg['inputs']['reference_access_for_selection'] or cfg['preparation']['voxel_size_m'] != 0 or cfg['preparation']['seed_stride_px'] != 8: raise ValueError('Unapproved preparation policy')
    a.output.mkdir(parents=True, exist_ok=False)
    try:
        loader = BoundInputs(a,cfg); basecfg = json.loads(a.base_config.read_text())
        rows = [prepare_region(loader,r,cfg,basecfg,a.output) for r in cfg['regions']]
        shutil.copy2(a.config,a.output/'config.json')
        write(a.output/'manifest.json',dict(schema='jbgs.source_selected_2dgs.prepared.v1',task_id=cfg['task_id'],regions=rows,scientific_verdict=None,reference_accessed=False,config_sha256=sha(a.config)))
        write(a.output/'receipt.json',dict(status='PASS_PREPARED_SOURCES',task_id=cfg['task_id'],scientific_verdict=None,reference_accessed=False,created_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.time()-start,python=platform.python_version(),numpy=np.__version__,config_sha256=sha(a.config),source_sha256=sha(__file__),policy_sha256=sha(ev.__file__),inputs=list(loader.bound.values()),outputs=[dict(path=str(p.relative_to(a.output)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(a.output.rglob('*')) if p.is_file()]))
    except Exception as exc:
        write(a.output/'failure.json',dict(status='FAIL_PREPARATION',error=repr(exc),elapsed_seconds=time.time()-start,scientific_verdict=None)); raise


if __name__ == '__main__': main()
