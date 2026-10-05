"""Build an additive same-512 review using existing measured artifacts only."""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repair-display-links', action='store_true')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    source = args.task / cfg['source_manifest']
    assert sha(source) == cfg['source_manifest_sha256'], 'Source manifest changed'
    manifest = json.loads(source.read_text())
    assert manifest['scientific_verdict'] is None
    assert [r['id'] for r in manifest['regions']] == cfg['regions']
    # Binary mesh parts are resolved against the viewer manifest URL by the
    # existing app. Preserve those P1/P2/P3 relative routes in this new profile.
    aliases = []
    for rid in cfg['regions']:
        assert (args.task / 'evaluation/viewer' / rid).is_dir()
        target = '../viewer/' + rid
        alias = args.out / rid
        if alias.is_symlink():
            assert str(alias.readlink()) == target
        else:
            assert not alias.exists(), 'Do not replace an existing directory'
            alias.symlink_to(target, target_is_directory=True)
        aliases.append(dict(path=rid, target=target, source='evaluation/viewer/' + rid))
    if args.repair_display_links:
        write_json(args.out / 'mesh_link_repair_receipt.json', dict(
            schema='GEOGS_ANCHOR_REVIEW_MESH_LINK_REPAIR_v1', scientific_verdict=None,
            reason='First browser smoke loaded points but mesh binary paths resolved relative to new manifest and returned HTTP404',
            original_failure='browser_qa/receipt.json', aliases=aliases,
            manifest_sha256=sha(args.out / 'manifest.json'), script_sha256=sha(Path(__file__)),
            original_manifest_sha256=sha(source), existing_payloads_modified=False,
            created_at=datetime.now(timezone.utc).isoformat()))
        print(json.dumps(dict(status='DISPLAY_MESH_LINKS_ADDED', scientific_verdict=None)))
        return
    assert not (args.out / 'receipt.json').exists()
    assert not (args.out / 'manifest.json').exists()
    ledger = {cfg['source_manifest']: sha(source)}
    generated = []
    base_url = '/task/' + cfg['source_manifest']

    def absolute_urls(value):
        if isinstance(value, dict):
            return {k: urljoin(base_url, v) if isinstance(v, str) and (k == 'url' or k.endswith('_url'))
                    else absolute_urls(v) for k, v in value.items()}
        if isinstance(value, list):
            return [absolute_urls(v) for v in value]
        return value

    manifest = absolute_urls(copy.deepcopy(manifest))
    manifest['default_resolution'] = '512'
    manifest['resolution_modes'] = [m for m in manifest['resolution_modes'] if m['id'] == '512']
    manifest['resolution_modes'][0]['label'] = 'Anchor·최종 동일 512'
    manifest['title'] = 'GeoGS 자산 검토 — prior / Anchor / 최종 동일512'
    manifest['review_profile'] = dict(task_id=cfg['task_id'], source_manifest=base_url,
        source_sha256=cfg['source_manifest_sha256'], newly_trained_models=0,
        newly_extracted_meshes=0, recomputed_quality_metrics=0, scientific_verdict=None)
    manifest['notes'].insert(0, '기존 실제 Anchor512와 final512를 재사용한 별도 비교 화면입니다.')
    labels = {
        'D005_Pnative': 'D005_Pnative · 원설정',
        'D0005_Pnative': 'D0005_Pnative · 깊이 1/10 · 보호 유지',
        'D0_Pnative': 'D0_Pnative · 깊이 손실 0 · 보호 유지',
        'D005_Prelease': 'D005_Prelease · 깊이 원설정 · 보호 해제',
        'D0005_Prelease': 'D0005_Prelease · 깊이 1/10 · 보호 해제',
        'D0_Prelease': 'D0_Prelease · 깊이 손실 0 · 보호 해제',
    }
    for region in manifest['regions']:
        rid = region['id']
        candidates = {c['id']: c for c in region['candidates']}
        assert [c['id'] for c in region['conditions']] == cfg['conditions']
        region['default_condition'] = cfg['default_condition']
        region['notes'].insert(0,
            '③ Anchor: 실제 8,000회 상태의 512 표면. ④·⑤도 같은512. 현재성 판단은 관측 근거가 있는 범위에 한정합니다.')
        for condition in region['conditions']:
            condition['label'] = labels[condition['id']]
        region['panel_candidates']['anchor'] = 'D005_Pnative.anchor_512.raw'
        region['panel_candidates']['vanilla'] = 'D005_Pnative.mesh_512.raw'
        for condition in cfg['conditions']:
            for kind in cfg['surface_kinds']:
                for identifier in ['D005_Pnative.anchor_512.' + kind, condition + '.mesh_512.' + kind]:
                    candidate = candidates[identifier]
                    assert candidate['status'] == 'available', identifier
                    assert (args.task / candidate['data']['url'].removeprefix('/task/')).is_file()
        new_sections = []
        for condition in cfg['conditions']:
            for kind in cfg['surface_kinds']:
                ids = ['prior_mesh', 'D005_Pnative.anchor_512.' + kind,
                       'D005_Pnative.mesh_512.' + kind, condition + '.mesh_512.' + kind]
                paths = [args.task / 'evaluation/viewer' / rid / (identifier + '.sections.png') for identifier in ids]
                images = []
                for path in paths:
                    ledger[str(path.relative_to(args.task))] = sha(path)
                    with Image.open(path) as original:
                        images.append(original.convert('RGB'))
                assert len({image.size for image in images}) == 1, 'Section frames differ'
                w, h = images[0].size
                stack = Image.new('RGB', (w, h * len(images)), 'white')
                for index, image in enumerate(images):
                    stack.paste(image, (0, h * index))
                relative = Path('sections') / rid / (condition + '.' + kind + '.png')
                destination = args.out / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                assert not destination.exists()
                stack.save(destination)
                # Each original section is copied without resizing or changing pixels.
                with Image.open(destination) as saved:
                    for index, image in enumerate(images):
                        assert saved.crop((0, h * index, w, h * (index + 1))).tobytes() == image.tobytes()
                generated.append(dict(path=str(relative), sha256=sha(destination),
                    width=w, height=h * len(images), source_paths=[str(p.relative_to(args.task)) for p in paths],
                    transform='VERTICAL_CONCATENATION_WITHOUT_RESAMPLING', pixel_equality_verified=True))
                new_sections.append(dict(id='asset_review.' + condition + '.' + kind,
                    label='같은512 ' + kind + ' · prior → Anchor → 바닐라 → ' + condition,
                    url='/task/' + cfg['output'] + '/' + str(relative), condition_id=condition,
                    caption='위에서 prior / Anchor8000 / 바닐라30000 / 선택조건30000. GS는 모두512·' + kind +
                        '. 검정은 동일 UAS. 기존 고정 단면 폭0.5m의 표본 띠를 그대로 연결했습니다. 실제 교선이나 현재성 정답이 아닙니다.',
                    selection_reason='All six conditions and both surfaces; existing fixed sections, no outcome ranking',
                    comparison_family='anchor_refinement_512'))
        # Make anchor and native evidence accessible alongside every selected condition.
        for item in region['renders']:
            if item.get('condition_id') == 'D005_Pnative':
                item['source_condition_id'] = item['condition_id']
                item['condition_id'] = None
                label = 'Anchor 8000회' if item.get('stage') == 'anchor_512' else '바닐라 30000회'
                item['label'] = label + ' · ' + item['label']
        # This profile presents matched512 stage sections; full1024 remains in the original viewer.
        retained = [item for item in region['sections'] if not any(
            key in item['id'] for key in ['.final.', '.anchor.', '.mesh_2048.'])]
        for item in retained:
            if item.get('condition_id') == 'D005_Pnative':
                item['source_condition_id'] = item['condition_id']
                item['condition_id'] = None
        region['sections'] = new_sections + retained
    manifest['downloads'].insert(0, dict(label='최종1024 원래 비교 화면',
        url='/app/index.html?manifest=' + base_url + '&color=height'))
    manifest['downloads'].insert(1, dict(label='이번 Anchor 표시 생성 기록',
        url='/task/' + cfg['output'] + '/receipt.json'))
    write_json(args.out / 'manifest.json', manifest)
    assert sha(source) == cfg['source_manifest_sha256'], 'Original manifest changed during build'
    write_json(args.out / 'receipt.json', dict(schema='GEOGS_ANCHOR_REVIEW_DISPLAY_v1',
        task_id=cfg['task_id'], status='EXISTING_ANCHOR512_AND_FINAL512_REVIEW_READY', scientific_verdict=None,
        created_at=datetime.now(timezone.utc).isoformat(), config=cfg, config_sha256=sha(args.config),
        script_sha256=sha(Path(__file__)), source_hashes=ledger, generated=generated, aliases=aliases,
        manifest_sha256=sha(args.out / 'manifest.json'), newly_trained_models=0,
        newly_extracted_meshes=0, recomputed_quality_metrics=0,
        verification_scope='Source manifest, required candidate availability/files, section input hashes and pixel equality; not a rehash of the full raw payload corpus'))
    print(json.dumps(dict(status='ANCHOR_REVIEW_READY', regions=cfg['regions'], sections=len(generated),
        manifest_sha256=sha(args.out / 'manifest.json'), scientific_verdict=None)))


if __name__ == '__main__':
    main()
