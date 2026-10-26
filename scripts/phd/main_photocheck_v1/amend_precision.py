"""Record a numerical-precision amendment; all scientific rules remain frozen."""
from common import *
def main():
    p=C/'photocheck_v1.json';old=load(p);previous=sha(p)
    if any(a.get('id')=='projection_float64' for a in old['amendments']):return
    dump(C/'photocheck_v1_r0.json',old);dump(C/'photocheck_v1_r0.lock.json',load(C/'photocheck_v1.lock.json'))
    old['amendments'].append(dict(id='projection_float64',at=now(),previous_sha256=previous,reason='On 256 identical benchmark points CPU/GPU float32 projection led to max stored curve difference 0.003143310546875, with all 3840 candidate decisions equal. Raise world-to-image arithmetic to float64 before native float32 interpolation. No GT, threshold or selection change. First full pilot curves not started.',previous=old['score']['dtype_compute']))
    old['score']['dtype_compute']='float64 geometry and projection; float32 image interpolation and NCC; float16 stored curve'
    dump(p,old);dump(C/'photocheck_v1.lock.json',dict(at=now(),sha256=sha(p),before_full_pilot=True,amendment='projection_float64',previous_sha256=previous,environment=env()))
    folder=O/'benchmark/float32_projection';folder.mkdir(exist_ok=True)
    for f in (O/'benchmark').glob('*'): 
        if f.is_file():f.rename(folder/f.name)
    if (O/'gates/benchmark.json').exists():(O/'gates/benchmark.json').rename(folder/'comparison.json')
    print('precision amendment locked',sha(p))
if __name__=='__main__':main()
