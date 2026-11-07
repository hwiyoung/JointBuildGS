// Exact point-ID display queries, independent of saved scoring distances.
#include <algorithm>
#include <cmath>
#include <vector>
#include <numeric>
#include <limits>
struct Node { double c[3],e[3]; int a,b,l=-1,r=-1; };
struct Tree {
 const double *p,*normals; std::vector<int> ids; std::vector<Node> nodes;
 Tree(const double* x,const double* nn,int n):p(x),normals(nn),ids(n){std::iota(ids.begin(),ids.end(),0);nodes.reserve(n/8+1);build(0,n);}
 int build(int a,int b){Node v;v.a=a;v.b=b;for(int d=0;d<3;d++){double lo=1e300,hi=-1e300;for(int i=a;i<b;i++){lo=std::min(lo,p[3*ids[i]+d]);hi=std::max(hi,p[3*ids[i]+d]);}v.c[d]=(hi+lo)/2;v.e[d]=(hi-lo)/2;}int id=nodes.size();nodes.push_back(v);if(b-a>16){int d=0;for(int k=1;k<3;k++)if(v.e[k]>v.e[d])d=k;int m=(a+b)/2;std::nth_element(ids.begin()+a,ids.begin()+m,ids.begin()+b,[&](int x,int y){return p[3*x+d]<p[3*y+d];});int l=build(a,m),r=build(m,b);nodes[id].l=l;nodes[id].r=r;}return id;}
 double side_bound(int id,const double* q,const double* u,const double* v){const Node& node=nodes[id];double lower=0;for(const double* axis:{u,v}){double c=0,e=0;for(int d=0;d<3;d++){c+=(node.c[d]-q[d])*axis[d];e+=node.e[d]*std::abs(axis[d]);}double x=std::max(0.,std::abs(c)-e-1e-10);lower+=x*x;}return lower;}
 void side_query(int id,const double* q,const double* n,const double* u,const double* v,double& best,double& axial,int& chosen){const Node& node=nodes[id];if(side_bound(id,q,u,v)>best+1e-14)return;if(node.l<0){for(int j=node.a;j<node.b;j++){int i=ids[j];double a=0,b=0,s=0;for(int d=0;d<3;d++){double x=p[3*i+d]-q[d];a+=x*u[d];b+=x*v[d];s+=x*n[d];}double dd=a*a+b*b,ax=std::abs(s);if(dd<best || (dd==best&&(chosen<0||ax<axial||(ax==axial&&i<chosen)))){best=dd;axial=ax;chosen=i;}}return;}double a=side_bound(node.l,q,u,v),b=side_bound(node.r,q,u,v);int first=a<=b?node.l:node.r,second=a<=b?node.r:node.l;side_query(first,q,n,u,v,best,axial,chosen);side_query(second,q,n,u,v,best,axial,chosen);}
 double ray_bound(int id,const double* o,const double* d,double radius,double best){const Node& v=nodes[id];double lo=0,hi=best;for(int k=0;k<3;k++){double a=v.c[k]-v.e[k]-radius-1e-10-o[k],b=v.c[k]+v.e[k]+radius+1e-10-o[k];if(std::abs(d[k])<1e-15){if(a>0||b<0)return INFINITY;}else{a/=d[k];b/=d[k];if(a>b)std::swap(a,b);lo=std::max(lo,a);hi=std::min(hi,b);if(lo>hi)return INFINITY;}}return lo;}
 void disc_query(int id,const double* o,const double* d,double radius,double& best,int& chosen){const Node& v=nodes[id];double bound=ray_bound(id,o,d,radius,best);if(!std::isfinite(bound)||bound>best)return;if(v.l<0){for(int j=v.a;j<v.b;j++){int i=ids[j];const double* n=normals+3*i;double num=0,den=0;for(int k=0;k<3;k++){num+=(p[3*i+k]-o[k])*n[k];den+=d[k]*n[k];}if(std::abs(den)<1e-12)continue;double t=num/den;if(t<=0||t>best)continue;double r2=0;for(int k=0;k<3;k++){double x=o[k]+t*d[k]-p[3*i+k];r2+=x*x;}if(r2<=radius*radius&&(t<best||chosen<0||i<chosen)){best=t;chosen=i;}}return;}double a=ray_bound(v.l,o,d,radius,best),b=ray_bound(v.r,o,d,radius,best);if(a<=b){if(a<=best)disc_query(v.l,o,d,radius,best,chosen);if(b<=best)disc_query(v.r,o,d,radius,best,chosen);}else{if(b<=best)disc_query(v.r,o,d,radius,best,chosen);if(a<=best)disc_query(v.l,o,d,radius,best,chosen);}}
};
extern "C" void* build(const double* p,const double* normals,int n){return new Tree(p,normals,n);}
extern "C" void destroy(void* t){delete (Tree*)t;}
extern "C" void assign_rows(void* t,const double* p,const double* normals,int count,double radius,int* out,double* distance){Tree* tree=(Tree*)t;
#pragma omp parallel for num_threads(6) schedule(dynamic,128)
 for(int i=0;i<count;i++){const double* n=normals+3*i;int k=0;for(int d=1;d<3;d++)if(std::abs(n[d])<std::abs(n[k]))k=d;double u[3]={0,0,0};u[(k+1)%3]=n[(k+2)%3];u[(k+2)%3]=-n[(k+1)%3];double len=std::sqrt(u[0]*u[0]+u[1]*u[1]+u[2]*u[2]);for(int d=0;d<3;d++)u[d]/=len;double v[3]={n[1]*u[2]-n[2]*u[1],n[2]*u[0]-n[0]*u[2],n[0]*u[1]-n[1]*u[0]};double best=radius*radius,axial=INFINITY;int chosen=-1;tree->side_query(0,p+3*i,n,u,v,best,axial,chosen);out[i]=chosen;distance[i]=chosen<0?INFINITY:std::sqrt(best);}}
extern "C" void disc_rows(void* t,const double* origins,const double* directions,int count,double radius,int* out,double* distance){Tree* tree=(Tree*)t;
#pragma omp parallel for num_threads(6) schedule(dynamic,128)
 for(int i=0;i<count;i++){double best=INFINITY;int chosen=-1;tree->disc_query(0,origins+3*i,directions+3*i,radius,best,chosen);out[i]=chosen;distance[i]=best;}}
