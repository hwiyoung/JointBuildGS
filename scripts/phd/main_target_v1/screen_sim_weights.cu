// Read-only rendering accounting over the ORIGINAL forward's sorted tile buffers.
// No training code, parameter updates, gradients, or backward kernels.
#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <cuda_runtime.h>
#include <vector>
__global__ void account(const uint2* ranges,const unsigned* ids,const float2* xy,
 const float* mat,const float4* no,const float3* color,const bool* roi,
 double* sums,double* roi_sums,float* maxima,float* image,int W,int H){
 int x=blockIdx.x*16+threadIdx.x,y=blockIdx.y*16+threadIdx.y,t=threadIdx.y*16+threadIdx.x;
 int HW=W*H,idx=y*W+x;bool done=x>=W||y>=H;
 uint2 range=ranges[blockIdx.y*gridDim.x+blockIdx.x];
 __shared__ unsigned si[256];__shared__ float2 sx[256];
 __shared__ float3 su[256],sv[256],sw[256],sc[256];__shared__ float so[256];
 float T=1.f,C0=0.f,C1=0.f,C2=0.f;
 for(unsigned base=range.x;base<range.y;base+=256){
  if(__syncthreads_count(done)==256)break;
  unsigned at=base+t;if(at<range.y){unsigned id=ids[at];si[t]=id;sx[t]=xy[id];
   su[t]=make_float3(mat[id*9],mat[id*9+1],mat[id*9+2]);
   sv[t]=make_float3(mat[id*9+3],mat[id*9+4],mat[id*9+5]);
   sw[t]=make_float3(mat[id*9+6],mat[id*9+7],mat[id*9+8]);so[t]=no[id].w;sc[t]=color[id];}
  __syncthreads();
  for(int j=0;!done&&j<min(256,int(range.y-base));j++){
   float3 u=su[j],v=sv[j],q=sw[j];
   float3 k=make_float3(x*q.x-u.x,x*q.y-u.y,x*q.z-u.z);
   float3 l=make_float3(y*q.x-v.x,y*q.y-v.y,y*q.z-v.z);
   float3 p=make_float3(k.y*l.z-k.z*l.y,k.z*l.x-k.x*l.z,k.x*l.y-k.y*l.x);
   if(p.z==0.f)continue;float a=p.x/p.z,b=p.y/p.z;
   float dx=sx[j].x-x,dy=sx[j].y-y;
   float rho=fminf(a*a+b*b,2.f*(dx*dx+dy*dy));
   float depth=(a*q.x+b*q.y)+q.z;if(depth<.2f)continue;
   float power=-.5f*rho;if(power>0.f)continue;
   float alpha=fminf(.99f,so[j]*expf(power));if(alpha<1.f/255.f)continue;
   float next=T*(1.f-alpha);if(next<.0001f){done=true;continue;}
   float weight=alpha*T;unsigned id=si[j];atomicAdd(sums+id,(double)weight);
   if(roi[idx])atomicAdd(roi_sums+id,(double)weight);
   atomicMax((int*)(maxima+id),__float_as_int(weight));
   C0+=sc[j].x*weight;C1+=sc[j].y*weight;C2+=sc[j].z*weight;T=next;
  }
 }
 if(x<W&&y<H){image[idx]=C0;image[HW+idx]=C1;image[2*HW+idx]=C2;image[3*HW+idx]=1.f-T;}
}
torch::Tensor weights(torch::Tensor ranges,torch::Tensor ids,torch::Tensor xy,
 torch::Tensor mat,torch::Tensor no,torch::Tensor color,torch::Tensor roi,
 torch::Tensor sums,torch::Tensor roi_sums,torch::Tensor maxima,int W,int H){
 auto im=torch::zeros({4,H,W},xy.options());dim3 block(16,16),grid((W+15)/16,(H+15)/16);
 account<<<grid,block,0,at::cuda::getCurrentCUDAStream()>>>((uint2*)ranges.data_ptr<int>(),
  (unsigned*)ids.data_ptr<int>(),(float2*)xy.data_ptr<float>(),mat.data_ptr<float>(),
  (float4*)no.data_ptr<float>(),(float3*)color.data_ptr<float>(),roi.data_ptr<bool>(),
  sums.data_ptr<double>(),roi_sums.data_ptr<double>(),maxima.data_ptr<float>(),im.data_ptr<float>(),W,H);
 auto error=cudaGetLastError();TORCH_CHECK(error==cudaSuccess,cudaGetErrorString(error));return im;
}
PYBIND11_MODULE(TORCH_EXTENSION_NAME,m){m.def("weights",&weights);}
