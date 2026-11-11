"""Host driver (stdlib only) for te_sim.py: prep (container) -> unchanged mesh recipe (te_mesh via launch.gtj) -> full score -> eval (container) -> clean.
usage: te_simhost.py <gpu> <stem> <arm> <prefix> <cls> [<cls> ...]"""
import json, sys
import launch as Lc
from te_pipeline import must
POP = {'3-라': 'bg', '3-다': 'rel', '3-나': 'nbr', '3-가': 'same'}
def main(gpu, stem, arm, prefix, *classes):
    for cls in classes:
        fam = f'{prefix}_{arm}_{POP[cls]}'; wd = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final_work'; final = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final.ply'
        if not (Lc.O/'sim'/f'{stem}__{fam}'/'prep.json').exists(): must(Lc.job('te_sim.py', 'prep', stem, arm, cls, prefix, cpus=12, memory='40g'), 'prep')
        ply = f'/te/sim/{stem}__{fam}/point_cloud.ply'
        if not final.exists():
            if not (Lc.O/'gtj/renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(Lc.gtj('render', stem, fam, ply, int(gpu)), 'render')
            if not (wd/'binding.json').exists(): must(Lc.gtj('prepare', stem, fam), 'prepare')
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
