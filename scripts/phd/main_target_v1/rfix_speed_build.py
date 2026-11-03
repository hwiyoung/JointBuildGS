"""Separate speed candidate; never loaded by the authorized rfix training run."""
import sys,shutil,difflib
from common import *
from torch.utils.cpp_extension import load
ROOT=OUT/'rfix_speed'
def main():
 label=sys.argv[1];base=OUT/'rfix/builds'/label/'source';dest=ROOT/'builds'/label;dest.mkdir(parents=True,exist_ok=False);src=dest/'source';shutil.copytree(base,src)
 p=src/'cuda_rasterizer/rfix_tiles.cuh';old=p.read_text();new=old[:old.index('__global__ void rf_count')]
 new+='''
// Small native rectangles keep their original registration. Larger rectangles
// use conservative coarse rejection followed by the exact original tile test.
__device__ __forceinline__ bool rf_coarse(int ax,int ay,int bx,int by,int W,int H,float2 xy,const float* m,float o) {
 if (isfinite(o) && o < 1.f/255.f) return false;
 float3 u={m[0],m[1],m[2]},v={m[3],m[4],m[5]},w={m[6],m[7],m[8]};
 return rf_possible_interval(ax*BLOCK_X,min(bx*BLOCK_X,W)-1,ay*BLOCK_Y,min(by*BLOCK_Y,H)-1,xy,u,v,w,o);
}
__global__ void rf_count(int P,int W,int H,const int* radii,const float2* xy,const float* mat,const float4* no,uint32_t* counts,dim3 grid) {
 int idx=blockIdx.x*blockDim.x+threadIdx.x;if(idx>=P)return;
 if(radii[idx]<=0){counts[idx]=0;return;}
 uint2 a,b;getRect(xy[idx],radii[idx],a,b,grid);unsigned area=(b.x-a.x)*(b.y-a.y),count=0;
 if(area<=16){counts[idx]=area;return;}
 for(int cy=a.y;cy<b.y;cy+=4)for(int cx=a.x;cx<b.x;cx+=4){
  int ex=min(cx+4,int(b.x)),ey=min(cy+4,int(b.y));
  if(!rf_coarse(cx,cy,ex,ey,W,H,xy[idx],mat+9*idx,no[idx].w))continue;
  for(int y=cy;y<ey;y++)for(int x=cx;x<ex;x++)count+=rf_tile(x,y,W,H,xy[idx],mat+9*idx,no[idx].w);
 }
 counts[idx]=count;
}
''';p.write_text(new);diffs=[''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/cuda_rasterizer/rfix_tiles.cuh',tofile='b/cuda_rasterizer/rfix_tiles.cuh'))]
 p=src/'cuda_rasterizer/rasterizer_impl.cu';old=p.read_text();a=old.index('\t\tfor (int y = rect_min.y;');b=old.index('\n\t}\n}',a);original=old[a:b]
 keybody=original[original.index('\t\t\t\tuint64_t key'):original.rindex('\n\t\t\t}')]
 newloop='''
        unsigned area=(rect_max.x-rect_min.x)*(rect_max.y-rect_min.y);
        for(int cy=rect_min.y;cy<rect_max.y;cy+=4)for(int cx=rect_min.x;cx<rect_max.x;cx+=4){
          int ex=min(cx+4,int(rect_max.x)),ey=min(cy+4,int(rect_max.y));
          if(area>16 && !rf_coarse(cx,cy,ex,ey,W,H,points_xy[idx],rf_mat+9*idx,rf_no[idx].w))continue;
          for(int y=cy;y<ey;y++)for(int x=cx;x<ex;x++){
            if(area>16 && !rf_tile(x,y,W,H,points_xy[idx],rf_mat+9*idx,rf_no[idx].w))continue;
'''+keybody+'''
          }
        }
''';new=old[:a]+newloop+old[b:];p.write_text(new);diffs.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/cuda_rasterizer/rasterizer_impl.cu',tofile='b/cuda_rasterizer/rasterizer_impl.cu')))
 (dest/'speed.patch').write_text('\n'.join(diffs));build=dest/'extension';build.mkdir()
 dump(dest/'lock.json',dict(at=stamp(),builder_sha256=sha(__file__),files={str(p):sha(p) for p in src.rglob('*') if p.is_file()},small_native_rectangle_max_tiles=16,coarse_tile_edge=4,training_use=False,scientific_verdict=None))
 mod=load(name='jbgs_rfix_speed_'+label,sources=[str(src/p) for p in ['cuda_rasterizer/rasterizer_impl.cu','cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','rasterize_points.cu','ext.cpp']],extra_include_paths=[str(src/'third_party/glm')],extra_cuda_cflags=['-I'+str(src/'third_party/glm')],build_directory=str(build),verbose=True)
 dump(dest/'receipt.json',dict(at=stamp(),extension_sha256=sha(mod.__file__),training_use=False,scientific_verdict=None));print('SPEED_BUILT',label,flush=True)
if __name__=='__main__':main()
