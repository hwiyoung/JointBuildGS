// PHD-MAIN-MVSFILTER-v1 회신 1: 원통 안 점의 부호(u16) 막대그림을 패치 무리마다 더함(1절 c = 1 나눔, 4절 깊이 분포). cyl_attr.cpp 와 같은 KD 나무·원통. KD 나무·원통 판정은 JUDGECHECK-v2 inherited/cylinders.cpp 와 같은 줄을 그대로 옮김(Hit 에 점 번호만 더함).
// 원통 = |t| <= H, r <= R (면 찾기 전 원통 안 모든 점 = raw_n 과 같은 점들). 패치마다 H·R 을 줌(JC 와 같은 고르기: 지붕 H 10 · 나머지 5, LoD2 벽 R .125 · 나머지 .075).
// 입력 패치마다 (cx cy cz nx ny nz H R group), group < 0 이면 건너뜀. 출력 = G x K double (무리 g 의 원통들 안 점 가운데 부호 k 인 점 수, 겹치면 패치마다 셈).
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
 if(argc!=9){std::cerr<<"points.npy offset count code.u16 K cores.bin(9 doubles) G result.bin\n";return 2;}
 std::string path=argv[1];size_t off=std::stoull(argv[2]),N=std::stoull(argv[3]);int K=std::stoi(argv[5]),G=std::stoi(argv[7]);
 int fd=open(path.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 const void*xyz=static_cast<const char*>(map)+off;
 std::vector<uint16_t> code(N);{std::ifstream a(argv[4],std::ios::binary);a.read(reinterpret_cast<char*>(code.data()),N*2);if(!a)throw std::runtime_error("code");}
 Tree tree(xyz,N,false,.125);std::ifstream cores(argv[6],std::ios::binary);if(!cores)throw std::runtime_error("cores");
 std::vector<double> hist((size_t)G*K,0.);std::vector<Hit> hits;double rec[9];
 while(cores.read(reinterpret_cast<char*>(rec),72)){
  int g=(int)rec[8];if(g<0)continue;V c={rec[0],rec[1],rec[2]},n={rec[3],rec[4],rec[5]};double Hh=rec[6],R=rec[7];double norm=std::sqrt(dot(n,n));
  if(!(std::isfinite(norm)&&std::abs(norm-1.)<1e-6))continue;
  V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};V u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;V v=cross(n,u);
  hits.clear();if(N)tree.query(0,c,n,u,v,hits);
  for(auto&h:hits)if(std::abs(h.t)<=Hh&&h.r2<=R*R){int k=code[h.p];if(k>=K)k=K-1;hist[(size_t)g*K+k]+=1;}
 }
 std::ofstream out(argv[8],std::ios::binary);out.write(reinterpret_cast<char*>(hist.data()),hist.size()*8);out.close();munmap(map,st.st_size);close(fd);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
