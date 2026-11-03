"""Separate additive renderer build. No original source or installed library writes."""
import shutil,difflib,os,sys
from common import *
from torch.utils.cpp_extension import load
import r8_record_prepare as guard
ROOT=OUT/'rfix'
def main():
 label=sys.argv[1];base=ROOT/'inventory'/label/'source';dest=ROOT/'builds'/label;dest.mkdir(parents=True,exist_ok=False);src=dest/'source';shutil.copytree(base,src)
 p=src/'cuda_rasterizer/rasterizer_impl.cu';old=p.read_text();new=old
 marker='#include "auxiliary.h"';assert new.count(marker)==1;new=new.replace(marker,marker+'\n#include "rfix_tiles.cuh"')
 header=Path(__file__).with_name('rfix_tiles.cuh');shutil.copyfile(header,src/'cuda_rasterizer/rfix_tiles.cuh')
 a='\tint* radii,\n\tdim3 grid)';b='\tint* radii, int W, int H, const float* rf_mat, const float4* rf_no,\n\tdim3 grid)';assert new.count(a)==1;new=new.replace(a,b)
 a='\t\t\t\tuint64_t key = y * grid.x + x;';assert new.count(a)==1;new=new.replace(a,'\t\t\t\tif (!rf_tile(x,y,W,H,points_xy[idx],rf_mat+9*idx,rf_no[idx].w)) continue;\n'+a)
 a='\t// Compute prefix sum over full list of touched tile counts by Gaussians';assert new.count(a)==1;new=new.replace(a,'\trf_count<<<(P+255)/256,256>>>(P,width,height,radii,geomState.means2D,transMat_precomp ? transMat_precomp : geomState.transMat,geomState.normal_opacity,geomState.tiles_touched,tile_grid);\n\tCHECK_CUDA(, debug)\n\n'+a)
 a='\t\tradii,\n\t\ttile_grid)';assert new.count(a)==1;new=new.replace(a,'\t\tradii, width, height, transMat_precomp ? transMat_precomp : geomState.transMat, geomState.normal_opacity,\n\t\ttile_grid)')
 marker='// Forward rendering procedure for differentiable rasterization';assert new.count(marker)==1;new=new.replace(marker,guard.CPP+'\n'+marker)
 a='\tsize_t binning_chunk_size = required<BinningState>(num_rendered);';assert new.count(a)==1;new=new.replace(a,a+'\n'+guard.CHECK);p.write_text(new)
 diffs=[''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/cuda_rasterizer/rasterizer_impl.cu',tofile='b/cuda_rasterizer/rasterizer_impl.cu'))]
 p=src/'ext.cpp';old=p.read_text();new=old.replace('PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {',guard.EXT+'\nPYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {\n  m.def("jbgs_set_guard", &jbgs_set_guard);\n  m.def("jbgs_get_guard", &jbgs_get_guard);\n  m.def("jbgs_get_guard_tiles", &jbgs_get_guard_tiles);')
 assert new!=old;p.write_text(new);diffs.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/ext.cpp',tofile='b/ext.cpp')))
 diffs.append(''.join(difflib.unified_diff([],header.read_text().splitlines(True),fromfile='/dev/null',tofile='b/cuda_rasterizer/rfix_tiles.cuh')))
 (dest/'renderer.patch').write_text('\n'.join(diffs));build=dest/'extension';build.mkdir()
 dump(CFG/('rfix_build_'+label+'.lock.json'),dict(at=stamp(),files={str(p):sha(p) for p in src.rglob('*') if p.is_file()},builder_sha256=sha(__file__),scientific_verdict=None))
 mod=load(name='jbgs_rfix_'+label,sources=[str(src/p) for p in ['cuda_rasterizer/rasterizer_impl.cu','cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','rasterize_points.cu','ext.cpp']],extra_include_paths=[str(src/'third_party/glm')],extra_cuda_cflags=['-I'+str(src/'third_party/glm')],build_directory=str(build),verbose=True)
 dump(dest/'receipt.json',dict(at=stamp(),status='BUILT',extension=mod.__file__,extension_sha256=sha(mod.__file__),patch_sha256=sha(dest/'renderer.patch'),scientific_verdict=None));print('BUILT',label,flush=True)
if __name__=='__main__':main()
