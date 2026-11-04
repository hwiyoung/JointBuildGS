// Exact nearest target in tangential distance; no normal-distance truncation.
// A spatial/normal BVH only prunes using conservative lower bounds.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <vector>
using V=std::array<double,3>;
V sub(V a,V b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
double dot(V a,V b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
double norm(V a){return std::sqrt(dot(a,a));}
struct Node{V c,n;double r,dn;int a,b,l=-1,rchild=-1;};
struct Tree{
 std::vector<V> p,n;std::vector<double>w;std::vector<int64_t> id;std::vector<int> ix;std::vector<Node>nodes;
 int build(int a,int b){
  Node v;v.a=a;v.b=b;V lo=p[ix[a]],hi=lo;
  for(int j=a;j<b;j++)for(int k=0;k<3;k++){lo[k]=std::min(lo[k],p[ix[j]][k]);hi[k]=std::max(hi[k],p[ix[j]][k]);}
  for(int k=0;k<3;k++)v.c[k]=(lo[k]+hi[k])/2;
  v.n=n[ix[a]];v.r=0;v.dn=0;
  for(int j=a;j<b;j++){v.r=std::max(v.r,norm(sub(p[ix[j]],v.c)));v.dn=std::max(v.dn,norm(sub(n[ix[j]],v.n)));}
  int at=nodes.size();nodes.push_back(v);
  if(b-a>24){int axis=0;for(int k=1;k<3;k++)if(hi[k]-lo[k]>hi[axis]-lo[axis])axis=k;int m=(a+b)/2;
   std::nth_element(ix.begin()+a,ix.begin()+m,ix.begin()+b,[&](int i,int j){return p[i][axis]<p[j][axis];});
   int left=build(a,m),right=build(m,b);nodes[at].l=left;nodes[at].rchild=right;}
  return at;
 }
 double lower(int j,V q){auto &v=nodes[j];V d=sub(q,v.c);double h=dot(d,v.n);V t={d[0]-h*v.n[0],d[1]-h*v.n[1],d[2]-h*v.n[2]};return std::max(0.,norm(t)-v.r-2*norm(d)*v.dn-1e-9);}
 void visit(int j,V q,double &best,double &ex,int64_t &chosen){
  if(lower(j,q)>best)return;auto &v=nodes[j];
  if(v.l<0){for(int k=v.a;k<v.b;k++){int i=ix[k];V d=sub(q,p[i]);double h=dot(d,n[i]);V t={d[0]-h*n[i][0],d[1]-h*n[i][1],d[2]-h*n[i][2]};double tt=norm(t),e=std::max(std::abs(h)-w[i],0.);
   if(chosen<0||tt<best||(tt==best&&(e<ex||(e==ex&&id[i]<id[chosen])))){best=tt;ex=e;chosen=i;}}
  }else{int a=v.l,b=v.rchild;if(lower(a,q)>lower(b,q))std::swap(a,b);visit(a,q,best,ex,chosen);visit(b,q,best,ex,chosen);}
 }
};
extern "C" void* release_tree(const double* p,const double*n,const double*w,const int64_t*ids,int64_t count){
 auto*t=new Tree;t->p.resize(count);t->n.resize(count);t->w.assign(w,w+count);t->id.assign(ids,ids+count);t->ix.resize(count);std::iota(t->ix.begin(),t->ix.end(),0);
 for(int64_t i=0;i<count;i++){for(int k=0;k<3;k++){t->p[i][k]=p[3*i+k];t->n[i][k]=n[3*i+k];}double a=norm(t->n[i]);for(double &x:t->n[i])x/=a;}
 if(count)t->build(0,count);return t;
}
extern "C" void release_query(void*ptr,const double*q,int64_t count,double*dist,double*excess,int64_t*out){
 auto*t=(Tree*)ptr;
 #pragma omp parallel for schedule(dynamic,64)
 for(int64_t i=0;i<count;i++){double d=std::numeric_limits<double>::infinity(),e=d;int64_t j=-1;if(!t->nodes.empty())t->visit(0,{q[3*i],q[3*i+1],q[3*i+2]},d,e,j);dist[i]=d;excess[i]=e;out[i]=j;}
}
extern "C" void release_free(void* p){delete (Tree*)p;}
