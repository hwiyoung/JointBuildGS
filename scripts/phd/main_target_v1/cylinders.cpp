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
struct Hit {double t,r2;};
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
   if(r2<=.25)out.push_back({t,r2});}
 }
};
double median_sorted(const std::vector<double>&a){size_t m=a.size()/2;return a.size()%2?a[m]:(a[m-1]+a[m])*.5;}
void measure(const std::vector<Hit>&hits,double H,double r,double*out){
 std::vector<double> t;t.reserve(hits.size());for(auto&p:hits)if(std::abs(p.t)<=H&&p.r2<=r*r)t.push_back(p.t);
 out[0]=0;for(int k=1;k<6;k++)out[k]=NAN;out[6]=t.size();if(t.empty())return;
 // Hits are sorted once; every radius/length subset stays sorted.
 int last=std::lround((2*H-.3)/.05);int start=std::max(0,int(std::ceil((H-.3-t.back()-1e-9)/.05)));
 double o=NAN;
 for(int k=start;k<=last;k++){
  double top=H-.05*k,bottom=top-.3;
  auto a=std::lower_bound(t.begin(),t.end(),bottom-1e-9),b=std::upper_bound(t.begin(),t.end(),top+1e-9);
  if(double(b-a)>=.2*t.size()){o=top-.15;break;}
 }
 if(!std::isfinite(o))return;
 auto a=std::lower_bound(t.begin(),t.end(),o-1.),b=std::upper_bound(t.begin(),t.end(),o+1.);
 std::vector<double>s(a,b);if(s.empty())return;double mean=std::accumulate(s.begin(),s.end(),0.)/s.size();
 double variance=0;for(double x:s)variance+=(x-mean)*(x-mean);
 double med=median_sorted(s);std::vector<double>ad;ad.reserve(s.size());for(double x:s)ad.push_back(std::abs(x-med));
 std::sort(ad.begin(),ad.end());out[0]=s.size();out[1]=mean;out[2]=med;
 out[3]=s.size()>1?std::sqrt(variance/(s.size()-1)):NAN;out[4]=1.4826*median_sorted(ad);out[5]=o;
}
int main(int argc,char**argv){try{
 if(argc!=7){std::cerr<<"points.npy offset count cores.bin core_count result.bin\n";return 2;}
 std::string path=argv[1];size_t off=std::stoull(argv[2]),N=std::stoull(argv[3]),nc=std::stoull(argv[5]);
 int fd=open(path.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 if(off+N*3*sizeof(float)>size_t(st.st_size))throw std::runtime_error("point size");
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 const float*xyz=reinterpret_cast<const float*>(static_cast<const char*>(map)+off);
 Tree tree(xyz,N);std::cerr<<"KD_TREE "<<N<<" points "<<tree.nodes.size()<<" nodes\n";
 std::ifstream cores(argv[4],std::ios::binary);std::ofstream out(argv[6],std::ios::binary);
 if(!cores||!out)throw std::runtime_error("input/output open");
 const double Hs[]={5.,3.,10.},rs[]={.05,.075,.10,.125,.15,.20,.25,.30,.40,.50};
 std::vector<Hit> hits;double result[3][10][7];
 for(size_t i=0;i<nc;i++){
  V c,n;cores.read(reinterpret_cast<char*>(c.data()),24);cores.read(reinterpret_cast<char*>(n.data()),24);
  if(!cores)throw std::runtime_error("short cores input");
  hits.clear();double norm=std::sqrt(dot(n,n));
  if(std::isfinite(norm)&&std::abs(norm-1.)<1e-6){
   V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};V u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;V v=cross(n,u);
   if(N)tree.query(0,c,n,u,v,hits);
   std::sort(hits.begin(),hits.end(),[](const Hit&a,const Hit&b){return a.t<b.t;});
   for(int h=0;h<3;h++)for(int r=0;r<10;r++)measure(hits,Hs[h],rs[r],result[h][r]);
  }else{for(auto&h:result)for(auto&r:h){for(double&x:r)x=NAN;r[0]=-1;r[6]=-1;}}
  out.write(reinterpret_cast<char*>(result),sizeof(result));
  if(i%10000==0)std::cerr<<"CORE "<<i<<"/"<<nc<<"\n";
 }
 out.close();if(!out)throw std::runtime_error("write failed");munmap(map,st.st_size);close(fd);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
