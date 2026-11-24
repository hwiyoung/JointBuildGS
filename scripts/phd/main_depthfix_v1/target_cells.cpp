// PHD-MAIN-DEPTHFIX-v1 (request 2): z-buffer of patch CELLS (parallelograms c + a*T1 + b*T2, |a|,|b| <= 1/2, T = sp*t) instead of discs.
// Same camera convention, pixel rule (rx = (x - cx)/fx) and nearest-wins as target_discs.cpp. Per item q[13]: c(3), n(3), T1(3), T2(3), id.
#include <cmath>
#include <algorithm>
#include <limits>
extern "C" void target_cells(int n, const double* p, const double* R, const double* t,
                             const double* K, int H, int W, float* depth, int* owner) {
    for (int j=0;j<H*W;j++){depth[j]=std::numeric_limits<float>::infinity();owner[j]=-1;}
    for (int i=0;i<n;i++) {
        const double* q=p+13*i;
        if(!std::isfinite(q[0]))continue;
        double c[3]={t[0],t[1],t[2]},nn[3]={0,0,0},a1[3]={0,0,0},a2[3]={0,0,0};
        for(int a=0;a<3;a++)for(int b=0;b<3;b++){c[a]+=R[3*a+b]*q[b];nn[a]+=R[3*a+b]*q[3+b];a1[a]+=R[3*a+b]*q[6+b];a2[a]+=R[3*a+b]*q[9+b];}
        const double radius=0.5*(std::sqrt(a1[0]*a1[0]+a1[1]*a1[1]+a1[2]*a1[2])+std::sqrt(a2[0]*a2[0]+a2[1]*a2[1]+a2[2]*a2[2]));
        if(c[2]<=radius)continue;
        const double g11=a1[0]*a1[0]+a1[1]*a1[1]+a1[2]*a1[2],g22=a2[0]*a2[0]+a2[1]*a2[1]+a2[2]*a2[2],g12=a1[0]*a2[0]+a1[1]*a2[1]+a1[2]*a2[2];
        const double det=g11*g22-g12*g12; if(!(det>0))continue;
        const double u=K[0]*c[0]/c[2]+K[2],v=K[4]*c[1]/c[2]+K[5];
        const double du=K[0]*radius*(1+std::abs(c[0])/c[2])/(c[2]-radius)+1;
        const double dv=K[4]*radius*(1+std::abs(c[1])/c[2])/(c[2]-radius)+1;
        int x0=std::max(0,int(std::floor(u-du))),x1=std::min(W-1,int(std::ceil(u+du)));
        int y0=std::max(0,int(std::floor(v-dv))),y1=std::min(H-1,int(std::ceil(v+dv)));
        const double offset=nn[0]*c[0]+nn[1]*c[1]+nn[2]*c[2];
        for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
            const double rx=(x-K[2])/K[0],ry=(y-K[5])/K[4];
            const double denom=nn[0]*rx+nn[1]*ry+nn[2];
            if(std::abs(denom)<1e-12)continue;
            const double z=offset/denom;const int j=y*W+x;
            if(z<=0 || z>=depth[j])continue;
            const double d0=z*rx-c[0],d1=z*ry-c[1],d2=z-c[2];
            const double p1=d0*a1[0]+d1*a1[1]+d2*a1[2],p2=d0*a2[0]+d1*a2[1]+d2*a2[2];
            const double aa=( g22*p1-g12*p2)/det, bb=(-g12*p1+g11*p2)/det;
            if(std::abs(aa)<=0.5+1e-9 && std::abs(bb)<=0.5+1e-9){depth[j]=float(z);owner[j]=int(q[12]);}
        }
    }
}
