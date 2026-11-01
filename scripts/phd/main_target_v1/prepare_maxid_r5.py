"""Copy pinned renderer into task payload and add diagnostic argmax; no training module edits."""
import shutil
from common import *
src=Path('/opt/geogs-source/submodules/diff-surfel-rasterization');dst=OUT/'r5/runtime/maxid_rasterizer'
assert not dst.exists();shutil.copytree(src,dst,ignore=shutil.ignore_patterns('build','*.so','__pycache__','.git'))
f=dst/'cuda_rasterizer/forward.cu';before=f.read_text();after=before.replace('float T = 1.0f;','float T = 1.0f;\n\tfloat diag_max_w = -1.0f; int diag_max_id = -1;')
after=after.replace('float w = alpha * T;','float w = alpha * T;\n\t\t\tif (w > diag_max_w) { diag_max_w = w; diag_max_id = collected_id[j]; }')
after=after.replace('out_others[pix_id + DISTORTION_OFFSET * H * W] = distortion;','out_others[pix_id + DISTORTION_OFFSET * H * W] = float(diag_max_id + 1);')
assert after!=before and after.count('diag_max_id + 1')==1;f.write_text(after)
dump(OUT/'r5/runtime/maxid_binding.json',dict(at=stamp(),source_image='jointbuildgs:geogs-conf-guided-v1',source_files={str(p.relative_to(src)):sha(p) for p in src.rglob('*') if p.is_file() and p.suffix in ['.cu','.h','.cpp']},modified_file=str(f),modified_sha256=sha(f),change='DISTORTION output replaced by 1+argmax(alpha*T), ties first in actual tile traversal. Depth, alpha, RGB computation unchanged. Inference only; no backward.',scientific_verdict=None))
print('PREPARED_MAXID')
