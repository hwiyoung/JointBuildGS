// Exact CPU cylinder queries, conservative KD-tree bounds; no GPU dependencies.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
using V=std::array<double,3>;
double dot(const V&a,const V&b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
V cross(const V&a,const V&b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
struct Node {uint32_t lo,hi;int left=-1,right=-1;V lower,upper;};
struct Hit {double t,r2;uint32_t id;};
struct Tree {
 const float *xyz;std::vector<uint32_t> idx;std::vector<Node> nodes;
 Tree(const float*x,size_t N):xyz(x),idx(N){
  if(N>UINT32_MAX)throw std::runtime_error("too many points");
  std::iota(idx.begin(),idx.end(),0);V a={1e100,1e100,1e100},b={-1e100,-1e100,-1e100};
  for(size_t i=0;i<N;i++)for(int k=0;k<3;k++){
   if(!std::isfinite(x[3*i+k]))throw std::runtime_error("nonfinite input point");
   a[k]=std::min(a[k],double(x[3*i+k]));b[k]=std::max(b[k],double(x[3*i+k]));}
  nodes.reserve(N/16+1);if(N)build(0,N,a,b);
 }
 int build(uint32_t lo,uint32_t hi,V a,V b){
  int id=nodes.size();nodes.push_back({lo,hi,-1,-1,a,b});if(hi-lo<=48)return id;
  int axis=0;for(int k=1;k<3;k++)if(b[k]-a[k]>b[axis]-a[axis])axis=k;
  uint32_t mid=lo+(hi-lo)/2;
  std::nth_element(idx.begin()+lo,idx.begin()+mid,idx.begin()+hi,[&](uint32_t i,uint32_t j){
   float x=xyz[3ull*i+axis],y=xyz[3ull*j+axis];return x<y||(x==y&&i<j);});
  double split=xyz[3ull*idx[mid]+axis];V al=a,bl=b;bl[axis]=split;al[axis]=split;
  int l=build(lo,mid,a,bl),r=build(mid,hi,al,b);nodes[id].left=l;nodes[id].right=r;return id;
 }
 void query(int id,const V&c,const V&n,const V&u,const V&v,std::vector<Hit>&out){
  const Node&q=nodes[id];V mid,h;for(int k=0;k<3;k++){mid[k]=(q.lower[k]+q.upper[k])*.5-c[k];h[k]=(q.upper[k]-q.lower[k])*.5;}
  const V axes[3]={n,u,v};const double lim[3]={10.,.5,.5};
  for(int j=0;j<3;j++){double span=0;for(int k=0;k<3;k++)span+=std::abs(axes[j][k])*h[k];
   if(std::abs(dot(mid,axes[j]))>lim[j]+span+1e-8)return;}
  if(q.left>=0){query(q.left,c,n,u,v,out);query(q.right,c,n,u,v,out);return;}
  for(uint32_t j=q.lo;j<q.hi;j++){uint32_t p=idx[j];V d;for(int k=0;k<3;k++)d[k]=double(xyz[3ull*p+k])-c[k];
   double t=dot(d,n);if(std::abs(t)>10.)continue;double r2=0;for(int k=0;k<3;k++){double v=d[k]-t*n[k];r2+=v*v;}
   if(r2<=.25)out.push_back({t,r2,p});}
 }
};
int main(int argc,char**argv){try{
 if(argc!=7)throw std::runtime_error("points.npy offset count cores.bin core_count mask.bin");
 size_t off=std::stoull(argv[2]),N=std::stoull(argv[3]),nc=std::stoull(argv[5]);
 int fd=open(argv[1],O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 const float*xyz=reinterpret_cast<const float*>(static_cast<const char*>(map)+off);Tree tree(xyz,N);
 std::vector<uint8_t> mask(N,0);std::vector<Hit>hits;std::ifstream cores(argv[4],std::ios::binary);
 for(size_t i=0;i<nc;i++){
  V c,n;double H,r;cores.read(reinterpret_cast<char*>(c.data()),24);cores.read(reinterpret_cast<char*>(n.data()),24);
  cores.read(reinterpret_cast<char*>(&H),8);cores.read(reinterpret_cast<char*>(&r),8);if(!cores)throw std::runtime_error("short core");
  if(!std::isfinite(dot(n,n))||std::abs(dot(n,n)-1)>1e-6||!std::isfinite(r))continue;
  V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};V u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;V v=cross(n,u);
  hits.clear();if(N)tree.query(0,c,n,u,v,hits);
  for(auto&p:hits)if(std::abs(p.t)<=H && p.r2<=r*r)mask[p.id]=1;
 }
 std::ofstream out(argv[6],std::ios::binary);out.write(reinterpret_cast<char*>(mask.data()),N);out.close();if(!out)throw std::runtime_error("write");
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
