"""Prepare the same tile-registration-only change for the unrun CDGS adapter."""
import difflib,shutil
from r8_screen_prepare import PH,O,R,dump,sha
HEADER=r'''// CDGS uses a 3D covariance conic, not the 2DGS projective disc.
// Exact native alpha predicate; radii and the native pixel/backward code unchanged.
#pragma once
__device__ bool rf_cd_tile(int tx,int ty,int W,int H,float2 xy,float4 c) {
 for(int y=ty*BLOCK_Y;y<min((ty+1)*BLOCK_Y,H);y++)for(int x=tx*BLOCK_X;x<min((tx+1)*BLOCK_X,W);x++) {
  float2 d={xy.x-float(x),xy.y-float(y)};
  float power=-.5f*(c.x*d.x*d.x+c.z*d.y*d.y)-c.y*d.x*d.y;
  if(power>0.f)continue;
  float alpha=min(.99f,c.w*exp(power));
  if(!(alpha<1.f/255.f))return true;
 }
 return false;
}
__global__ void rf_cd_count(int P,int W,int H,const int* radii,const float2* xy,const float4* conic,uint32_t* counts,dim3 grid) {
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=P)return;
 if(radii[i]<=0){counts[i]=0;return;}
 uint2 a,b;getRect(xy[i],radii[i],a,b,grid);unsigned n=0;
 for(int y=a.y;y<b.y;y++)for(int x=a.x;x<b.x;x++)n+=rf_cd_tile(x,y,W,H,xy[i],conic[i]);
 counts[i]=n;
}
'''
def main():
 src=PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/cdgs-release-adapters-v2/submodules/diff-gaussian-rasterization-depth-acc';root=O/'rfix/cdgs_prepared';root.mkdir(exist_ok=False);p=src/'cuda_rasterizer/rasterizer_impl.cu';old=p.read_text();new=old
 changes=[('#include "auxiliary.h"','#include "auxiliary.h"\n#include "rfix_cdgs_tiles.cuh"'),('\tint* radii,\n\tdim3 grid)','\tint* radii,int W,int H,const float4* rf_conic,\n\tdim3 grid)'),('\t\t\t\tuint64_t key = y * grid.x + x;','\t\t\t\tif(!rf_cd_tile(x,y,W,H,points_xy[idx],rf_conic[idx]))continue;\n\t\t\t\tuint64_t key = y * grid.x + x;'),('\t// Compute prefix sum over full list of touched tile counts by Gaussians','\trf_cd_count<<<(P+255)/256,256>>>(P,width,height,radii,geomState.means2D,geomState.conic_opacity,geomState.tiles_touched,tile_grid);\n\tCHECK_CUDA(, debug)\n\t// Compute prefix sum over full list of touched tile counts by Gaussians'),('\t\tradii,\n\t\ttile_grid)','\t\tradii,width,height,geomState.conic_opacity,\n\t\ttile_grid)')]
 for a,b in changes:assert new.count(a)==1,(a,new.count(a));new=new.replace(a,b)
 diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/cuda_rasterizer/rasterizer_impl.cu',tofile='b/cuda_rasterizer/rasterizer_impl.cu'))+'\n'+''.join(difflib.unified_diff([],HEADER.splitlines(True),fromfile='/dev/null',tofile='b/cuda_rasterizer/rfix_cdgs_tiles.cuh'));(root/'renderer.patch').write_text(diff)
 # Dry-run in original source only; nothing is applied there.
 result=__import__('subprocess').run(['git','apply','--check',str((root/'renderer.patch').resolve())],cwd=src,text=True,capture_output=True);assert result.returncode==0,result.stderr
 dump(root/'receipt.json',dict(status='PREPARED_NOT_APPLIED',source=str(src),original_sha256=sha(p),patch_sha256=sha(root/'renderer.patch'),apply_check=result.returncode,original_training='NOT_EXECUTED: all requested CDGS arms stopped in preparation READY.json',build='not substituted or installed',scientific_verdict=None))
if __name__=='__main__':main()
