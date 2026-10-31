#include <cmath>
#include <algorithm>
#include <limits>
extern "C" void target_discs(int n, const double* p, const double* R, const double* t,
                            const double* K, int H, int W, float* depth, int* owner) {
    for (int j=0;j<H*W;j++){depth[j]=std::numeric_limits<float>::infinity();owner[j]=-1;}
    for (int i=0;i<n;i++) {
        const double* q=p+8*i; const double radius=q[6];
        if(!std::isfinite(q[0]) || !(radius>0))continue;
        double c[3]={t[0],t[1],t[2]},normal[3]={0,0,0};
        for(int a=0;a<3;a++)for(int b=0;b<3;b++){c[a]+=R[3*a+b]*q[b];normal[a]+=R[3*a+b]*q[3+b];}
        if(c[2]<=radius)continue;
        const double u=K[0]*c[0]/c[2]+K[2],v=K[4]*c[1]/c[2]+K[5];
        const double du=K[0]*radius*(1+std::abs(c[0])/c[2])/(c[2]-radius)+1;
        const double dv=K[4]*radius*(1+std::abs(c[1])/c[2])/(c[2]-radius)+1;
        int x0=std::max(0,int(std::floor(u-du))),x1=std::min(W-1,int(std::ceil(u+du)));
        int y0=std::max(0,int(std::floor(v-dv))),y1=std::min(H-1,int(std::ceil(v+dv)));
        const double offset=normal[0]*c[0]+normal[1]*c[1]+normal[2]*c[2];
        for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
            const double rx=(x-K[2])/K[0],ry=(y-K[5])/K[4];
            const double denom=normal[0]*rx+normal[1]*ry+normal[2];
            if(std::abs(denom)<1e-12)continue;
            const double z=offset/denom;const int j=y*W+x;
            if(z<=0 || z>=depth[j])continue;
            const double dx=z*rx-c[0],dy=z*ry-c[1],dz=z-c[2];
            if(dx*dx+dy*dy+dz*dz<=radius*radius+1e-12){depth[j]=float(z);owner[j]=int(q[7]);}
        }
    }
}
