#!/usr/bin/env python3
"""Frozen0..8k count/resource figure; no renderer, reference or training execution."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from PIL import Image

EXPECTED_SFM = {'P1': 'no_anchor_sfm_memory_recovery_v2', 'P2': 'no_anchor_sfm_memory_recovery_P2_v2',
                'P3': 'no_anchor_sfm_memory_recovery_P3_v3'}
EXPECTED_ALS = {'P1': 'runs/P1/D005_Pnative', 'P2': 'runs_allocator_v2/P2/D005_Pnative',
                'P3': 'runs_allocator_v2/P3/D005_Pnative'}
GAUSSIAN_SHA = '4be070008683ba1943de9e22d1f4d1a9c194aef56010c0b3186d0bd7f6aadb9a'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): digest.update(block)
    return digest.hexdigest()


def read(path): return json.loads(path.read_text())


def header_count(path):
    with path.open('rb') as stream:
        lines = []
        for _ in range(1000):
            line = stream.readline()
            if not line or sum(map(len, lines)) > 16384: raise ValueError('Invalid bounded PLY header')
            lines.append(line)
            if line.strip() == b'end_header': break
        else: raise ValueError('Unterminated PLY header')
    counts = [int(line.split()[2]) for line in lines if line.startswith(b'element vertex ')]
    assert len(counts) == 1 and counts[0] > 0
    return counts[0], hashlib.sha256(b''.join(lines)).hexdigest()


def prefix(path, sfm):
    rows, raw = [], []
    with path.open('rb') as stream:
        for line in stream:
            assert line.endswith(b'\n'), 'Incomplete prefix line'
            row = json.loads(line)
            assert type(row['iteration']) is int and (not rows or row['iteration'] > rows[-1]['iteration'])
            if row['iteration'] > 8000: break
            for key in ('gaussians', 'protected'):
                assert type(row[key]) is int and row[key] >= 0
            assert 0 <= row['protected'] <= row['gaussians'] and row['gaussians'] > 0
            rows.append(row)
            raw.append(line)
            if row['iteration'] == 8000: break
    assert [row['iteration'] for row in rows] == ([1] if sfm else []) + list(range(100, 8001, 100))
    return b''.join(raw), rows


def build(args):
    assert Path('/.dockerenv').is_file()
    assert not any(Path(p).exists() for p in ('/task', '/reference', '/artifacts/JointBuildGS'))
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    assert not (out/'proof.json').exists()
    cfg, layout, policy = read(args.config), read(Path('/layout.json')), read(Path('/policy.json'))
    assert sha(Path('/layout.json')) == cfg['runtime_layout_sha256']
    assert sha(Path('/policy.json')) == cfg['historical_policy_sha256']
    assert policy['selected_attempts'] == EXPECTED_SFM and policy['prefix_iteration'] == 8000
    assert {r: layout['anchors'][r]['baseline_directory'] for r in cfg['regions']} == EXPECTED_ALS
    assert sha(Path('/native_gaussian_model.py')) == GAUSSIAN_SHA
    source_text = Path('/native_gaussian_model.py').read_text()
    assert 'self.frozen_mask = torch.zeros((self.get_xyz.shape[0]), dtype=torch.bool, device="cuda")' in source_text
    (out/'snapshots').mkdir()
    evidence, bindings, table, endpoint = [], [], [], []
    def bind(path, relative, name):
        assert not relative.startswith('/') and '..' not in Path(relative).parts
        target = out/'snapshots'/name
        shutil.copyfile(path, target)
        record = dict(path=relative, sha256=sha(path), bytes=path.stat().st_size,
                      snapshot=str(target.relative_to(out)), snapshot_sha256=sha(target))
        assert record['sha256'] == record['snapshot_sha256']
        evidence.append(record)
        return record
    bind(Path('/layout.json'), 'contracts/runtime_layout_allocator_v2.json', 'runtime_layout.json')
    bind(Path('/policy.json'), 'contracts/sfm_prefix8000_diagnostic_v1.json', 'historical_policy.json')
    bind(Path('/native_gaussian_model.py'), 'sources/GeoGS-state-camera-v1/scene/gaussian_model.py', 'native_gaussian_model.py')
    for region in cfg['regions']:
        for family, sfm in (('ALS_anchor', False), ('Historical_SfM_no_anchor', True)):
            tag = region+'_'+('sfm' if sfm else 'als')
            root = Path('/inputs')/region/('sfm' if sfm else 'als')
            run = EXPECTED_SFM[region]+'/runs/'+region+'/SFM_noanchor_D005_Pnative' if sfm else EXPECTED_ALS[region]
            trace_raw, rows = prefix(root/'trace.jsonl', sfm)
            trace_sha = hashlib.sha256(trace_raw).hexdigest()
            snapshot_trace = out/'snapshots'/(tag+'_trace_through8000.jsonl')
            snapshot_trace.write_bytes(trace_raw)
            complete = read(root/'complete_receipt.json')
            assert complete['schema'] == 'JBGS_GEOGS_COMPLETE_STATE_v1' and complete['iteration'] == 8000
            assert complete['scientific_verdict'] is None and complete['after_protection_registration'] is True
            assert complete['gaussians'] == rows[-1]['gaussians']
            complete_record = bind(root/'complete_receipt.json', run+'/model/jbgs_complete/iteration_8000/receipt.json', tag+'_complete8000.json')
            n_ply, ply_header_sha = header_count(root/'complete.ply')
            assert n_ply == complete['gaussians']
            assert (root/'checkpoint.pth').stat().st_size > 0
            invocation = read(root/'invocation.json')
            invocation_record = bind(root/'invocation.json', run+('/invocation.json' if sfm else '/train_invocation.json'), tag+'_invocation.json')
            source_map = invocation['source_sha256' if sfm else 'implementation_hashes']
            assert source_map['scene/gaussian_model.py'] == GAUSSIAN_SHA
            if sfm:
                initial = read(root/'initialization.json')
                initial_record = bind(root/'initialization.json', run+'/model/jbgs_no_anchor/initialization.json', tag+'_initialization.json')
                first = read(root/'first_step.json')
                bind(root/'first_step.json', run+'/model/jbgs_no_anchor/first_step.json', tag+'_first_step.json')
                sfm_manifest = read(root/'sfm_manifest.json')
                manifest_record = bind(root/'sfm_manifest.json', EXPECTED_SFM[region]+'/inputs/'+region+'/initialization_manifest.json', tag+'_sfm_manifest.json')
                assert sha(root/'sfm_manifest.json') == invocation['sfm_manifest_sha256']
                assert initial['status'] == 'PASS_PREOPTIMIZATION_PROTECTION' and initial['iteration'] == 0
                assert initial['gaussian_count_before'] == initial['gaussian_count_after'] == sfm_manifest['point_count']
                assert initial['pretrained_model_or_optimizer_loaded'] is False and initial['als_gaussians_inserted'] == 0
                assert first['status'] == 'PASS_FIRST_STEP_DIRECT_REFINEMENT' and first['stage2_active'] is True
                assert all(row['protected'] == initial['protected_gaussians'] for row in rows)
                init_n, init_protected = initial['gaussian_count_after'], initial['protected_gaussians']
                init_origin = 'PREOPTIMIZATION_AUDIT'
                registration_iteration = 0
                memory = read(root/'memory_runtime_receipt.json')
                assert memory['status'] == 'PASS_MEMORY_RECOVERY_RUNTIME_PREPARED' and memory['storage_version'] == 2
                assert 'resource_recovery_version' not in memory, 'Do not substitute final resourcev3 retries'
                assert memory['science_config_unchanged'] is True
                bind(root/'memory_runtime_receipt.json', EXPECTED_SFM[region]+'/source/jbgs_memory_recovery_receipt.json', tag+'_memory_runtime.json')
                assert {k:v for k,v in memory['destination_python_sha256'].items() if 'submodules' not in Path(k).parts} == source_map
                parent_status = 'NO_CLOSED_PARENT_RECEIPT_AT_SNAPSHOT' if not (root/'train_receipt.json').exists() else read(root/'train_receipt.json')['status']
            else:
                init_n, initial_header_sha = header_count(root/'input.ply')
                initial_record = bind(root/'input.ply', run+'/model/input.ply', tag+'_input.ply')
                assert sha(root/'input.ply') == sha(root/'canonical_initialization.ply')
                assert invocation['config_sha256'] == layout['scientific_config_sha256'] and '--lod_init' in invocation['command']
                assert invocation['command'][invocation['command'].index('--stage_switch_iter')+1] == '8000'
                assert all(row['protected'] == 0 for row in rows[:-1]) and rows[-1]['protected'] > 0
                assert rows[0]['gaussians'] == init_n
                init_protected, registration_iteration = 0, 8000
                init_origin = 'INPUT_PLY_COUNT_PLUS_FROZEN_NATIVE_INITIAL_MASK_ZERO'
                if region == 'P1': assert complete['checkpoint_sha256'] == layout['anchors']['P1']['checkpoint_sha256']
                parent_status = read(root/'train_receipt.json')['status']
            if (root/'train_receipt.json').exists():
                bind(root/'train_receipt.json', run+('/receipt.json' if sfm else '/train_receipt.json'), tag+'_parent_receipt.json')
            counts = [dict(iteration=0, gaussians=init_n, protected=init_protected, origin=init_origin)]
            counts += [dict(iteration=row['iteration'], gaussians=row['gaussians'], protected=row['protected'], origin='NATIVE_TRACE') for row in rows]
            for row in counts:
                table.append(dict(region=region, family=family, iteration=row['iteration'], gaussians=row['gaussians'],
                    registered_protected_gaussians=row['protected'], registered_protected_fraction=row['protected']/row['gaussians'],
                    count_origin=row['origin'], registration_iteration=registration_iteration,
                    source_run=run, prefix_sha256=trace_sha, complete_receipt_sha256=complete_record['sha256']))
            endpoint.append(dict(region=region, family=family, initial_gaussians=init_n,
                initial_registered_protected=init_protected, gaussians_8000=rows[-1]['gaussians'],
                registered_protected_8000=rows[-1]['protected'], registration_iteration=registration_iteration))
            # The running parent may append later. Only the already complete
            # prefix is bound; a second read confirms it did not change.
            assert prefix(root/'trace.jsonl', sfm)[0] == trace_raw
            bindings.append(dict(region=region, family=family, source_run=run,
                source_trace=run+'/model/jbgs_trace.jsonl', trace_prefix_sha256=trace_sha,
                snapshot_trace=str(snapshot_trace.relative_to(out)), trace_rows=len(rows),
                bytes_through8000=len(trace_raw), first_iteration=rows[0]['iteration'], last_iteration=8000,
                source_trace_append_after8000_allowed=sfm, prefix_stability_second_read=True,
                complete_receipt=complete_record, invocation=invocation_record, initialization=initial_record,
                checkpoint_payload=dict(path=run+'/model/jbgs_complete/iteration_8000/checkpoint.pth',
                    bytes=(root/'checkpoint.pth').stat().st_size, declared_sha256=complete['checkpoint_sha256'], full_hash_recomputed=False),
                ply_payload=dict(path=run+'/model/jbgs_complete/iteration_8000/point_cloud.ply',
                    bytes=(root/'complete.ply').stat().st_size, declared_sha256=complete['ply_sha256'], full_hash_recomputed=False,
                    header_vertex_count=n_ply, bounded_header_sha256=ply_header_sha),
                parent_status_at_snapshot=parent_status, fixed_historical_selection=True))
    assert len(table) == cfg['chart_contract']['expected_rows']
    for name, data in (('counts.csv', table), ('endpoints.csv', endpoint)):
        with (out/name).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.titleweight':'bold',
                         'axes.labelcolor':'#27313A', 'text.color':'#27313A', 'xtick.color':'#49535C',
                         'ytick.color':'#49535C', 'pdf.fonttype':42})
    fig, axes = plt.subplots(2, 3, figsize=cfg['chart_contract']['footprint_inches'], sharex=True, sharey='row')
    fig.subplots_adjust(left=.075, right=.97, bottom=.205, top=.78, hspace=.23, wspace=.14)
    fig.suptitle('Gaussian and registered-protection counts | 0–8,000 iterations', x=.075, y=.965, ha='left', fontsize=18, weight='bold')
    fig.text(.075, .922, 'Canonical ALS anchor vs historical SfM initialization without anchor · P1 / P2 / P3', fontsize=11)
    colors = cfg['chart_contract']['palette']
    top_max = max(row['gaussians'] for row in table)*1.16
    lines = []
    for column, region in enumerate(cfg['regions']):
        axes[0,column].set_title(region, loc='left', pad=12, fontsize=13)
        for family in ('ALS_anchor', 'Historical_SfM_no_anchor'):
            rows = [row for row in table if row['region']==region and row['family']==family]
            x = [row['iteration'] for row in rows]
            color = colors[family]
            native = family=='ALS_anchor'
            for r, key in ((0,'gaussians'), (1,'registered_protected_gaussians')):
                ax = axes[r,column]
                y = [row[key] for row in rows]
                line, = ax.step(x, y, where='post', color=color, linewidth=1.8, linestyle='--' if native else '-')
                if r==0 and column==0: lines.append(line)
                ax.scatter([x[-1]], [y[-1]], marker='s' if native else 'o', s=36,
                           facecolors='white' if native else color, edgecolors=color, linewidths=1.3, clip_on=False, zorder=4)
                if r==0:
                    ax.annotate(f'{y[-1]/1e6:.3f} M', (8000,y[-1]), xytext=(-8,10 if not native else -16),
                                textcoords='offset points', ha='right', color=color, fontsize=10, weight='bold')
                else:
                    ax.annotate(f'{y[-1]:,}', (8000,y[-1]), xytext=(-8,8 if native else 10),
                                textcoords='offset points', ha='right', color=color, fontsize=10, weight='bold')
        for ax in axes[:,column]:
            ax.set_xlim(0,8000); ax.set_xticks([0,2000,4000,6000,8000])
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_: '0' if v==0 else f'{int(v/1000)}k'))
            ax.grid(axis='y', color='#E0E4E8', linewidth=.7)
            ax.set_axisbelow(True)
            ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
            for side in ('left','bottom'): ax.spines[side].set_color('#A5ACB3')
        axes[0,column].set_ylim(0,top_max)
        axes[0,column].yaxis.set_major_formatter(FuncFormatter(lambda v,_: f'{v/1e6:g}'))
        axes[1,column].set_yscale('symlog', linthresh=1000, linscale=1)
        axes[1,column].set_ylim(-40,400000)
        axes[1,column].set_yticks([0,1000,10000,100000])
        axes[1,column].yaxis.set_major_formatter(FuncFormatter(lambda v,_: '0' if v==0 else f'{int(v/1000):,}k'))
        axes[1,column].set_xlabel('Optimizer iteration')
    axes[0,0].set_ylabel('Gaussians (millions)', labelpad=13)
    axes[1,0].set_ylabel('Registered protected Gaussians\n(symlog; linear through 1,000)', labelpad=13)
    fig.legend(lines, ['ALS initialization + anchor', 'Historical SfM initialization + no anchor'],
               loc='upper left', bbox_to_anchor=(.07,.889), ncol=2, frameon=False, handlelength=3, columnspacing=2.6)
    fig.text(.075,.126,'ALS mask registration: iteration 8,000.  SfM mask registration: before step 1.  Bottom panels preserve zero; numbers are exact counts.',fontsize=10)
    fig.text(.075,.093,'Registered mask count is not total prior influence: the ALS anchoring loss is active while its pre-8k mask remains zero.',fontsize=10)
    fig.text(.075,.060,'Initialization and protection membership differ. CPU offload costs are not pure-method timing. Counts alone do not establish quality or anchor necessity.',fontsize=9.5)
    fig.savefig(out/'resource_prefix8000.png', dpi=cfg['chart_contract']['png_dpi'], facecolor='white')
    fig.savefig(out/'resource_prefix8000.pdf', facecolor='white', metadata={'Title':'Fixed0..8000 Gaussian and registered protection counts','Author':'JointBuildGS'})
    plt.close(fig)
    with Image.open(out/'resource_prefix8000.png') as image:
        image.load(); dimensions=image.size
    assert (out/'resource_prefix8000.pdf').read_bytes().startswith(b'%PDF-')
    shutil.copyfile(args.config, out/'config_snapshot.json')
    shutil.copyfile(__file__, out/'build_snapshot.py')
    notes = '# 고정 0–8,000회 Gaussian 수·등록 보호 수\n\n'
    notes += 'scientific_verdict: null\n\n이 그림은 고정된 과거 실행의 count/resource 기록만 사용한다. 표면 fallback을 활성화하지 않고 새로운 최종 resource-v3 재시도를 대체 입력으로 쓰지 않는다.\n\n'
    notes += '등록 보호 수는 frozen_mask의 원소 수다. ALS는 8,000회에 매칭을 등록하며 그 전에도 anchoring loss가 작동한다. SfM은 초기화 전혀 다른 점 집합에 step 1 이전 보호를 등록했다. 하단 symlog 축은 0을 보존하고 1,000까지 선형이다.\n\n'
    notes += '초기 ALS Gaussian 수는 원 input.ply의 vertex 수이며 보호 0은 frozen create_from_pcd의 zeros mask로 확인했다. SfM 초기 수는 preoptimization audit의 실제 기록이다. 100-step trace와 SfM iteration1만 연결했다.\n\n'
    notes += '8k complete receipt는 실제 SHA로 봉인하고 PLY header의 N을 확인했다. 다중 GB checkpoint/PLY 전체 SHA는 그 complete receipt의 선언값으로만 보존했으며, 새 전체 해시 검증이나 tensor 로드는 하지 않았다.\n\n'
    notes += 'CPU moment offload 비용이 달라 순수 방법 속도 비교가 아니며 시간 곡선도 그리지 않았다. 품질·Anchor 필요성·최종 수렴·22k/30k 완료 결론은 없다.\n'
    (out/'NOTES_ko.md').write_text(notes)
    outputs = [dict(path=path.name,bytes=path.stat().st_size,sha256=sha(path)) for path in sorted(out.iterdir()) if path.is_file()]
    proof = dict(schema='GEOGS_RESOURCE_PREFIX_FIGURE_PROOF_v1', status='PASS_COUNT_DATA_AND_FIGURE_GENERATION',
        scientific_verdict=None, reference_accessed=False, render_quality_analyzed=False, training_launched=False,
        surface_fallback_activated=False, new_final_retry_substituted=False, iteration_range=[0,8000],
        config_sha256=sha(args.config), image_id=cfg['runtime_image_id'], rows=len(table), endpoints=endpoint,
        trace_prefix_bindings=bindings, evidence=evidence, outputs=outputs, png_dimensions=list(dimensions),
        versions=dict(matplotlib=matplotlib.__version__), visual_review='Separate visual_qa receipt after inspection',
        large_payload_full_hashes_recomputed=False, original_traces_unmodified=True,
        timestamp_unix=time.time(), limitations=cfg['limitations'])
    with (out/'proof.json').open('x') as stream: json.dump(proof,stream,indent=2,allow_nan=False); stream.write('\n')
    print(json.dumps(dict(status=proof['status'], rows=len(table), endpoints=endpoint, png_dimensions=dimensions)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    build(parser.parse_args())
