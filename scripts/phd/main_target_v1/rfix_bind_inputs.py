"""Bind reused simulation products to their previously sealed receipts."""
from r8_screen_prepare import R,O,C,j,sha,local,docker,dump
import datetime
ROOT=O/'rfix'
def main():
 old=O/'screen_sim/handover/PHD-MAIN-TARGET-v1_화면크기정리모의_1103-0255';manifest=old/'external_payloads.json';known={r['path']:r for r in j(manifest)['files']};rows=[]
 for state in j(C/'rfix.json')['states']:
  key=state['key'];root=O/'screen_sim/states'/key
  for name in ['groups.npz','gaussians.npz','contribution.json']:
   p=root/name;previous=known[docker(p)]['sha256'];current=sha(p);assert current==previous,str(p);rows.append(dict(path=docker(p),sha256=current,previous_receipt=str(manifest),first_binding='previous sealed simulation delivery',verified_now=True))
  module=root/'account_build/screen_sim_weights.so';previous=j(root/'contribution.json')['account_module_sha256'];assert sha(module)==previous;rows.append(dict(path=docker(module),sha256=previous,previous_receipt=docker(root/'contribution.json'),first_binding='previous simulation producer receipt, itself in sealed manifest',verified_now=True))
 dump(ROOT/'reused_input_bindings.json',dict(at=datetime.datetime.now().astimezone().isoformat(),files=rows,prior_external_manifest_sha256=sha(manifest),note='Task settings and original model/source inputs were locked before calculation. These derived simulation products retain their earlier sealed producer/delivery bindings; current verification is explicitly timestamped after the first rfix renders.',scientific_verdict=None))
if __name__=='__main__':main()
