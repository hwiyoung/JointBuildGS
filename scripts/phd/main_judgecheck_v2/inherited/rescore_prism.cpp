// Exact square-prism membership, with a 1 m spatial hash used only for candidates.
// Input: float64 points Nx3; columns Mx19 (centre, inverse basis, length, bbox).
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <unordered_map>
#include <vector>
using Key=std::array<int,3>;
struct Hash {size_t operator()(Key const& q) const {size_t h=1469598103934665603ULL;for(int x:q){h^=uint32_t(x);h*=1099511628211ULL;}return h;}};
template<class T> std::vector<T> read(const char* p){std::ifstream f(p,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error(p);auto n=f.tellg();std::vector<T>a(size_t(n)/sizeof(T));f.seekg(0);f.read((char*)a.data(),n);return a;}
template<class T> void write(const char* p,std::vector<T>const&a){std::ofstream f(p,std::ios::binary);f.write((const char*)a.data(),a.size()*sizeof(T));if(!f)throw std::runtime_error(p);}
int main(int argc,char**argv){
 if(argc!=5)return 2;auto P=read<double>(argv[1]),C=read<double>(argv[2]);if(P.size()%3||C.size()%19)return 3;
 size_t n=P.size()/3,m=C.size()/19;std::unordered_map<Key,std::vector<int32_t>,Hash> grid;
 for(size_t j=0;j<m;j++){auto c=&C[j*19];if(!std::isfinite(c[0])||!std::isfinite(c[3])||c[12]<=0)continue;
  for(int x=int(std::floor(c[13]));x<=int(std::floor(c[16]));x++)for(int y=int(std::floor(c[14]));y<=int(std::floor(c[17]));y++)for(int z=int(std::floor(c[15]));z<=int(std::floor(c[18]));z++)grid[{x,y,z}].push_back(j);
 }
 std::vector<int32_t>owner(n,-1),hits(n,0);
 for(size_t i=0;i<n;i++){auto p=&P[3*i];Key key={int(std::floor(p[0])),int(std::floor(p[1])),int(std::floor(p[2]))};auto it=grid.find(key);if(it==grid.end())continue;double best=std::numeric_limits<double>::infinity();
  for(int j:it->second){auto c=&C[j*19];double v[3]={p[0]-c[0],p[1]-c[1],p[2]-c[2]};double a=c[3]*v[0]+c[4]*v[1]+c[5]*v[2],b=c[6]*v[0]+c[7]*v[1]+c[8]*v[2],h=c[9]*v[0]+c[10]*v[1]+c[11]*v[2];
   if(std::abs(a)>.125||std::abs(b)>.125||std::abs(h)>c[12])continue;hits[i]++;double d=std::abs(h);if(d<best||(d==best&&j<owner[i])){best=d;owner[i]=j;}
  }
 }
 write(argv[3],owner);write(argv[4],hits);std::cout<<"points "<<n<<" columns "<<m<<" occupied_grid_cells "<<grid.size()<<"\n";
}
