// PHD-MAIN-MVSFILTER-v1 덧붙임 1: 원통 안 점의 화소 값(A2 의 c·f) 모으기. KD 나무·원통 판정은 JUDGECHECK-v2 inherited/cylinders.cpp 와 같은 줄을 그대로 옮김(Hit 에 점 번호만 더함).
// 원통 = |t| <= H, r <= R (면 찾기 전 원통 안 모든 점 = raw_n 과 같은 점들). 패치마다 H·R 을 줌(JC 와 같은 고르기: 지붕 H 10 · 나머지 5, LoD2 벽 R .125 · 나머지 .075).
// 출력(패치마다 double 4): raw_n, c 중앙값, c >= 5 비율, f/(c+f) 평균.
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
#include <sstream>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
using V=std::array<double,3>;
double dot(const V&a,const V&b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
V cross(const V&a,const V&b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
struct Node {uint32_t lo,hi;int left=-1,right=-1;V lower,upper;};
struct Hit {double t,r2;uint32_t p;};
struct Tree {
 const void *xyz;bool f64;double radius;std::vector<uint32_t> idx;std::vector<Node> nodes;
 double value(size_t i)const{return f64?static_cast<const double*>(xyz)[i]:static_cast<const float*>(xyz)[i];}
 Tree(const void*x,size_t N,bool dp,double rad):xyz(x),f64(dp),radius(rad),idx(N){
  if(N>UINT32_MAX)throw std::runtime_error("too many points");
  std::iota(idx.begin(),idx.end(),0);V a={1e100,1e100,1e100},b={-1e100,-1e100,-1e100};
  for(size_t i=0;i<N;i++)for(int k=0;k<3;k++){
   if(!std::isfinite(value(3*i+k)))throw std::runtime_error("nonfinite input point");
   a[k]=std::min(a[k],value(3*i+k));b[k]=std::max(b[k],value(3*i+k));}
  nodes.reserve(N/16+1);if(N)build(0,N,a,b);
 }
 int build(uint32_t lo,uint32_t hi,V a,V b){
  int id=nodes.size();nodes.push_back({lo,hi,-1,-1,a,b});if(hi-lo<=48)return id;
  int axis=0;for(int k=1;k<3;k++)if(b[k]-a[k]>b[axis]-a[axis])axis=k;
  uint32_t mid=lo+(hi-lo)/2;
  std::nth_element(idx.begin()+lo,idx.begin()+mid,idx.begin()+hi,[&](uint32_t i,uint32_t j){
   double x=value(3ull*i+axis),y=value(3ull*j+axis);return x<y||(x==y&&i<j);});
  double split=value(3ull*idx[mid]+axis);V al=a,bl=b;bl[axis]=split;al[axis]=split;
  int l=build(lo,mid,a,bl),r=build(mid,hi,al,b);nodes[id].left=l;nodes[id].right=r;return id;
 }
 void query(int id,const V&c,const V&n,const V&u,const V&v,std::vector<Hit>&out){
  const Node&q=nodes[id];V mid,h;for(int k=0;k<3;k++){mid[k]=(q.lower[k]+q.upper[k])*.5-c[k];h[k]=(q.upper[k]-q.lower[k])*.5;}
  const V axes[3]={n,u,v};const double lim[3]={10.,radius,radius};
  for(int j=0;j<3;j++){double span=0;for(int k=0;k<3;k++)span+=std::abs(axes[j][k])*h[k];
   if(std::abs(dot(mid,axes[j]))>lim[j]+span+1e-8)return;}
  if(q.left>=0){query(q.left,c,n,u,v,out);query(q.right,c,n,u,v,out);return;}
  for(uint32_t j=q.lo;j<q.hi;j++){uint32_t p=idx[j];V d;for(int k=0;k<3;k++)d[k]=value(3ull*p+k)-c[k];
   double t=dot(d,n);if(std::abs(t)>10.)continue;double r2=0;for(int k=0;k<3;k++){double v=d[k]-t*n[k];r2+=v*v;}
   if(r2<=radius*radius)out.push_back({t,r2,p});}
 }
};
int main(int argc,char**argv){try{
 if(argc!=7){std::cerr<<"points.npy offset count attr_cf.u16 cores.bin(cx cy cz nx ny nz H R) result.bin\n";return 2;}
 std::string path=argv[1];size_t off=std::stoull(argv[2]),N=std::stoull(argv[3]);
 int fd=open(path.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 if(off+N*3*sizeof(float)>size_t(st.st_size))throw std::runtime_error("point size");
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 const void*xyz=static_cast<const char*>(map)+off;
 std::vector<uint16_t> cf(2*N);{std::ifstream a(argv[4],std::ios::binary);a.read(reinterpret_cast<char*>(cf.data()),cf.size()*2);if(!a)throw std::runtime_error("attr");}
 Tree tree(xyz,N,false,.125);std::cerr<<"KD_TREE "<<N<<" points\n";
 std::ifstream cores(argv[5],std::ios::binary);std::ofstream out(argv[6],std::ios::binary);if(!cores||!out)throw std::runtime_error("io");
 std::vector<Hit> hits;double res[4];std::vector<int> cs;size_t i=0;double rec[8];
 while(cores.read(reinterpret_cast<char*>(rec),64)){
  V c={rec[0],rec[1],rec[2]},n={rec[3],rec[4],rec[5]};double Hh=rec[6],R=rec[7];hits.clear();double norm=std::sqrt(dot(n,n));
  res[0]=-1;res[1]=res[2]=res[3]=NAN;
  if(std::isfinite(norm)&&std::abs(norm-1.)<1e-6){
   V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};V u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;V v=cross(n,u);
   if(N)tree.query(0,c,n,u,v,hits);
   cs.clear();double sr=0;long k5=0;for(auto&h:hits){if(std::abs(h.t)<=Hh&&h.r2<=R*R){int cc=cf[2*h.p],ff=cf[2*h.p+1];cs.push_back(cc);k5+=cc>=5;sr+=double(ff)/(cc+ff);}}
   res[0]=cs.size();if(!cs.empty()){std::nth_element(cs.begin(),cs.begin()+cs.size()/2,cs.end());double md=cs[cs.size()/2];
    if(cs.size()%2==0){int lo=*std::max_element(cs.begin(),cs.begin()+cs.size()/2);md=(md+lo)*.5;}res[1]=md;res[2]=double(k5)/cs.size();res[3]=sr/cs.size();}
  }
  out.write(reinterpret_cast<char*>(res),32);if(++i%20000==0)std::cerr<<"CORE "<<i<<"\n";
 }
 out.close();if(!out)throw std::runtime_error("write failed");munmap(map,st.st_size);close(fd);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
