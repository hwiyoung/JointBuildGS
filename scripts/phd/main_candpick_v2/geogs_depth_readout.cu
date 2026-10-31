#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAException.h>
#include <cmath>

// GeoGS forward.cu: skip depth < near_n before updating transmittance;
// alpha cap .99; exclusive termination below .0001; expected depth / alpha.
// Use the unchanged gsplat projected discs, pixel centers and tile ordering.
__global__ void read_depth(
    const float* means, const float* rays, const float* opacities,
    const float* centers, const int* offsets, const int* ids,
    const int64_t* pixels, int np, int width, int tiles_x, int tiles_n,
    int intersections, float* result, int* counts) {
    int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j>=np)return;
    int64_t pixel=pixels[j]; int x=pixel%width,y=pixel/width;
    float px=x+.5f,py=y+.5f;
    int tile=(y/16)*tiles_x+x/16;
    int start=offsets[tile],end=tile+1<tiles_n?offsets[tile+1]:intersections;
    float trans=1.f,alpha_sum=0.f,moment=0.f,center_moment=0.f;
    int used=0,near_skip=0,nonfinite=0;
    for(int k=start;k<end;k++) {
        int g=ids[k];const float* r=rays+9*g;
        float kx=px*r[6]-r[0],ky=px*r[7]-r[1],kz=px*r[8]-r[2];
        float lx=py*r[6]-r[3],ly=py*r[7]-r[4],lz=py*r[8]-r[5];
        float cx=ky*lz-kz*ly,cy=kz*lx-kx*lz,cz=kx*ly-ky*lx;
        if(cz==0.f)continue;
        float sx=cx/cz,sy=cy/cz;
        float depth=sx*r[6]+sy*r[7]+r[8];
        if(!isfinite(depth)){nonfinite++;continue;}
        if(depth<.2f){near_skip++;continue;}
        float dx=means[2*g]-px,dy=means[2*g+1]-py;
        float rho=fminf(sx*sx+sy*sy,2.f*(dx*dx+dy*dy));
        float power=-.5f*rho;
        if(!isfinite(power)){nonfinite++;continue;}
        if(power>0.f)continue;
        float alpha=fminf(.99f,opacities[g]*expf(power));
        if(alpha<1.f/255.f)continue;
        float next_trans=trans*(1.f-alpha);
        if(next_trans<.0001f)break;
        float weight=alpha*trans;
        alpha_sum+=weight;moment+=weight*depth;center_moment+=weight*centers[g];
        trans=next_trans;used++;
    }
    result[j*3]=alpha_sum>0.f?moment/alpha_sum:NAN;
    result[j*3+1]=alpha_sum;
    result[j*3+2]=alpha_sum>0.f?center_moment/alpha_sum:NAN;
    counts[j*3]=used;counts[j*3+1]=near_skip;counts[j*3+2]=nonfinite;
}

std::vector<torch::Tensor> forward(
    torch::Tensor means,torch::Tensor rays,torch::Tensor opacity,
    torch::Tensor centers,torch::Tensor offsets,torch::Tensor ids,
    torch::Tensor pixels,int64_t width) {
    TORCH_CHECK(means.is_cuda()&&rays.is_cuda()&&pixels.is_cuda());
    TORCH_CHECK(means.scalar_type()==torch::kFloat32&&rays.scalar_type()==torch::kFloat32);
    TORCH_CHECK(offsets.scalar_type()==torch::kInt32&&ids.scalar_type()==torch::kInt32);
    TORCH_CHECK(pixels.scalar_type()==torch::kInt64);
    auto result=torch::empty({pixels.numel(),3},means.options());
    auto counts=torch::empty({pixels.numel(),3},offsets.options());
    int tiles_x=offsets.size(-1);
    read_depth<<<(pixels.numel()+255)/256,256,0,at::cuda::getCurrentCUDAStream()>>>(
        means.data_ptr<float>(),rays.data_ptr<float>(),opacity.data_ptr<float>(),
        centers.data_ptr<float>(),offsets.data_ptr<int>(),ids.data_ptr<int>(),
        pixels.data_ptr<int64_t>(),pixels.numel(),width,tiles_x,offsets.numel(),ids.numel(),
        result.data_ptr<float>(),counts.data_ptr<int>());
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return {result,counts};
}
PYBIND11_MODULE(TORCH_EXTENSION_NAME,m){m.def("forward",&forward);}
