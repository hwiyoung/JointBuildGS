"""Create a new bounded source snapshot from the immutable MVS parent."""
from pathlib import Path
import json
import shutil
import importlib.util


def prepare(parent,destination,repo):
    repo=Path(repo);parent=Path(parent);destination=Path(destination)
    spec=importlib.util.spec_from_file_location('baseline',repo/'scripts/phd/p1_single_view_weight_v1/prepare_source.py')
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    if destination.exists(): raise FileExistsError(destination)
    if any(p.is_symlink() for p in parent.rglob('*')): raise ValueError('No source symlinks')
    provenance=json.loads((parent/'mvs_pgsr_source_provenance.json').read_text())
    original=base.implementation_hashes(parent)
    if original!=provenance['prepared_implementation_hashes']: raise ValueError('Parent snapshot changed')
    for name,expected in base.EXPECTED_PARENT.items():
        if original[name]!=expected: raise ValueError('Unexpected parent')
    parent_payload=base.payload_hashes(parent)
    train=(parent/'train.py').read_text()
    train=base.replace_once(train,'import jbgs_mvs_pgsr\n','import jbgs_mvs_pgsr\nimport jbgs_region_weight\n','import')
    train=base.replace_once(train,base.INIT_BLOCK,base.INIT_BLOCK+'    region_weight_control = jbgs_region_weight.Controller(dataset.model_path, args, mvs_pgsr_control)\n','controller')
    train=base.replace_once(train,base.RAW_BLOCK,base.RAW_BLOCK+'\n        da_depth_loss = region_weight_control.apply(render_pkg["surf_depth"], da_depth, da_depth_loss, camera=cam_name, iteration=iteration)','objective')
    state=(parent/'jbgs_state.py').read_text()
    state=base.replace_once(state,base.RESUME_IMPORT,'    from jbgs_region_weight import verify_resume_source\n','source lineage')
    state=base.replace_once(state,base.ALLOWED_BLOCK,base.ALLOWED_REPLACEMENT,'fixed controller')
    line="    receipt['restore_equivalence'] = restore_equivalence\n"
    state=base.replace_once(state,line,line+"    receipt['declared_dynamic_depth_weight_change'] = [state['args']['dynamic_depth_weight'], args.dynamic_depth_weight]\n",'restore receipt')
    helpers={'jbgs_weight_core.py':repo/'src/phd/p1_single_view_weight_v1/loss.py','jbgs_region_weight.py':repo/'src/phd/region_weight_v1/loss.py'}
    for name,value in {'train.py':train,'jbgs_state.py':state,**{k:v.read_bytes() for k,v in helpers.items()}}.items():compile(value,name,'exec')
    shutil.copytree(parent,destination,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (destination/'train.py').write_text(train);(destination/'jbgs_state.py').write_text(state)
    for name,file in helpers.items():shutil.copyfile(file,destination/name)
    prepared_payload=base.payload_hashes(destination)
    changed=sorted(k for k in parent_payload if prepared_payload.get(k)!=parent_payload[k])
    added=sorted(set(prepared_payload)-set(parent_payload))
    if changed!=['jbgs_state.py','train.py'] or added!=sorted(helpers):raise ValueError('Patch scope exceeded')
    if base.payload_hashes(parent)!=parent_payload:raise ValueError('Parent changed during preparation')
    receipt=dict(schema='JBGS_REGION_WEIGHT_SOURCE_v1',scientific_verdict=None,
        parent_source_provenance_sha256=base.sha(parent/'mvs_pgsr_source_provenance.json'),
        ancestor_anchor_implementation_hashes=provenance['parent_implementation_hashes'],
        parent_implementation_hashes=original,prepared_implementation_hashes=base.implementation_hashes(destination),
        parent_payload_hashes=parent_payload,prepared_payload_hashes=prepared_payload,
        changed_parent_files=changed,added_files=added,helper_sha256={k:base.sha(destination/k) for k in helpers},
        policy='Every bound P2/P3 depth uses frozen R1/R2/R3; R1 alpha, other used 1, excluded 0; original valid denominator; RGB unchanged; fixed MVS .05 and prior .005; native protection',
        preparer_sha256=base.sha(__file__))
    (destination/'region_weight_source_provenance.json').write_text(json.dumps(receipt,indent=2))
    return receipt
