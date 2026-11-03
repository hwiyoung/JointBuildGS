// Exact shared-edge connected components, triangle-count cutoff, and eval crop.
// Bounded implementation of inherited post_process_mesh, preserving file order.
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
struct Edge {uint64_t key;uint32_t tri;bool operator<(Edge const& b)const{return key<b.key;}};
uint32_t root(std::vector<uint32_t>&p,uint32_t a){while(p[a]!=a){p[a]=p[p[a]];a=p[a];}return a;}
int main(int argc,char**argv){
 if(argc!=10)return 2;std::ifstream f(argv[1],std::ios::binary);std::string line;size_t nv=0,nf=0;bool verts=false;int vb=0;
 while(std::getline(f,line)){if(line=="end_header")break;std::istringstream s(line);std::string a,b,c;s>>a>>b>>c;if(a=="element"){verts=b=="vertex";if(verts)nv=std::stoull(c);else if(b=="face")nf=std::stoull(c);}else if(a=="property"&&verts){if(b=="double")vb+=8;else if(b=="uchar")vb++;else throw std::runtime_error("Unsupported PLY vertex property");}}
 if(vb!=27)throw std::runtime_error("Expected Open3D xyz64 RGB8 PLY");size_t off=f.tellg();f.close();int fd=open(argv[1],O_RDONLY);struct stat st;fstat(fd,&st);const unsigned char*data=(const unsigned char*)mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);auto V=data+off;auto F=V+nv*vb;
 if(off+nv*vb+nf*13!=size_t(st.st_size))throw std::runtime_error("PLY size mismatch");
 std::vector<Edge>edges;edges.reserve(3*nf);std::vector<uint32_t>p(nf),size(nf,1);std::iota(p.begin(),p.end(),0);
 for(size_t i=0;i<nf;i++){uint32_t t[3];if(F[i*13]!=3)return 3;std::memcpy(t,F+i*13+1,12);for(int k=0;k<3;k++){auto a=std::min(t[k],t[(k+1)%3]),b=std::max(t[k],t[(k+1)%3]);edges.push_back({(uint64_t(a)<<32)|b,uint32_t(i)});}}
 std::cout<<"EDGES "<<edges.size()<<std::endl;std::sort(edges.begin(),edges.end());
 for(size_t i=1;i<edges.size();i++)if(edges[i].key==edges[i-1].key){auto a=root(p,edges[i].tri),b=root(p,edges[i-1].tri);if(a!=b){if(size[a]<size[b])std::swap(a,b);p[b]=a;size[a]+=size[b];}}
 edges.clear();edges.shrink_to_fit();std::vector<uint32_t>counts;for(size_t i=0;i<nf;i++)if(p[i]==i)counts.push_back(size[i]);std::sort(counts.begin(),counts.end());if(counts.size()<50)throw std::runtime_error("Inherited cleanup requires at least 50 components");uint32_t cut=std::max<uint32_t>(counts[counts.size()-50],50);
 double co=std::stod(argv[4]),si=std::stod(argv[5]),u0=std::stod(argv[6]),u1=std::stod(argv[7]),v0=std::stod(argv[8]),v1=std::stod(argv[9]);std::vector<uint8_t>inside(nv),used(nv),keep(nf);size_t nc=0,nout=0;
 for(size_t i=0;i<nv;i++){double xyz[3];std::memcpy(xyz,V+i*vb,24);double u=co*xyz[0]+si*xyz[1],v=si*xyz[0]-co*xyz[1];inside[i]=u>=u0&&u<=u1&&v>=v0&&v<=v1;}
 for(size_t i=0;i<nf;i++){if(size[root(p,i)]<cut)continue;uint32_t t[3];std::memcpy(t,F+i*13+1,12);if(t[0]==t[1]||t[1]==t[2]||t[2]==t[0])continue;nc++;if(!(inside[t[0]]&&inside[t[1]]&&inside[t[2]]))continue;keep[i]=1;nout++;for(auto j:t)used[j]=1;}
 p.clear();size.clear();p.shrink_to_fit();size.shrink_to_fit();std::vector<uint32_t>index(nv);uint32_t nvo=0;for(size_t i=0;i<nv;i++)if(used[i])index[i]=nvo++;
 std::ofstream o(argv[2],std::ios::binary);o<<"ply\nformat binary_little_endian 1.0\ncomment RESCORE inherited component rule bounded memory\nelement vertex "<<nvo<<"\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face "<<nout<<"\nproperty list uchar uint vertex_indices\nend_header\n";
 for(size_t i=0;i<nv;i++)if(used[i])o.write((char*)V+i*vb,vb);
 for(size_t i=0;i<nf;i++)if(keep[i]){uint32_t t[3];std::memcpy(t,F+i*13+1,12);for(auto&j:t)j=index[j];o.put(char(3));o.write((char*)t,12);}o.close();if(!o)return 4;
 std::ofstream j(argv[3]);j<<"{\"raw_triangles\":"<<nf<<",\"components\":"<<counts.size()<<",\"cutoff_triangles\":"<<cut<<",\"cleanup_triangles\":"<<nc<<",\"final_triangles\":"<<nout<<",\"final_vertices\":"<<nvo<<"}\n";munmap((void*)data,st.st_size);close(fd);std::cout<<"CLEANUP_COMPLETE "<<nout<<std::endl;
}
