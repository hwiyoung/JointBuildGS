// PHD-MAIN-JUDGEGT-v1: exact CPU column/cylinder/sphere queries on a KD tree (pruning as in JUDGECHECK-v2 cylinders.cpp). No GPU.
// usage: gtcols <mode> points.npy offset count cores.bin core_count out.bin f4|f8
//  mode cyl : core = c(3) n(3) radius H            -> out per core: raw_n (|t|<=H, r<=radius), median t       (2 doubles)
//  mode col : core = c(3) n(3) t1(3) half H tau hM
//             square column: |t|<=H, |u|<=half, |v|<=half with u = t1 axis, v = n x t1 (t measured from c)
//             -> out: n_total, n_band0 (|t|<=tau), n_bandM (|t-hM|<=tau; -1 if hM NaN), n_dens (|t|<=1), n_clusters,
//                     then clusters 1..6 (count, median) in ascending t, clusters split where neighbour gap > gap   (5+12 = 17 doubles)
//  mode img : core = c(3) n(3) t1(3) half H tau  -> out: n_col, best_n, h_I (median of the densest 2tau window, tie -> |median| smallest), tie flag
//             (another max window with median > tau away), second_n, second_median (densest window wholly outside the best), best_lo, best_hi  (8 doubles)
//  mode pca : core = c(3)                          -> out: n05, normal05(3), n10, normal10(3)   (points within 0.5 / 1.0 m)   (8 doubles)
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>
#include <stdexcept>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <omp.h>
using V = std::array<double,3>;
static double dot(const V&a,const V&b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static V cross(const V&a,const V&b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
struct Node{uint32_t lo,hi;int left=-1,right=-1;V lower,upper;};
struct Tree{
 const void*xyz;bool f64;std::vector<uint32_t> idx;std::vector<Node> nodes;
 double val(size_t i)const{return f64?static_cast<const double*>(xyz)[i]:static_cast<const float*>(xyz)[i];}
 V pt(uint32_t p)const{return {val(3ull*p),val(3ull*p+1),val(3ull*p+2)};}
 Tree(const void*x,size_t N,bool dp):xyz(x),f64(dp),idx(N){
  if(N>UINT32_MAX)throw std::runtime_error("too many points");
  std::iota(idx.begin(),idx.end(),0);V a={1e100,1e100,1e100},b={-1e100,-1e100,-1e100};
  for(size_t i=0;i<N;i++)for(int k=0;k<3;k++){double v=val(3*i+k);if(!std::isfinite(v))throw std::runtime_error("nonfinite");a[k]=std::min(a[k],v);b[k]=std::max(b[k],v);}
  nodes.reserve(N/16+1);if(N)build(0,N,a,b);}
 int build(uint32_t lo,uint32_t hi,V a,V b){
  int id=nodes.size();nodes.push_back({lo,hi,-1,-1,a,b});if(hi-lo<=48)return id;
  int axis=0;for(int k=1;k<3;k++)if(b[k]-a[k]>b[axis]-a[axis])axis=k;
  uint32_t mid=lo+(hi-lo)/2;
  std::nth_element(idx.begin()+lo,idx.begin()+mid,idx.begin()+hi,[&](uint32_t i,uint32_t j){double x=val(3ull*i+axis),y=val(3ull*j+axis);return x<y||(x==y&&i<j);});
  double split=val(3ull*idx[mid]+axis);V al=a,bl=b;bl[axis]=split;al[axis]=split;
  int l=build(lo,mid,a,bl),r=build(mid,hi,al,b);nodes[id].left=l;nodes[id].right=r;return id;}
 // oriented box: |d.axes[j]| <= lim[j]
 template<class F> void box(int id,const V&c,const V axes[3],const double lim[3],F&&f)const{
  const Node&q=nodes[id];V mid,h;for(int k=0;k<3;k++){mid[k]=(q.lower[k]+q.upper[k])*.5-c[k];h[k]=(q.upper[k]-q.lower[k])*.5;}
  for(int j=0;j<3;j++){double span=0;for(int k=0;k<3;k++)span+=std::abs(axes[j][k])*h[k];if(std::abs(dot(mid,axes[j]))>lim[j]+span+1e-8)return;}
  if(q.left>=0){box(q.left,c,axes,lim,f);box(q.right,c,axes,lim,f);return;}
  for(uint32_t j=q.lo;j<q.hi;j++){V p=pt(idx[j]);V d={p[0]-c[0],p[1]-c[1],p[2]-c[2]};f(d,p,idx[j]);}}
 template<class F> void sphere(int id,const V&c,double r,F&&f)const{
  const Node&q=nodes[id];double d2=0;for(int k=0;k<3;k++){double e=std::max({q.lower[k]-c[k],0.,c[k]-q.upper[k]});d2+=e*e;}
  if(d2>r*r+1e-12)return;
  if(q.left>=0){sphere(q.left,c,r,f);sphere(q.right,c,r,f);return;}
  for(uint32_t j=q.lo;j<q.hi;j++){V p=pt(idx[j]);double s=0;for(int k=0;k<3;k++){double e=p[k]-c[k];s+=e*e;}if(s<=r*r)f(p);}}
};
static double median(std::vector<double>&a){if(a.empty())return NAN;std::sort(a.begin(),a.end());size_t m=a.size()/2;return a.size()%2?a[m]:(a[m-1]+a[m])*.5;}
static void perp(const V&n,V&u,V&v){V axis=std::abs(n[2])<.9?V{0,0,1}:V{1,0,0};u=cross(axis,n);double un=std::sqrt(dot(u,u));for(double&x:u)x/=un;v=cross(n,u);}
// smallest-eigenvalue eigenvector of symmetric 3x3 (Jacobi)
static V smallest_eig(double A[3][3]){
 double a[3][3];for(int i=0;i<3;i++)for(int j=0;j<3;j++)a[i][j]=A[i][j];double Vm[3][3]={{1,0,0},{0,1,0},{0,0,1}};
 for(int sweep=0;sweep<50;sweep++){double off=std::abs(a[0][1])+std::abs(a[0][2])+std::abs(a[1][2]);if(off<1e-15)break;
  for(int p=0;p<2;p++)for(int q=p+1;q<3;q++){if(std::abs(a[p][q])<1e-300)continue;double th=(a[q][q]-a[p][p])/(2*a[p][q]);
   double t=(th>=0?1.:-1.)/(std::abs(th)+std::sqrt(th*th+1));double c=1/std::sqrt(t*t+1),s=t*c;
   for(int k=0;k<3;k++){double akp=a[k][p],akq=a[k][q];a[k][p]=c*akp-s*akq;a[k][q]=s*akp+c*akq;}
   for(int k=0;k<3;k++){double apk=a[p][k],aqk=a[q][k];a[p][k]=c*apk-s*aqk;a[q][k]=s*apk+c*aqk;}
   for(int k=0;k<3;k++){double vkp=Vm[k][p],vkq=Vm[k][q];Vm[k][p]=c*vkp-s*vkq;Vm[k][q]=s*vkp+c*vkq;}}}
 int m=0;for(int i=1;i<3;i++)if(a[i][i]<a[m][m])m=i;V n={Vm[0][m],Vm[1][m],Vm[2][m]};double l=std::sqrt(dot(n,n));for(double&x:n)x/=l;return n;}
static void fitn(const std::vector<V>&P,double*out){
 out[0]=P.size();out[1]=out[2]=out[3]=NAN;if(P.size()<3)return;V m={0,0,0};for(auto&p:P)for(int k=0;k<3;k++)m[k]+=p[k];for(int k=0;k<3;k++)m[k]/=P.size();
 double C[3][3]={{0,0,0},{0,0,0},{0,0,0}};for(auto&p:P)for(int i=0;i<3;i++)for(int j=0;j<3;j++)C[i][j]+=(p[i]-m[i])*(p[j]-m[j]);
 V n=smallest_eig(C);out[1]=n[0];out[2]=n[1];out[3]=n[2];}
std::vector<std::vector<uint32_t>> PAIRS;
int main(int argc,char**argv){try{PAIRS.resize(omp_get_max_threads());
 if(argc!=9){std::cerr<<"mode points.npy offset count cores.bin core_count out.bin f4|f8\n";return 2;}
 std::string mode=argv[1],path=argv[2];size_t off=std::stoull(argv[3]),N=std::stoull(argv[4]),nc=std::stoull(argv[6]);bool f64=std::string(argv[8])=="f8";
 int fd=open(path.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open points");struct stat st;fstat(fd,&st);
 if(off+N*3*(f64?8:4)>size_t(st.st_size))throw std::runtime_error("point size");
 void*map=mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);if(map==MAP_FAILED)throw std::runtime_error("mmap");
 Tree tree(static_cast<const char*>(map)+off,N,f64);std::cerr<<"KD_TREE "<<N<<" points\n";
 const int K=8;int cw=mode=="cyl"?8:(mode=="col"?13:(mode=="img"?12:(mode=="pca"?3:(mode=="imgk"?11+K:(mode=="colk"?11+3*K:(mode=="cylk"?10:(mode=="cylids"?8:0))))))),ow=(mode=="cyl"||mode=="cylids")?2:(mode=="col"?17:(mode=="imgk"?1+5*K:(mode=="colk"?2+2*K:(mode=="cylk"?12:8))));if(!cw)throw std::runtime_error("mode");
 std::vector<double> cores(nc*cw),out(nc*ow,NAN);
 {std::ifstream f(argv[5],std::ios::binary);f.read(reinterpret_cast<char*>(cores.data()),cores.size()*8);if(!f)throw std::runtime_error("short cores");}
 #pragma omp parallel for schedule(dynamic,256)
 for(long long i=0;i<(long long)nc;i++){
  const double*q=&cores[i*cw];double*o=&out[i*ow];V c={q[0],q[1],q[2]};
  if(mode=="pca"){std::vector<V> P5,P10;if(N)tree.sphere(0,c,1.0,[&](const V&p){P10.push_back(p);double s=0;for(int k=0;k<3;k++){double e=p[k]-c[k];s+=e*e;}if(s<=.25)P5.push_back(p);});
   fitn(P5,o);fitn(P10,o+4);continue;}
  V n={q[3],q[4],q[5]};double nn=std::sqrt(dot(n,n));if(!(std::isfinite(nn)&&std::abs(nn-1.)<1e-6)){o[0]=-1;continue;}
  if(mode=="cylids"){   // JUDGEEVAL: judgment cylinder point indices (radius q[6], half length q[7]) -> pairs (core, point) to $EVCOLS_IDS
   double r=q[6],Hc=q[7];V u,v;perp(n,u,v);V axes[3]={n,u,v};double lim[3]={Hc,r,r};std::vector<double> t;std::vector<uint32_t> id;
   if(N)tree.box(0,c,axes,lim,[&](const V&d,const V&,uint32_t pi){double tt=dot(d,n);if(std::abs(tt)>Hc)return;double r2=0;for(int k=0;k<3;k++){double e=d[k]-tt*n[k];r2+=e*e;}if(r2<=r*r){t.push_back(tt);id.push_back(pi);}});
   o[0]=t.size();o[1]=median(t);auto&L=PAIRS[omp_get_thread_num()];for(auto pi:id){L.push_back((uint32_t)i);L.push_back(pi);}continue;}
  if(mode=="cylk"){   // JUDGEEVAL: judgment cylinder (radius q[6]) for three half lengths q[7..9]: n, mean, median, sd (all points, no outer face)
   double r=q[6];double Hm=std::max({q[7],q[8],q[9]});V u,v;perp(n,u,v);V axes[3]={n,u,v};double lim[3]={Hm,r,r};std::vector<double> t;
   if(N)tree.box(0,c,axes,lim,[&](const V&d,const V&,uint32_t){double tt=dot(d,n);if(std::abs(tt)>Hm)return;double r2=0;for(int k=0;k<3;k++){double e=d[k]-tt*n[k];r2+=e*e;}if(r2<=r*r)t.push_back(tt);});
   for(int h=0;h<3;h++){std::vector<double> s;for(double x:t)if(std::abs(x)<=q[7+h])s.push_back(x);double*oo=o+4*h;oo[0]=s.size();oo[1]=oo[2]=oo[3]=NAN;
    if(!s.empty()){double m=0;for(double x:s)m+=x;m/=s.size();double vv=0;for(double x:s)vv+=(x-m)*(x-m);oo[1]=m;oo[3]=s.size()>1?std::sqrt(vv/(s.size()-1)):NAN;oo[2]=median(s);}}
   continue;}
  if(mode=="imgk"||mode=="colk"){   // JUDGEEVAL: square patch column, K tolerances at once
   V u={q[6],q[7],q[8]};double half=q[9],H=q[10];double un_=dot(u,n);for(int k=0;k<3;k++)u[k]-=un_*n[k];double un=std::sqrt(dot(u,u));if(!(un>1e-9)){V a,b;perp(n,a,b);u=a;}else for(double&x:u)x/=un;
   V v=cross(n,u);V axes[3]={n,u,v};double lim[3]={H,half,half};std::vector<double> t;
   if(N)tree.box(0,c,axes,lim,[&](const V&d,const V&,uint32_t){double tt=dot(d,n);if(std::abs(tt)>H)return;if(std::abs(dot(d,u))>half||std::abs(dot(d,v))>half)return;t.push_back(tt);});
   std::sort(t.begin(),t.end());size_t T=t.size();
   if(mode=="colk"){long dn=0;for(double x:t)if(std::abs(x)<=1.)dn++;o[0]=T;o[1]=dn;
    for(int k=0;k<K;k++){double tp=q[11+3*k],hi=q[12+3*k],ti=q[13+3*k];if(!std::isfinite(tp)){o[2+2*k]=NAN;o[3+2*k]=NAN;continue;}long b0=0,bi=0;
     for(double x:t){if(std::abs(x)<=tp)b0++;if(std::isfinite(hi)&&std::abs(x-hi)<=ti)bi++;}o[2+2*k]=b0;o[3+2*k]=std::isfinite(hi)?bi:-1;}
    continue;}
   o[0]=T;
   for(int k=0;k<K;k++){double tau=q[11+k];double*oo=o+1+5*k;oo[0]=0;oo[1]=NAN;oo[2]=0;oo[3]=0;oo[4]=NAN;if(!std::isfinite(tau)){oo[0]=NAN;continue;}if(!T)continue;
    std::vector<size_t> J(T);size_t mx=0;for(size_t i=0,j=0;i<T;i++){if(j<i)j=i;while(j<T&&t[j]<=t[i]+2*tau)j++;J[i]=j;mx=std::max(mx,j-i);}
    double best=NAN;size_t bi=0;for(size_t i=0;i<T;i++)if(J[i]-i==mx){std::vector<double> s(t.begin()+i,t.begin()+J[i]);double m=median(s);if(!std::isfinite(best)||std::abs(m)<std::abs(best)){best=m;bi=i;}}
    int tie=0;for(size_t i=0;i<T;i++)if(J[i]-i==mx){std::vector<double> s(t.begin()+i,t.begin()+J[i]);if(std::abs(median(s)-best)>tau)tie=1;}
    double lo=t[bi],hi=t[J[bi]-1];size_t sn=0;double sm=NAN;
    for(size_t i=0;i<T;i++){if(!(t[i]>hi||t[J[i]-1]<lo))continue;size_t cc=J[i]-i;if(cc>sn){sn=cc;std::vector<double> s(t.begin()+i,t.begin()+J[i]);sm=median(s);}}
    oo[0]=mx;oo[1]=best;oo[2]=tie;oo[3]=sn;oo[4]=sm;}
   continue;}
  if(mode=="cyl"){double r=q[6],H=q[7];V u,v;perp(n,u,v);V axes[3]={n,u,v};double lim[3]={H,r,r};std::vector<double> t;
   if(N)tree.box(0,c,axes,lim,[&](const V&d,const V&,uint32_t){double tt=dot(d,n);if(std::abs(tt)>H)return;double r2=0;for(int k=0;k<3;k++){double e=d[k]-tt*n[k];r2+=e*e;}if(r2<=r*r)t.push_back(tt);});
   o[0]=t.size();o[1]=median(t);continue;}
  V u={q[6],q[7],q[8]};double un=std::sqrt(dot(u,u));double half=q[9],H=q[10],tau=q[11],hM=mode=="col"?q[12]:NAN;
  // make u exactly perpendicular to n
  double un_=dot(u,n);for(int k=0;k<3;k++)u[k]-=un_*n[k];un=std::sqrt(dot(u,u));if(!(un>1e-9)){V a,b;perp(n,a,b);u=a;}else for(double&x:u)x/=un;
  V v=cross(n,u);V axes[3]={n,u,v};double lim[3]={H,half,half};std::vector<double> t;
  if(N)tree.box(0,c,axes,lim,[&](const V&d,const V&,uint32_t){double tt=dot(d,n);if(std::abs(tt)>H)return;if(std::abs(dot(d,u))>half||std::abs(dot(d,v))>half)return;t.push_back(tt);});
  std::sort(t.begin(),t.end());
  if(mode=="img"){   // addendum 4: densest window of width 2 tau over the column's image points
   o[0]=t.size();o[1]=0;o[2]=NAN;o[3]=0;o[4]=0;o[5]=NAN;o[6]=NAN;o[7]=NAN;size_t T=t.size();if(!T)continue;
   std::vector<size_t> J(T);size_t mx=0;for(size_t i=0,j=0;i<T;i++){if(j<i)j=i;while(j<T&&t[j]<=t[i]+2*tau)j++;J[i]=j;mx=std::max(mx,j-i);}
   double best=NAN;size_t bi=0;for(size_t i=0;i<T;i++)if(J[i]-i==mx){std::vector<double> s(t.begin()+i,t.begin()+J[i]);double m=median(s);if(!std::isfinite(best)||std::abs(m)<std::abs(best)){best=m;bi=i;}}
   int tie=0;for(size_t i=0;i<T;i++)if(J[i]-i==mx){std::vector<double> s(t.begin()+i,t.begin()+J[i]);if(std::abs(median(s)-best)>tau)tie=1;}
   double lo=t[bi],hi=t[J[bi]-1];size_t sn=0;double sm=NAN;
   // second: densest window lying wholly outside the best window [lo, hi]
   for(size_t i=0;i<T;i++){if(!(t[i]>hi||t[J[i]-1]<lo))continue;size_t c=J[i]-i;if(c>sn){sn=c;std::vector<double> s(t.begin()+i,t.begin()+J[i]);sm=median(s);}}
   o[1]=mx;o[2]=best;o[3]=tie;o[4]=sn;o[5]=sm;o[6]=lo;o[7]=hi;continue;}
  long b0=0,bm=0,dn=0;for(double x:t){if(std::abs(x)<=tau)b0++;if(std::isfinite(hM)&&std::abs(x-hM)<=tau)bm++;if(std::abs(x)<=1.)dn++;}
  o[0]=t.size();o[1]=b0;o[2]=std::isfinite(hM)?bm:-1;o[3]=dn;
  // order 3.2: clusters split where the neighbour gap exceeds 4 tau
  double g=4.*tau;
int ncl=0;size_t s0=0;
  for(size_t k=1;k<=t.size();k++){if(k==t.size()||t[k]-t[k-1]>g){if(ncl<6){std::vector<double> seg(t.begin()+s0,t.begin()+k);o[5+2*ncl]=seg.size();o[6+2*ncl]=median(seg);}ncl++;s0=k;}}
  o[4]=t.empty()?0:ncl;
 }
 std::ofstream f(argv[7],std::ios::binary);f.write(reinterpret_cast<char*>(out.data()),out.size()*8);if(!f)throw std::runtime_error("write");
 if(mode=="cylids"){const char*pp=getenv("EVCOLS_IDS");std::ofstream g(pp,std::ios::binary);for(auto&L:PAIRS)g.write((char*)L.data(),L.size()*4);}
 munmap(map,st.st_size);close(fd);return 0;}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
