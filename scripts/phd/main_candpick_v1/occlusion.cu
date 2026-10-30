#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <cuda_runtime.h>

__global__ void query_kernel(const float* xy, const float* rays, const float* opacity,
    const int* offsets, const int* ids, int ni, int tw, int th,
    const float* query, int nq, float* output) {
    int q=blockIdx.x*blockDim.x+threadIdx.x;
    if(q>=nq) return;
    float px=query[q*3], py=query[q*3+1], limit=query[q*3+2];
    int tile=int(py)/16*tw+int(px)/16;
    int begin=offsets[tile], end=tile+1==tw*th?ni:offsets[tile+1];
    float T=1.f;
    for(int i=begin;i<end;i++) {
        int g=ids[i]; const float* m=rays+g*9;
        float ux=px*m[6]-m[0], uy=px*m[7]-m[1], uz=px*m[8]-m[2];
        float vx=py*m[6]-m[3], vy=py*m[7]-m[4], vz=py*m[8]-m[5];
        float cz=ux*vy-uy*vx;
        if(cz==0.f) continue;
        float sx=(uy*vz-uz*vy)/cz, sy=(uz*vx-ux*vz)/cz;
        float depth=m[6]*sx+m[7]*sy+m[8];
        if(depth>=limit) continue;
        float dx=xy[g*2]-px, dy=xy[g*2+1]-py;
        float sigma=.5f*fminf(sx*sx+sy*sy,2.f*(dx*dx+dy*dy));
        float alpha=fminf(.999f,opacity[g]*__expf(-sigma));
        if(sigma<0.f || alpha<1.f/255.f) continue;
        float next=T*(1.f-alpha);
        if(next<=1.e-4f) break;
        T=next;
    }
    output[q]=T;
}

torch::Tensor cand_transmittance(torch::Tensor xy, torch::Tensor rays,
    torch::Tensor opacity, torch::Tensor offsets, torch::Tensor ids,
    torch::Tensor query, int64_t tw, int64_t th) {
    TORCH_CHECK(xy.is_cuda() && rays.is_cuda() && opacity.is_cuda() &&
        offsets.is_cuda() && ids.is_cuda() && query.is_cuda(), "CUDA required");
    TORCH_CHECK(xy.is_contiguous() && rays.is_contiguous() && opacity.is_contiguous() &&
        offsets.is_contiguous() && ids.is_contiguous() && query.is_contiguous(), "contiguous required");
    TORCH_CHECK(offsets.scalar_type()==torch::kInt32 && ids.scalar_type()==torch::kInt32,
        "gsplat intersection indices must be int32");
    auto out=torch::empty({query.size(0)},query.options());
    if(query.size(0)) query_kernel<<<(query.size(0)+255)/256,256,0,at::cuda::getCurrentCUDAStream()>>>(
        xy.data_ptr<float>(),rays.data_ptr<float>(),opacity.data_ptr<float>(),
        offsets.data_ptr<int>(),ids.data_ptr<int>(),ids.numel(),tw,th,
        query.data_ptr<float>(),query.size(0),out.data_ptr<float>());
    return out;
}
