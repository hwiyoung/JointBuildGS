// Exact nearest camera-Z per integer pixel; no dilation or interpolation.
#include <cmath>
#include <cstdint>
extern "C" void zbuffer(const double* x, int64_t count, const double* r,
                         const double* t, const double* k, double* buf) {
  for (int64_t i=0;i<count;++i) {
    const double a=x[3*i], b=x[3*i+1], c=x[3*i+2];
    const double z=((a*r[6]+b*r[7])+c*r[8])+t[2];
    if (!(z>0)) continue;
    const double u=k[0]*(((a*r[0]+b*r[1])+c*r[2])+t[0])/z+k[2];
    const double v=k[1]*(((a*r[3]+b*r[4])+c*r[5])+t[1])/z+k[3];
    if (!(u>=0 && u<1024 && v>=0 && v<741)) continue;
    const int64_t j=static_cast<int64_t>(v)*1024+static_cast<int64_t>(u);
    if (z<buf[j]) buf[j]=z;
  }
}
