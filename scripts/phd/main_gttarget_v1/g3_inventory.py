"""Stage 3 inventory (CPU): for every order item (sections 6-10) list whether the inputs it needs exist, so no training has to be rerun.
Writes tables/stage3_inventory (csv+json). Re-run at any time; it only reads."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
TE6 = TE/'addendum6'; FTR = FT
RUNS = [(s, 'gtt_s0') for s in STEMS]+[('R1rep_b10__ALS', 'gtt_s1'), ('R1rep_b10__LoD2', 'gtt_s1'), ('B173nb_b10__LoD2', 'gtt_s0_rerun1'), ('B173nb_b10__LoD2', 'gtt_s1')]  # 11-20: rerun (stopped) and seed-1 run added
DUMPS = ['0', '1000', '3000_pre_reset', '3500', '5000', '6000_pre_reset', '7000', '9000_pre_reset', '12000_pre_reset', '15000', '30000']
VARS = ['base', 'occl', 'median_depth', 'occl_median']
def main():
    rows = []
    def add(item, stem, run, what, ok, note=''): rows.append(dict(title=TITLE, item=item, stem=stem, run=run, what=what, ok=bool(ok), note=note))
    for stem, run in RUNS:
        root = O/'runs'/stem/run; m = root/'model'; rc = json.loads((root/'receipt.json').read_text()) if (root/'receipt.json').exists() else {}
        st = rc.get('status'); add('6 학습', stem, run, 'receipt status', st == 'COMPLETED', str(st))
        if st != 'COMPLETED':
            add('6 학습', stem, run, 'health stop reason', bool(rc.get('health')), (rc.get('health') or {}).get('reason', '')); continue
        add('7.1 추출', stem, run, 'iteration 30000 ply', (m/'point_cloud/iteration_30000/point_cloud.ply').exists())
        tl = m/'trainlog'
        for d in DUMPS: add('6.1 기록', stem, run, f'scene dump {d}', (tl/'scene'/f'{d}.pt').exists())
        ev = {p.stem.rsplit('_', 1)[0] for p in (tl/'events').glob('*.npz')}
        for e in ['birth', 'delete', 'link', 'release', 'retarget', 'opacity_reset']: add('6.1 기록', stem, run, f'events {e}', e in ev)
        add('8.1 상태', stem, run, 'states 30000', (tl/'states/30000.npz').exists())
        for v in VARS:
            k = f'{stem}__{run}_{v}'
            add('7.1 추출', stem, run, f'mesh {v} score', (O/'meshes'/k/'score.json').exists()); add('7.1 추출', stem, run, f'mesh {v} points', (O/'meshes'/k/'points.npz').exists())
            add('9 그림', stem, run, f'mesh {v} final.ply', (O/'gtj/meshes'/k/'final.ply').exists())
    for stem in STEMS:
        site = stem.split('__')[0]
        add('7.3 목표 메시', stem, '-', 'target mesh score', (O/'meshes'/f'{stem}__gtt_target/score.json').exists())
        add('4 가림 지도', stem, '-', 'occl maps', len(list((O/'stage1'/stem/'occl').glob('*.npz'))) > 0)
        add('7.2 점', stem, '-', 'GTJUDGE rows', (GT/'scenes'/stem/'rows.npz').exists())
        for nm, p in [('addendum6 points sel', 'points/sel'), ('addendum6 ra within', 'ra/within'), ('addendum6 da labels', 'da/labels'), ('addendum6 ga patch', 'ga/patch'), ('addendum6 ba causes', 'ba/causes')]:
            add('2.2 본 방법 판', stem, 'FT', nm, (TE6/f'{p}_{stem}.npz').exists())
        add('2.2 본 방법 판', stem, 'FT', 'FT 30000 ply', (FTR/'runs'/site/f'ft_{stem.split("__")[1]}_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply').exists())
        add('2.2 패치 다수결 판', stem, 'A-1', 'GTJUDGE addendum11 final_data', (GT/'addendum11/final_data'/f'{stem}.npz').exists())
    table('stage3_inventory', rows); bad = [r for r in rows if not r['ok']]
    print('INVENTORY', len(rows), 'items,', len(bad), 'missing'); [print(' MISSING', r['item'], r['stem'], r['run'], r['what'], r['note']) for r in bad]
if __name__ == '__main__': main()
