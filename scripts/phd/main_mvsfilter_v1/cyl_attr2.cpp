// PHD-MAIN-MVSFILTER-v1 덧붙임 2: 원통 안 점의 A2 본 판(1 %) 화소 값 c·f·o·m 모으기. cyl_attr.cpp(덧붙임 1)와 같은 KD 나무·원통(같은 점) — 값만 더 냄. 새 화소 셈 없음.
// 출력(패치마다 double 11): raw_n, c 중앙값, c>=5 비율, f/(c+f) 평균 (앞 셋+1 = cyl_attr 와 같아야 함 — 검산),
//   m 중앙값, c/m 중앙값, o/m 평균, c 10 % 값, c 90 % 값(선형 보간, numpy 기본과 같음), '2c >= m 또는 c >= 5' 인 점의 비율, 점 수 확인용 m 합.
// c·m 은 자기 포함(a2_count.cpp). 중앙값은 짝수 개일 때 가운데 둘의 평균(cyl_attr 와 같음).
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
static double pct(std::vector<double>&x,double q){std::sort(x.begin(),x.end());double p=q*(x.size()-1);size_t a=size_t(std::floor(p));size_t b=std::min(a+1,x.size()-1);return x[a]+(p-a)*(x[b]-x[a]);}
static double med(std::vector<double> x){return pct(x,.5);}
int main(int argc,char**argv){try{
 if(argc!=7){std::cerr<<"points.npy offset count attr_cfom.u16 cores.bin(cx cy cz nx ny nz H R) result.bin\n";return 2;}
 std::string path=argv[1];size_t off=std::stoull(argv[2]),N=std::stoull(argv[3]);
 int fd=open(path.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 if(off+N*3*sizeof(float)>size_t(st.st_size))throw std::runtime_error("point size");
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 const void*xyz=static_cast<const char*>(map)+off;
 std::vector<uint16_t> cf(4*N);{std::ifstream a(argv[4],std::ios::binary);a.read(reinterpret_cast<char*>(cf.data()),cf.size()*2);if(!a)throw std::runtime_error("attr");}
 Tree tree(xyz,N,false,.125);std::cerr<<"KD_TREE "<<N<<" points\n";
 std::ifstream cores(argv[5],std::ios::binary);std::ofstream out(argv[6],std::ios::binary);if(!cores||!out)throw std::runtime_error("io");
 std::vector<Hit> hits;const int K=11;double res[K];std::vector<double> cs,ms,cm;size_t i=0;double rec[8];
 while(cores.read(reinterpret_cast<char*>(rec),64)){
  V c={rec[0],rec[1],rec[2]},n={rec[3],rec[4],rec[5]};double Hh=rec[6],R=rec[7];hits.clear();double norm=std::sqrt(dot(n,n));
  res[0]=-1;for(int k=1;k<K;k++)res[k]=NAN;
  if(std::isfinite(norm)&&std::abs(norm-1.)<1e-6){
   V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};V u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;V v=cross(n,u);
   if(N)tree.query(0,c,n,u,v,hits);
   cs.clear();ms.clear();cm.clear();double sr=0,so=0,msum=0;long k5=0,kh=0;
   for(auto&h:hits){if(std::abs(h.t)<=Hh&&h.r2<=R*R){int cc=cf[4*h.p],ff=cf[4*h.p+1],oo=cf[4*h.p+2],mm=cf[4*h.p+3];
     cs.push_back(cc);ms.push_back(mm);cm.push_back(double(cc)/mm);k5+=cc>=5;kh+=(2*cc>=mm)||(cc>=5);sr+=double(ff)/(cc+ff);so+=double(oo)/mm;msum+=mm;}}
   res[0]=cs.size();
   if(!cs.empty()){double s=cs.size();res[1]=med(cs);res[2]=k5/s;res[3]=sr/s;res[4]=med(ms);res[5]=med(cm);res[6]=so/s;res[7]=pct(cs,.1);res[8]=pct(cs,.9);res[9]=kh/s;res[10]=msum;}
  }
  out.write(reinterpret_cast<char*>(res),8*K);if(++i%20000==0)std::cerr<<"CORE "<<i<<"\n";
 }
 out.close();if(!out)throw std::runtime_error("write failed");munmap(map,st.st_size);close(fd);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
