#include <algorithm>
#include <cmath>
#include <cstdint>
// Exact orthographic triangle rasterization at pixel centers. No hole filling.
extern "C" void raster(const double* q, const float* color, int64_t count,
                        int width, int height, double* depth, float* rgb,
                        int64_t* owner, int64_t offset) {
  for (int64_t i=0;i<count;++i) {
    const double* a=q+9*i; const double* b=a+3; const double* c=a+6;
    int x0=std::max(0,(int)std::floor(std::min({a[0],b[0],c[0]})));
    int x1=std::min(width-1,(int)std::ceil(std::max({a[0],b[0],c[0]})));
    int y0=std::max(0,(int)std::floor(std::min({a[1],b[1],c[1]})));
    int y1=std::min(height-1,(int)std::ceil(std::max({a[1],b[1],c[1]})));
    double den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
    if(std::abs(den)<1e-14) continue;
    for(int y=y0;y<=y1;++y) for(int x=x0;x<=x1;++x) {
      double wa=((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den;
      double wb=((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den;
      double wc=1-wa-wb;
      if(wa < -1e-10 || wb < -1e-10 || wc < -1e-10) continue;
      int64_t p=(int64_t)y*width+x; double z=wa*a[2]+wb*b[2]+wc*c[2];
      if(z>depth[p]) {
        depth[p]=z; owner[p]=offset+i;
        for(int k=0;k<3;++k) rgb[3*p+k]=color[3*i+k];
      }
    }
  }
}
