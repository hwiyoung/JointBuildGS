"""Host driver (stdlib only): c3 view-drop meshes for both arms. usage: te_vdrophost.py <gpu> <stem> <cell> <arm> [<arm>]"""
import json, sys
import launch as Lc
from te_pipeline import must
def main(gpu, stem, cell, *arms):
    for arm in arms:
        fam = f'vdrop_{arm}'; wd = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final_work'; final = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final.ply'
        site, prior = stem.split('__')
        model = f'/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/{site}/ft_{prior}_s0/attempt1/model' if arm == 'own' else \
                f'/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/runs/{site}/gt_{prior}_s0/{"attempt2" if stem == "B0_b10__LoD2" else "attempt1"}/model'
        if not (Lc.O/'sim'/f'{stem}__{fam}'/'drop_views.json').exists(): must(Lc.job('te_viewdrop.py', 'plan', stem, arm, cell), 'plan')
        if not final.exists():
            if not (Lc.O/'gtj/renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(Lc.gtj('render', stem, fam, model+'/point_cloud/iteration_30000/point_cloud.ply', int(gpu)), 'render')
            if not (wd/'binding.json').exists():
                must(Lc.gtj('prepare', stem, fam), 'prepare'); must(Lc.job('te_viewdrop.py', 'apply', stem, fam), 'apply')
            if not (wd/'plan/plan.json').exists(): must(Lc.gtj('plan', stem, fam), 'plan')
            n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
            for k in range(n):
                if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): must(Lc.gtj(f'tile:{k}', stem, fam), f'tile {k}')
            if not (wd/'merged.json').exists():
                if Lc.gtj('merge', stem, fam): must(Lc.gtj('recover', stem, fam), 'recover')
            must(Lc.gtj('finish', stem, fam), 'finish')
        if not (Lc.O/'meshes'/f'{stem}__{fam}'/'score.json').exists(): must(Lc.gtj('score', stem, fam), 'score')
        must(Lc.job('te_sim.py', 'eval', stem, arm, fam), 'eval'); Lc.gtj('clean', stem, fam)
if __name__ == '__main__': main(*sys.argv[1:])
