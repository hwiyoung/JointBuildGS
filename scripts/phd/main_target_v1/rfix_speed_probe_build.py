"""Observation-only speed candidate operands; never used for training."""
import shutil,re,sys
from torch.utils.cpp_extension import load
from common import *
ROOT=OUT/'rfix_speed'
CODE=r'''
// Read-only, task-local per-pixel operands of the native atomic additions.
__device__ int rf_probe_n=0;
__device__ const int* rf_probe_ids=nullptr;
__device__ float* rf_probe_terms=nullptr;
__device__ int rf_probe_hw=0;
void rf_probe_set_raw(int n,const int* ids,float* terms,int hw) {
 cudaMemcpyToSymbol(rf_probe_n,&n,sizeof(n));cudaMemcpyToSymbol(rf_probe_ids,&ids,sizeof(ids));
 cudaMemcpyToSymbol(rf_probe_terms,&terms,sizeof(terms));cudaMemcpyToSymbol(rf_probe_hw,&hw,sizeof(hw));
}
__device__ __forceinline__ void rf_probe_atomic(float* dst,float value,int id,int pix,int channel) {
 for(int k=0;k<rf_probe_n;k++)if(id==rf_probe_ids[k])rf_probe_terms[(k*18+channel)*rf_probe_hw+pix]=value;
 atomicAdd(dst,value);
}
'''
EXT=r'''
void rf_probe_set_raw(int n,const int* ids,float* terms,int hw);
void rf_probe_set(torch::Tensor ids,torch::Tensor terms) {
 rf_probe_set_raw(ids.numel(),ids.data_ptr<int>(),terms.data_ptr<float>(),terms.size(2));
}
'''
def main():
 root=ROOT/'gradient_probe';root.mkdir(exist_ok=False)
 for variant in ['fixed']:
  base=ROOT/'inventory/target/source' if variant=='original' else ROOT/'builds/target/source';src=root/variant/'source';shutil.copytree(base,src);p=src/'cuda_rasterizer/backward.cu';s=p.read_text();s=s.replace('#include "auxiliary.h"','#include "auxiliary.h"\n'+CODE)
  lines=[];replacements=[]
  for line in s.splitlines(True):
   if 'atomicAdd(' in line and 'global_id' in line:
    code,comment=(line.split('//',1)+[''])[:2] if '//' in line else (line,'')
    m=re.search(r'atomicAdd\((.*),\s*(.*?)\);',code);assert m,line;dest,value=m.groups()
    if 'dL_dcolors' in dest:ch='ch'
    elif 'dL_dnormal3D' in dest:ch='3+ch'
    elif 'dL_dtransMat' in dest:ch=str(6+int(re.search(r'\+ (\d+)\]',dest).group(1)))
    elif 'dL_dmean2D' in dest:ch='15' if '.x' in dest else '16'
    elif 'dL_dopacity' in dest:ch='17'
    else:raise ValueError(line)
    line=line.replace(m.group(0),f'rf_probe_atomic({dest},{value},global_id,pix_id,{ch});');replacements.append(dict(destination=dest,channel=ch))
   lines.append(line)
  assert len(replacements)==17,len(replacements);p.write_text(''.join(lines));p=src/'ext.cpp';s=p.read_text().replace('PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {',EXT+'\nPYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {\n m.def("rf_probe_set",&rf_probe_set);');p.write_text(s);build=root/variant/'extension';build.mkdir()
  dump(root/variant/'lock.json',dict(at=stamp(),code_sha256=sha(__file__),files={str(p):sha(p) for p in src.rglob('*') if p.is_file()},atomic_operands=replacements,acceptance_use=True,scientific_verdict=None))
  mod=load(name='jbgs_rfix_speed_probe_'+variant,sources=[str(src/p) for p in ['cuda_rasterizer/rasterizer_impl.cu','cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','rasterize_points.cu','ext.cpp']],extra_include_paths=[str(src/'third_party/glm')],extra_cuda_cflags=['-I'+str(src/'third_party/glm')],build_directory=str(build),verbose=True)
  dump(root/variant/'build.json',dict(at=stamp(),extension_sha256=sha(mod.__file__),acceptance_use=True,scientific_verdict=None))
if __name__=='__main__':main()
