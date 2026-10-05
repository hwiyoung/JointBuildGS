// SRDM 2018 Eq.11,13-17. This is a paper reimplementation, not author code.
// Compile in Docker runtime scratch; no training libraries or reference data.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <utility>
#include <vector>
#include <omp.h>

namespace {
inline float weight(float a, float b, float sigma) {
    if (!std::isfinite(a) || !std::isfinite(b)) return 0.0f;
    const float delta = std::abs(a-b);
    if (delta <= 2*sigma) {
        const float q = (std::exp(-2.0f)-1)/(4*sigma*sigma);
        return 1+q*delta*delta;
    }
    return std::exp(-delta/sigma);
}

// Eq.14: forward + reverse - unary. Per-path scratch is only 2*D floats.
// Optional label-independent normalization is algebraically argmin preserving:
// every removed path constant is identical for all disparity hypotheses.
void axis_pair(const float* input, const float* gray, int h, int w, int d,
               int dx, int dy, float penalty, float sigma, bool normalize,
               float* output) {
    std::vector<std::pair<int,int>> starts;
    for (int y=0; y<h; ++y) for (int x=0; x<w; ++x) {
        int px=x-dx, py=y-dy;
        if (px<0 || px>=w || py<0 || py>=h) starts.emplace_back(x,y);
    }
    #pragma omp parallel for schedule(static)
    for (std::size_t line=0; line<starts.size(); ++line) {
        std::vector<float> prev(d), cur(d);
        const int sx=starts[line].first, sy=starts[line].second;
        int endx=sx, endy=sy;
        while (endx+dx>=0 && endx+dx<w && endy+dy>=0 && endy+dy<h) {
            endx+=dx; endy+=dy;
        }
        for (int reverse=0; reverse<2; ++reverse) {
            int x=reverse ? endx:sx, y=reverse ? endy:sy;
            const int vx=reverse ? -dx:dx, vy=reverse ? -dy:dy;
            bool first=true;
            while (x>=0 && x<w && y>=0 && y<h) {
                const std::size_t pixel=std::size_t(y)*w+x;
                const std::size_t off=pixel*d;
                float minimum=std::numeric_limits<float>::infinity();
                const float wt=first ? 0.0f:weight(gray[pixel],gray[std::size_t(y-vy)*w+x-vx],sigma);
                for (int k=0;k<d;++k) {
                    float m=first ? 0.0f:prev[k];
                    if (!first && k>0) m=std::min(m,prev[k-1]+penalty);
                    if (!first && k+1<d) m=std::min(m,prev[k+1]+penalty);
                    cur[k]=input[off+k]+wt*m;
                    minimum=std::min(minimum,cur[k]);
                }
                if (normalize) for(int k=0;k<d;++k) cur[k]-=minimum;
                if (!reverse) {
                    std::memcpy(output+off,cur.data(),std::size_t(d)*sizeof(float));
                } else {
                    for (int k=0;k<d;++k) output[off+k]+=cur[k]-input[off+k];
                    if (normalize) {
                        float m=*std::min_element(output+off,output+off+d);
                        for (int k=0;k<d;++k) output[off+k]-=m;
                    }
                }
                prev.swap(cur); first=false; x+=vx; y+=vy;
            }
        }
    }
}
}

extern "C" int srdm_aggregate(const float* unary,const float* gray,
    int h,int w,int d,float penalty,float sigma,int orientations,int normalize,
    int threads,float* sum,float* first,float* second) {
    if(h<=0 || w<=0 || d<=0 || sigma<=0 || threads<=0) return 1;
    omp_set_num_threads(threads);
    const std::size_t n=std::size_t(h)*w*d;
    std::fill(sum,sum+n,0.0f);
    const int dx[4]={1,1,0,-1};
    const int dy[4]={0,1,1,1};
    for(int r=0;r<4;++r) if(orientations & (1<<r)) {
        axis_pair(unary,gray,h,w,d,dx[r],dy[r],penalty,sigma,normalize,first);
        // Eq.15 explicitly doubles P for the orthogonal second aggregation.
        axis_pair(first,gray,h,w,d,-dy[r],dx[r],2*penalty,sigma,normalize,second);
        #pragma omp parallel for schedule(static)
        for(std::size_t i=0;i<n;++i) sum[i]+=second[i];
    }
    return 0;
}

extern "C" int srdm_photo(const std::uint32_t* cl,const std::uint32_t* cr,
    const float* hl,const float* hr,const std::uint8_t* vl,const std::uint8_t* vr,
    int h,int w,int lo,int hi,float alpha,float tc,float th,int threads,float* out) {
    if(h<=0 || w<=0 || lo>hi || tc<=0 || th<=0) return 1;
    omp_set_num_threads(threads);
    const int nd=hi-lo+1;
    #pragma omp parallel for schedule(static)
    for(int y=0;y<h;++y) for(int x=0;x<w;++x) {
        const std::size_t p=std::size_t(y)*w+x;
        for(int k=0;k<nd;++k) {
            int xr=x-(lo+k);
            const std::size_t off=p*nd+k;
            if(!vl[p] || xr<0 || xr>=w || !vr[std::size_t(y)*w+xr]) {
                out[off]=-1.0f; continue;
            }
            const std::size_t q=std::size_t(y)*w+xr;
            float census=static_cast<float>(__builtin_popcount(cl[p]^cr[q]));
            float hog=0;
            for(int b=0;b<12;++b) hog+=std::abs(hl[p*12+b]-hr[q*12+b]);
            out[off]=alpha*std::min(census,tc)/tc+(1-alpha)*std::min(hog,th)/th;
        }
    }
    return 0;
}

extern "C" int srdm_ranges(const float* gray,const float* sparse,const std::uint8_t* valid,
    int h,int w,int radius,float tolerance,float gamma,int lo,int hi,int threads,
    std::int32_t* outlo,std::int32_t* outhi) {
    if(h<=0 || w<=0 || radius<0 || gamma<0 || lo>hi) return 1;
    omp_set_num_threads(threads);
    // Row lists avoid scanning absent ALS points in each local window.
    std::vector<std::vector<int>> rows(h);
    for(int y=0;y<h;++y) for(int x=0;x<w;++x)
        if(valid[std::size_t(y)*w+x]) rows[y].push_back(x);
    #pragma omp parallel for schedule(static)
    for(int y=0;y<h;++y) for(int x=0;x<w;++x) {
        const std::size_t p=std::size_t(y)*w+x;
        float minimum=std::numeric_limits<float>::infinity();
        float maximum=-minimum;
        for(int yy=std::max(0,y-radius);yy<=std::min(h-1,y+radius);++yy) {
            const auto& row=rows[yy];
            auto begin=std::lower_bound(row.begin(),row.end(),x-radius);
            auto end=std::upper_bound(begin,row.end(),x+radius);
            for(auto it=begin;it!=end;++it) {
                const std::size_t q=std::size_t(yy)*w+*it;
                if(std::abs(gray[p]-gray[q])<tolerance) {
                    minimum=std::min(minimum,sparse[q]);
                    maximum=std::max(maximum,sparse[q]);
                }
            }
        }
        if(std::isfinite(minimum)) {
            outlo[p]=std::max(lo,static_cast<int>(std::ceil(minimum-gamma)));
            outhi[p]=std::min(hi,static_cast<int>(std::floor(maximum+gamma)));
        } else {outlo[p]=lo; outhi[p]=hi;}
    }
    return 0;
}
