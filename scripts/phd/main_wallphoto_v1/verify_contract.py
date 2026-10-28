"""Before curves: independently bind unchanged numerical functions and input identity."""
import ast
from common import *
def main():
    ref=Path('/repo/scripts/phd/main_photocheck_v1');rows=[]
    for name,functions in [('prepare.py',['group']),('cameras.py',['Cameras','mesh_scene','select_photos']),('curves.py',['project_torch','compute','height_array']),('features.py',['derive'])]:
        original=ref/name;current=S/name
        a=original.read_text().replace('photocheck_v1.json','wallphoto_v1.json');b=current.read_text()
        defs=lambda s:{n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        da,db=defs(a),defs(b)
        for f in functions:assert da[f]==db[f],(name,f)
        rows.append(dict(file=name,functions=functions,status='IDENTICAL_AST_AFTER_CONFIG_FILENAME_ONLY',reference_sha256=sha(original),current_sha256=sha(current)))
    cfg=load(C/'wallphoto_v1.json');refcfg=load('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json')
    unchanged=['frame','sources','points','uncertainty','heights','photos','score','judgments','projection_gate','evaluation']
    for k in unchanged:assert cfg[k]==refcfg[k],k
    assert sha('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json')==cfg['reference']['config_sha256']
    assert sha(C/'wallphoto_v1.json')==load(C/'wallphoto_v1.lock.json')['sha256']
    inputs=[]
    for p in [W/'image_split.json',W/'building_split.json',W/'inputs/image_inventory.json',CAL/'cameras.txt',DENSE/'sparse/images.bin']:
        inputs.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
    record=dict(status='PASS',at=now(),unchanged_config_sections=unchanged,numerical_functions=rows,inputs=inputs,scientific_verdict=None,environment=env())
    dump(O/'gates/reference_contract.json',record);dump(D/'tables/reference_contract.json',record)
    print('unchanged reference contract PASS',flush=True)
if __name__=='__main__':main()
