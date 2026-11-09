// Orthographic flat-disc / triangle rasterizer. Per-pixel depth-sorted alpha.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
struct Frag {float z,a,r,g,b;int next;};
int main(int argc,char**argv){
 if(argc!=7)return 2;int W=std::stoi(argv[1]),H=std::stoi(argv[2]);bool opaque=std::stoi(argv[3]);
 std::ifstream clip(argv[6]);double centre[3],basis[9],width,height,zmin,zmax;int nrings;for(double &x:centre)clip>>x;for(double &x:basis)clip>>x;clip>>width>>height>>zmin>>zmax>>nrings;
 std::vector<std::vector<std::array<double,2>>> rings(nrings);for(auto &r:rings){int n;clip>>n;r.resize(n);for(auto &p:r)clip>>p[0]>>p[1];}
 auto included=[&](int x,int y,double z){double q[3]={(x+.5-W*.5)*width/W,(H*.5-y-.5)*height/H,z};double p[3];for(int c=0;c<3;c++)p[c]=centre[c]+q[0]*basis[c]+q[1]*basis[3+c]+q[2]*basis[6+c];if(p[2]<zmin||p[2]>zmax)return false;bool inside=false;
  for(const auto&r:rings)for(size_t i=0,j=r.size()-1;i<r.size();j=i++)if((r[i][1]>p[1])!=(r[j][1]>p[1])&&p[0]<(r[j][0]-r[i][0])*(p[1]-r[i][1])/(r[j][1]-r[i][1])+r[i][0])inside=!inside;return inside;};
 std::ifstream in(argv[4],std::ios::binary);std::vector<double> raw;double v;while(in.read((char*)&v,8))raw.push_back(v);
 if(raw.size()%14)return 3;size_t N=raw.size()/14;std::vector<unsigned char> rgb(W*H*3);for(int i=0;i<W*H;i++){rgb[i*3]=252;rgb[i*3+1]=252;rgb[i*3+2]=250;}
 std::vector<float> depth(W*H,INFINITY);std::vector<int> head;std::vector<Frag> fs;if(!opaque){head.assign(W*H,-1);fs.reserve(5000000);}
 size_t drawn=0;
 for(size_t k=0;k<N;k++){
  double*p=raw.data()+14*k;bool tri=p[0]>.5;double det=p[4]*p[8]-p[5]*p[7];if(std::abs(det)<1e-15)continue;
  double rx=tri?std::abs(p[4])+std::abs(p[7]):std::hypot(p[4],p[7]);double ry=tri?std::abs(p[5])+std::abs(p[8]):std::hypot(p[5],p[8]);
  int x0=std::max(0,(int)std::floor(p[1]-rx)),x1=std::min(W-1,(int)std::ceil(p[1]+rx));int y0=std::max(0,(int)std::floor(p[2]-ry)),y1=std::min(H-1,(int)std::ceil(p[2]+ry));bool hit=false;
  for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
   double dx=x+.5-p[1],dy=y+.5-p[2];double a=(dx*p[8]-dy*p[7])/det,b=(p[4]*dy-p[5]*dx)/det;
   if(tri?(a<0||b<0||a+b>1):(a*a+b*b>1))continue;
   int i=y*W+x;double zd=p[3]+a*p[6]+b*p[9];if(!included(x,y,zd))continue;float z=zd;hit=true;
   if(opaque){if(z<depth[i]){depth[i]=z;for(int c=0;c<3;c++)rgb[i*3+c]=(unsigned char)std::round(255*std::clamp(p[10+c],0.,1.));}}
   else {if(fs.size()>500000000){std::cerr<<"FRAGMENT_MEMORY_LIMIT";return 4;}fs.push_back({z,(float)p[13],(float)p[10],(float)p[11],(float)p[12],head[i]});head[i]=(int)fs.size()-1;}
  }drawn+=hit;
 }
 if(!opaque){std::vector<int> order;for(int i=0;i<W*H;i++){
  order.clear();for(int j=head[i];j>=0;j=fs[j].next)order.push_back(j);std::stable_sort(order.begin(),order.end(),[&](int a,int b){return fs[a].z<fs[b].z;});
  double T=1.,col[3]={0,0,0};for(int j:order){auto &f=fs[j];double aa=std::clamp((double)f.a,0.,1.);col[0]+=T*aa*f.r;col[1]+=T*aa*f.g;col[2]+=T*aa*f.b;T*=1-aa;if(T<1e-8)break;}
  for(int c=0;c<3;c++)rgb[i*3+c]=(unsigned char)std::round(255*std::clamp(col[c]+T*(c==2?250.:252.)/255.,0.,1.));
 }}
 std::ofstream out(argv[5],std::ios::binary);out.write((char*)rgb.data(),rgb.size());std::cout<<"primitives="<<N<<" rasterized="<<drawn<<" fragments="<<fs.size()<<"\n";
}
