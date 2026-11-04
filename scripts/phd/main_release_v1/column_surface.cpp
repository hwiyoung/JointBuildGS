// Exact triangle vs inherited square prism intersection. BVH broad phase.
#include <algorithm>
#include <array>
#include <cmath>
#include <numeric>
#include <vector>
using V=std::array<double,3>;
V sub(V a,V b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
V cross(V a,V b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
double dot(V a,V b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
struct Node{V lo,hi;int a,b,l=-1,r=-1;};
struct Tree{
 const double*T;std::vector<int>ix;std::vector<Node>nodes;
 int build(int a,int b){Node v;v.a=a;v.b=b;v.lo={INFINITY,INFINITY,INFINITY};v.hi={-INFINITY,-INFINITY,-INFINITY};
  for(int j=a;j<b;j++)for(int t=0;t<3;t++)for(int k=0;k<3;k++){double x=T[9*ix[j]+3*t+k];v.lo[k]=std::min(v.lo[k],x);v.hi[k]=std::max(v.hi[k],x);}
  int at=nodes.size();nodes.push_back(v);if(b-a>16){int axis=0;for(int k=1;k<3;k++)if(v.hi[k]-v.lo[k]>v.hi[axis]-v.lo[axis])axis=k;int m=(a+b)/2;
   std::nth_element(ix.begin()+a,ix.begin()+m,ix.begin()+b,[&](int i,int j){return T[9*i+axis]+T[9*i+3+axis]+T[9*i+6+axis]<T[9*j+axis]+T[9*j+3+axis]+T[9*j+6+axis];});
   int l=build(a,m),r=build(m,b);nodes[at].l=l;nodes[at].r=r;}return at;}
 bool sep(V axis,V *p,V half){double a=dot(axis,p[0]),b=dot(axis,p[1]),c=dot(axis,p[2]);double r=std::abs(axis[0])*half[0]+std::abs(axis[1])*half[1]+std::abs(axis[2])*half[2];return std::min({a,b,c})>r||std::max({a,b,c})< -r;}
 bool tri(int id,const double*c){V p[3],half={.125,.125,c[12]};
  for(int t=0;t<3;t++){V d={T[9*id+3*t]-c[0],T[9*id+3*t+1]-c[1],T[9*id+3*t+2]-c[2]};for(int k=0;k<3;k++)p[t][k]=c[3+3*k]*d[0]+c[4+3*k]*d[1]+c[5+3*k]*d[2];}
  V axes[3]={{1,0,0},{0,1,0},{0,0,1}};for(V a:axes)if(sep(a,p,half))return false;
  V edges[3]={sub(p[1],p[0]),sub(p[2],p[1]),sub(p[0],p[2])};if(sep(cross(edges[0],edges[1]),p,half))return false;
  for(V e:edges)for(V a:axes)if(sep(cross(e,a),p,half))return false;return true;}
 bool query(int at,const double*c){auto &v=nodes[at];for(int k=0;k<3;k++)if(v.lo[k]>c[16+k]||v.hi[k]<c[13+k])return false;
  if(v.l<0){for(int j=v.a;j<v.b;j++)if(tri(ix[j],c))return true;return false;}return query(v.l,c)||query(v.r,c);}
};
extern "C" void surface_presence(const double*T,int nt,const double*C,int nc,unsigned char*out){
 Tree tree;tree.T=T;tree.ix.resize(nt);std::iota(tree.ix.begin(),tree.ix.end(),0);if(nt)tree.build(0,nt);
 #pragma omp parallel for schedule(dynamic,32)
 for(int i=0;i<nc;i++){const double*c=C+19*i;out[i]=nt&&std::isfinite(c[0])&&std::isfinite(c[3])&&c[12]>0&&tree.query(0,c);}
}
