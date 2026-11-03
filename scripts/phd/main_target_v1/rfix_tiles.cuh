// Tile registration only. Original preprocess, radii, forward/backward math unchanged.
// A tile is retained iff at least one valid integer pixel passes the original
// per-splat alpha and near predicates. Transmittance is deliberately not used.
// Outward-rounded interval rejection is only a shortcut to the exact predicate.
#pragma once
#include <math_constants.h>
struct RFInterval { float lo, hi; };
__device__ __forceinline__ RFInterval rf_const(float a) { return {a,a}; }
__device__ __forceinline__ RFInterval rf_add(RFInterval a,RFInterval b) {return {__fadd_rd(a.lo,b.lo),__fadd_ru(a.hi,b.hi)};}
__device__ __forceinline__ RFInterval rf_sub(RFInterval a,RFInterval b) {return {__fsub_rd(a.lo,b.hi),__fsub_ru(a.hi,b.lo)};}
__device__ __forceinline__ RFInterval rf_mul(RFInterval a,RFInterval b) {
 float lo=fminf(fminf(__fmul_rd(a.lo,b.lo),__fmul_rd(a.lo,b.hi)),fminf(__fmul_rd(a.hi,b.lo),__fmul_rd(a.hi,b.hi)));
 float hi=fmaxf(fmaxf(__fmul_ru(a.lo,b.lo),__fmul_ru(a.lo,b.hi)),fmaxf(__fmul_ru(a.hi,b.lo),__fmul_ru(a.hi,b.hi)));
 return {lo,hi};
}
__device__ __forceinline__ RFInterval rf_quot(RFInterval a,RFInterval b) {
 if(b.lo<=0.f && b.hi>=0.f)return {-CUDART_INF_F,CUDART_INF_F};
 float lo=fminf(fminf(__fdiv_rd(a.lo,b.lo),__fdiv_rd(a.lo,b.hi)),fminf(__fdiv_rd(a.hi,b.lo),__fdiv_rd(a.hi,b.hi)));
 float hi=fmaxf(fmaxf(__fdiv_ru(a.lo,b.lo),__fdiv_ru(a.lo,b.hi)),fmaxf(__fdiv_ru(a.hi,b.lo),__fdiv_ru(a.hi,b.hi)));
 return {lo,hi};
}
__device__ __forceinline__ float rf_sqmin(RFInterval a) {float t=(a.lo<=0.f&&a.hi>=0.f)?0.f:fminf(fabsf(a.lo),fabsf(a.hi));return __fmul_rd(t,t);}
__device__ __forceinline__ bool rf_pixel(int x,int y,float2 xy,float3 Tu,float3 Tv,float3 Tw,float opacity) {
 float3 k = float(x) * Tw - Tu;
 float3 l = float(y) * Tw - Tv;
 float3 p = cross(k,l);
 if(p.z==0.f)return false;
 float2 s={p.x/p.z,p.y/p.z};
 float rho3d=s.x*s.x+s.y*s.y;
 float2 d={xy.x-float(x),xy.y-float(y)};
 float rho2d=FilterInvSquare*(d.x*d.x+d.y*d.y);
 float rho=min(rho3d,rho2d);
 float depth=(s.x*Tw.x+s.y*Tw.y)+Tw.z;
 if(depth<near_n)return false;
 float power=-.5f*rho;
 if(power>0.f)return false;
 float alpha=min(.99f,opacity*exp(power));
 return !(alpha<1.f/255.f);
}
__device__ __forceinline__ bool rf_possible_interval(int x0,int x1,int y0,int y1,float2 xy,float3 Tu,float3 Tv,float3 Tw,float opacity) {
 if(!isfinite(opacity)||!isfinite(xy.x)||!isfinite(xy.y))return true;
 RFInterval X={float(x0),float(x1)},Y={float(y0),float(y1)};
 RFInterval k[3],l[3];float u[3]={Tu.x,Tu.y,Tu.z},v[3]={Tv.x,Tv.y,Tv.z},w[3]={Tw.x,Tw.y,Tw.z};
 for(int i=0;i<3;i++){if(!isfinite(u[i])||!isfinite(v[i])||!isfinite(w[i]))return true;k[i]=rf_sub(rf_mul(X,rf_const(w[i])),rf_const(u[i]));l[i]=rf_sub(rf_mul(Y,rf_const(w[i])),rf_const(v[i]));}
 RFInterval p[3];p[0]=rf_sub(rf_mul(k[1],l[2]),rf_mul(k[2],l[1]));p[1]=rf_sub(rf_mul(k[2],l[0]),rf_mul(k[0],l[2]));p[2]=rf_sub(rf_mul(k[0],l[1]),rf_mul(k[1],l[0]));
 for(int i=0;i<3;i++)if(!isfinite(p[i].lo)||!isfinite(p[i].hi))return true;
 if(p[2].lo<=0.f&&p[2].hi>=0.f)return true;
 RFInterval a=rf_quot(p[0],p[2]),b=rf_quot(p[1],p[2]);
 if(!isfinite(a.lo)||!isfinite(a.hi)||!isfinite(b.lo)||!isfinite(b.hi))return true;
 RFInterval depth=rf_add(rf_add(rf_mul(a,rf_const(Tw.x)),rf_mul(b,rf_const(Tw.y))),rf_const(Tw.z));
 if(depth.hi<near_n)return false;
 float rho3=__fadd_rd(rf_sqmin(a),rf_sqmin(b));
 float rho2=__fmul_rd(FilterInvSquare,__fadd_rd(rf_sqmin(rf_sub(rf_const(xy.x),X)),rf_sqmin(rf_sub(rf_const(xy.y),Y))));
 float rho=fminf(rho3,rho2);
 // CUDA expf has a documented finite ULP error. Enlarge the upper bound by
 // eight representable steps, then round multiplication upward. Uncertain
 // threshold cases reach the original exact per-pixel predicate below.
 float upper=expf(__fmul_ru(-.5f,rho));
 for(int i=0;i<8;i++)upper=nextafterf(upper,CUDART_INF_F);
 upper=__fmul_ru(opacity,upper);
 return !(upper<1.f/255.f);
}
__device__ __forceinline__ bool rf_tile(int tx,int ty,int W,int H,float2 xy,const float* mat,float opacity) {
 int x0=tx*BLOCK_X,y0=ty*BLOCK_Y,x1=min(x0+BLOCK_X,W)-1,y1=min(y0+BLOCK_Y,H)-1;
 if(x1<x0||y1<y0)return false;
 float3 u={mat[0],mat[1],mat[2]},v={mat[3],mat[4],mat[5]},w={mat[6],mat[7],mat[8]};
 if(!rf_possible_interval(x0,x1,y0,y1,xy,u,v,w,opacity))return false;
 // Most retained tiles are decided by their centre or a corner.
 if(rf_pixel((x0+x1)/2,(y0+y1)/2,xy,u,v,w,opacity))return true;
 for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++)if(rf_pixel(x,y,xy,u,v,w,opacity))return true;
 return false;
}
__global__ void rf_count(int P,int W,int H,const int* radii,const float2* xy,const float* mat,const float4* no,uint32_t* counts,dim3 grid) {
 int idx=blockIdx.x*blockDim.x+threadIdx.x;if(idx>=P)return;
 if(radii[idx]<=0){counts[idx]=0;return;}
 uint2 a,b;getRect(xy[idx],radii[idx],a,b,grid);unsigned count=0;
 for(int y=a.y;y<b.y;y++)for(int x=a.x;x<b.x;x++)count+=rf_tile(x,y,W,H,xy[idx],mat+9*idx,no[idx].w);
 counts[idx]=count;
}
