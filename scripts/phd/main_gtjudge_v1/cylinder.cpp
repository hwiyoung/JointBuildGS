#include <algorithm>
#include <cmath>
#include <vector>
#include <numeric>
#include <limits>
struct Node{double lo[3],hi[3];int a,b,l=-1,r=-1;};
struct Tree{const double* p;std::vector<int> ids;std::vector<Node> nodes;
 Tree(const double* x,int n):p(x),ids(n){std::iota(ids.begin(),ids.end(),0);nodes.reserve(n/8+1);build(0,n);}
 int build(int a,int b){Node v;v.a=a;v.b=b;for(int d=0;d<3;d++){v.lo[d]=1e300;v.hi[d]=-1e300;for(int i=a;i<b;i++){double q=p[3*ids[i]+d];v.lo[d]=std::min(v.lo[d],q);v.hi[d]=std::max(v.hi[d],q);}}
 int id=nodes.size();nodes.push_back(v);if(b-a>24){int d=0;for(int k=1;k<3;k++)if(v.hi[k]-v.lo[k]>v.hi[d]-v.lo[d])d=k;int m=(a+b)/2;
 std::nth_element(ids.begin()+a,ids.begin()+m,ids.begin()+b,[&](int x,int y){return p[3*x+d]<p[3*y+d];});int l=build(a,m),r=build(m,b);nodes[id].l=l;nodes[id].r=r;}return id;}
 double bound(const Node& v,const double* q,const double* n,double radius,double best){
 // Conservative bounds only; exact cylinder membership is still tested at leaves.
 for(int d=0;d<3;d++){double e=best*std::abs(n[d])+radius*std::sqrt(std::max(0.,1-n[d]*n[d]));if(v.lo[d]>q[d]+e+1e-12||v.hi[d]<q[d]-e-1e-12)return 1e300;}
 int k=0;for(int d=1;d<3;d++)if(std::abs(n[d])<std::abs(n[k]))k=d;
 double u[3]={0,0,0};u[(k+1)%3]=n[(k+2)%3];u[(k+2)%3]=-n[(k+1)%3];double un=std::sqrt(u[0]*u[0]+u[1]*u[1]+u[2]*u[2]);for(int d=0;d<3;d++)u[d]/=un;
 double w[3]={n[1]*u[2]-n[2]*u[1],n[2]*u[0]-n[0]*u[2],n[0]*u[1]-n[1]*u[0]};double lower_rad2=0;
 for(const double* axis:{u,w}){double center=0,extent=0;for(int d=0;d<3;d++){center+=((v.lo[d]+v.hi[d])*.5-q[d])*axis[d];extent+=(v.hi[d]-v.lo[d])*.5*std::abs(axis[d]);}double b=std::max(0.,std::abs(center)-extent-1e-12);lower_rad2+=b*b;}
 if(lower_rad2>radius*radius)return 1e300;
 double s=0,extent=0,rho=0,diag=0,delta[3];for(int d=0;d<3;d++){delta[d]=(v.lo[d]+v.hi[d])*.5-q[d];double e=(v.hi[d]-v.lo[d])*.5;s+=delta[d]*n[d];extent+=e*std::abs(n[d]);diag+=e*e;}
 for(int d=0;d<3;d++){double x=delta[d]-s*n[d];rho+=x*x;}double lower=std::max(0.,std::abs(s)-extent);if(lower>best||std::sqrt(rho)>radius+std::sqrt(diag))return 1e300;return lower;}
 void query(int id,const double* q,const double* n,double radius,double &best,double &answer,int &chosen){const Node& v=nodes[id];if(bound(v,q,n,radius,best)>best)return;
 if(v.l<0){for(int j=v.a;j<v.b;j++){int i=ids[j];double dx[3],s=0;for(int d=0;d<3;d++){dx[d]=p[3*i+d]-q[d];s+=dx[d]*n[d];}double a=std::abs(s);if(a>best)continue;double rad=0;for(int d=0;d<3;d++){double x=dx[d]-s*n[d];rad+=x*x;}if(rad<=radius*radius&&(a<best||chosen<0||(a==best&&i<chosen))){best=a;answer=s;chosen=i;}}return;}
 double bl=bound(nodes[v.l],q,n,radius,best),br=bound(nodes[v.r],q,n,radius,best);if(bl<=br){if(bl<=best)query(v.l,q,n,radius,best,answer,chosen);if(br<=best)query(v.r,q,n,radius,best,answer,chosen);}else{if(br<=best)query(v.r,q,n,radius,best,answer,chosen);if(bl<=best)query(v.l,q,n,radius,best,answer,chosen);}}
};
extern "C" void* build(const double* p,int n){return new Tree(p,n);}
extern "C" void destroy(void* t){delete (Tree*)t;}
extern "C" void query(void* t,const double* q,const double* normal,const double* lengths,int n,double radius,double* out,int* index){Tree* tree=(Tree*)t;
#pragma omp parallel for num_threads(4) schedule(dynamic,128)
 for(int i=0;i<n;i++){double best=lengths[i],answer=std::numeric_limits<double>::quiet_NaN();int chosen=-1;tree->query(0,q+3*i,normal+3*i,radius,best,answer,chosen);out[i]=answer;index[i]=chosen;}}
