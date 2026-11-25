// PHD-MAIN-JUDGEEVAL-v1: step 2 visibility (Merrell et al. 2007 free-space violation per pixel) and step 3 multi-view geometric consistency
// pixel (col,row) is at image coordinate (col,row) as in COLMAP MVS and the earlier unprojection (mfcommon.unproject).
// (COLMAP StereoFusion rules, fusion.cc; evaluated per start pixel without merging). CPU, OpenMP. No truth is read.
// usage:
//  judgevis vis  cams.bin maps.txt patches.bin NP out.bin passpix.bin
//     patches: s(3) n(3) u(3) half (10 doubles; s = point on the prior surface). out per patch (20 doubles):
//       for d in {1%,5%}: pixels unseen, pass, block, agree, images_with_pass, images_with_vote   (12)
//       for d in {1%,5%}: centre pixel per image: images unseen, pass, block, agree                (8)
//     passpix: int32 triples (patch, image, row*W+col) of pixels classed pass at 1 %.
//  judgevis fuse cams.bin maps.txt overlap.bin starts.bin NS out.bin
//     starts: int32 pairs (image, row*W+col). out per start (3 int32): colmap_consistent (cluster >= min_num_pixels), cluster size reached (capped),
//       A2 image count (overlapping images j where the direct projection passes the three conditions).
// cams.bin: int32 n, W, H; then per image 16 doubles: R(9) t(3) fx fy cx cy  (x_cam = R x_world + t, COLMAP).
// maps.txt: per image one line "<depth.bin>\t<normal.bin>" (COLMAP geometric maps).
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <unordered_set>
#include <omp.h>
using V=std::array<double,3>;
struct Cam{double R[9],t[3],fx,fy,cx,cy;};
int NI,W,H;std::vector<Cam> cams;std::vector<std::vector<float>> depth,normal;
static std::vector<float> readmap(const std::string&p,int ch){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("open "+p);std::string hdr;int amp=0;char c;
 while(amp<3&&f.get(c)){hdr+=c;if(c=='&')amp++;}int w,h,cc;char x;std::istringstream is(hdr);is>>w>>x>>h>>x>>cc;if(w!=W||h!=H||cc!=ch)throw std::runtime_error("size "+p);
 std::vector<float> raw((size_t)w*h*cc);f.read((char*)raw.data(),raw.size()*4);std::vector<float> out((size_t)w*h*cc);
 // COLMAP .bin maps: per channel, rows of w values (same as mfcommon.read_depth / read_bin, verified by unprojection): raw[ch][row][col] -> out[(row*W+col)*cc+ch]
 for(int k=0;k<cc;k++)for(int row=0;row<h;row++)for(int col=0;col<w;col++)out[((size_t)row*w+col)*cc+k]=raw[(size_t)k*w*h+(size_t)row*w+col];return out;}
static void load(const char*cb,const char*mt,bool normals){std::ifstream f(cb,std::ios::binary);f.read((char*)&NI,4);f.read((char*)&W,4);f.read((char*)&H,4);cams.resize(NI);
 for(auto&c:cams){double v[16];f.read((char*)v,128);for(int i=0;i<9;i++)c.R[i]=v[i];for(int i=0;i<3;i++)c.t[i]=v[9+i];c.fx=v[12];c.fy=v[13];c.cx=v[14];c.cy=v[15];}
 std::ifstream m(mt);std::vector<std::pair<std::string,std::string>> P;std::string line;while(std::getline(m,line)){auto k=line.find('\t');P.push_back({line.substr(0,k),line.substr(k+1)});}
 if((int)P.size()!=NI)throw std::runtime_error("maps count");depth.resize(NI);if(normals)normal.resize(NI);
 #pragma omp parallel for schedule(dynamic,1)
 for(int i=0;i<NI;i++){depth[i]=readmap(P[i].first,1);if(normals)normal[i]=readmap(P[i].second,3);}
 std::cerr<<"LOADED "<<NI<<" maps\n";}
static inline void tocam(const Cam&c,const double*X,double*Y){for(int r=0;r<3;r++)Y[r]=c.R[3*r]*X[0]+c.R[3*r+1]*X[1]+c.R[3*r+2]*X[2]+c.t[r];}
static inline void toworld(const Cam&c,const double*Y,double*X){double d[3]={Y[0]-c.t[0],Y[1]-c.t[1],Y[2]-c.t[2]};for(int r=0;r<3;r++)X[r]=c.R[r]*d[0]+c.R[3+r]*d[1]+c.R[6+r]*d[2];}
static inline int cls(double D,double Z,double rel){if(!(D>0))return 0;double dl=rel*Z;if(D>Z+dl)return 1;if(D<Z-dl)return 2;return 3;}   // 0 unseen 1 pass 2 block 3 agree
int vis(int argc,char**argv){load(argv[2],argv[3],false);size_t NP=std::stoull(argv[5]);std::vector<double> P(NP*10);{std::ifstream f(argv[4],std::ios::binary);f.read((char*)P.data(),P.size()*8);}
 std::vector<std::atomic<long>> cnt(NP*20);for(auto&a:cnt)a=0;std::vector<std::vector<int32_t>> pass(omp_get_max_threads());const double rels[2]={0.01,0.05};
 #pragma omp parallel for schedule(dynamic,1)
 for(int im=0;im<NI;im++){const Cam&c=cams[im];auto&pl=pass[omp_get_thread_num()];const float*Dm=depth[im].data();
  double cw[3]; {double z[3]={0,0,0};toworld(c,z,cw);}
  for(size_t p=0;p<NP;p++){const double*q=&P[p*10];double sc[3];tocam(c,q,sc);if(sc[2]<=0.05)continue;double uc=c.fx*sc[0]/sc[2]+c.cx,vc=c.fy*sc[1]/sc[2]+c.cy;
   if(uc<-50||vc<-50||uc>W+50||vc>H+50)continue;
   double n[3]={q[3],q[4],q[5]},u[3]={q[6],q[7],q[8]},v[3]={n[1]*u[2]-n[2]*u[1],n[2]*u[0]-n[0]*u[2],n[0]*u[1]-n[1]*u[0]};double h=q[9];
   double px[4],py[4];bool ok=true;const double sg[4][2]={{-1,-1},{1,-1},{1,1},{-1,1}};
   for(int k=0;k<4;k++){double X[3],Y[3];for(int r=0;r<3;r++)X[r]=q[r]+sg[k][0]*h*u[r]+sg[k][1]*h*v[r];tocam(c,X,Y);if(Y[2]<=0.05){ok=false;break;}px[k]=c.fx*Y[0]/Y[2]+c.cx;py[k]=c.fy*Y[1]/Y[2]+c.cy;}
   if(!ok)continue;
   // plane in camera coords: nc . Y = nc . sc
   double nc[3]={c.R[0]*n[0]+c.R[1]*n[1]+c.R[2]*n[2],c.R[3]*n[0]+c.R[4]*n[1]+c.R[5]*n[2],c.R[6]*n[0]+c.R[7]*n[1]+c.R[8]*n[2]};double rhs=nc[0]*sc[0]+nc[1]*sc[1]+nc[2]*sc[2];
   auto Zat=[&](double uu,double vv){double d[3]={(uu-c.cx)/c.fx,(vv-c.cy)/c.fy,1.};double den=nc[0]*d[0]+nc[1]*d[1]+nc[2]*d[2];if(std::abs(den)<1e-9)return -1.;return rhs/den;};
   // centre pixel
   int cu=(int)std::lround(uc),cv=(int)std::lround(vc);   // COLMAP convention: pixel (col,row) sits at u = col
   if(cu>=0&&cv>=0&&cu<W&&cv<H){double Z=Zat(cu,cv);if(Z>0){double D=Dm[(size_t)cv*W+cu];for(int k=0;k<2;k++)cnt[p*20+12+4*k+cls(D,Z,rels[k])]++;}}
   // pixels inside the projected quad (pixel centre test)
   int x0=std::max(0,(int)std::floor(std::min({px[0],px[1],px[2],px[3]}))),x1=std::min(W-1,(int)std::ceil(std::max({px[0],px[1],px[2],px[3]})));
   int y0=std::max(0,(int)std::floor(std::min({py[0],py[1],py[2],py[3]}))),y1=std::min(H-1,(int)std::ceil(std::max({py[0],py[1],py[2],py[3]})));
   double area=0;for(int k=0;k<4;k++){int k2=(k+1)%4;area+=px[k]*py[k2]-px[k2]*py[k];}double sgn=area>=0?1:-1;
   int c4[2][4]={{0,0,0,0},{0,0,0,0}};bool anyp[2]={false,false},anyv[2]={false,false};
   for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){double X=x,Y=y;bool in=true;for(int k=0;k<4;k++){int k2=(k+1)%4;double cr=(px[k2]-px[k])*(Y-py[k])-(py[k2]-py[k])*(X-px[k]);if(cr*sgn<0){in=false;break;}}
    if(!in)continue;double Z=Zat(X,Y);if(!(Z>0))continue;double D=Dm[(size_t)y*W+x];
    for(int k=0;k<2;k++){int cl=cls(D,Z,rels[k]);c4[k][cl]++;if(cl==1)anyp[k]=true;if(cl)anyv[k]=true;if(k==0&&cl==1){pl.push_back((int32_t)p);pl.push_back(im);pl.push_back(y*W+x);}}}
   for(int k=0;k<2;k++){for(int j=0;j<4;j++)if(c4[k][j])cnt[p*20+6*k+j]+=c4[k][j];if(anyp[k])cnt[p*20+6*k+4]++;if(anyv[k])cnt[p*20+6*k+5]++;}}
  if(im%50==0)std::cerr<<"IMG "<<im<<"\n";}
 {std::vector<double> o(NP*20);for(size_t i=0;i<o.size();i++)o[i]=cnt[i];std::ofstream f(argv[6],std::ios::binary);f.write((char*)o.data(),o.size()*8);}
 {std::ofstream f(argv[7],std::ios::binary);for(auto&v:pass)f.write((char*)v.data(),v.size()*4);}return 0;}
// ---- fusion (COLMAP StereoFusion::Fuse rules, per start pixel, own visited set)
std::vector<std::vector<int>> ovl;
static inline bool proj(const Cam&c,const double*X,double&u,double&v,double&z){double Y[3];tocam(c,X,Y);if(Y[2]<=0)return false;z=Y[2];u=c.fx*Y[0]/Y[2]+c.cx;v=c.fy*Y[1]/Y[2]+c.cy;return true;}
static inline void pix3d(int im,int row,int col,double d,double*X){const Cam&c=cams[im];double Y[3]={(col-c.cx)/c.fx*d,(row-c.cy)/c.fy*d,d};toworld(c,Y,X);}
static inline void nworld(int im,int row,int col,double*N){const Cam&c=cams[im];const float*nm=&normal[im][((size_t)row*W+col)*3];double Y[3]={nm[0],nm[1],nm[2]};
 for(int r=0;r<3;r++)N[r]=c.R[r]*Y[0]+c.R[3+r]*Y[1]+c.R[6+r]*Y[2];}
int fuse(int argc,char**argv){load(argv[2],argv[3],true);{std::ifstream f(argv[4],std::ios::binary);int n,k;f.read((char*)&n,4);f.read((char*)&k,4);ovl.assign(n,{});for(int i=0;i<n;i++){std::vector<int> v(k);f.read((char*)v.data(),k*4);for(int x:v)if(x>=0)ovl[i].push_back(x);}}
 size_t NS=std::stoull(argv[6]);std::vector<int32_t> S(NS*2);{std::ifstream f(argv[5],std::ios::binary);f.read((char*)S.data(),S.size()*4);}std::vector<int32_t> out(NS*3,0);
 const double MDE=0.01,MRE2=2.0*2.0,MCN=std::cos(10.0*M_PI/180.0);const int MINP=5,MAXT=100;
 #pragma omp parallel for schedule(dynamic,256)
 for(long long s=0;s<(long long)NS;s++){int im0=S[2*s],pix0=S[2*s+1];int r0=pix0/W,c0=pix0%W;double d0=depth[im0][pix0];if(!(d0>0))continue;
  double Xr[3],Nr[3];pix3d(im0,r0,c0,d0,Xr);nworld(im0,r0,c0,Nr);
  // A2: one hop, overlapping images, same three conditions
  int a2=0;for(int j:ovl[im0]){double u,v,z;if(!proj(cams[j],Xr,u,v,z))continue;int cc=(int)std::lround(u),rr=(int)std::lround(v);if(cc<0||rr<0||cc>=W||rr>=H)continue;double d=depth[j][(size_t)rr*W+cc];if(!(d>0))continue;
   if(std::abs((z-d)/d)>MDE)continue;double du=u-cc,dv=v-rr;if(du*du+dv*dv>MRE2)continue;double N[3];nworld(j,rr,cc,N);if(Nr[0]*N[0]+Nr[1]*N[1]+Nr[2]*N[2]<MCN)continue;a2++;}
  // COLMAP traversal
  struct Q{int im,row,col,t;};std::vector<Q> q;q.push_back({im0,r0,c0,0});std::unordered_set<long long> vis;int cnt=0;
  while(!q.empty()&&cnt<MINP){Q e=q.back();q.pop_back();long long key=(long long)e.im*W*H+(long long)e.row*W+e.col;if(vis.count(key))continue;double d=depth[e.im][(size_t)e.row*W+e.col];if(!(d>0))continue;
   if(e.t>0){double u,v,z;if(!proj(cams[e.im],Xr,u,v,z))continue;if(std::abs((z-d)/d)>MDE)continue;double du=u-e.col,dv=v-e.row;if(du*du+dv*dv>MRE2)continue;double N[3];nworld(e.im,e.row,e.col,N);if(Nr[0]*N[0]+Nr[1]*N[1]+Nr[2]*N[2]<MCN)continue;}
   vis.insert(key);cnt++;double X[3];pix3d(e.im,e.row,e.col,d,X);int nt=e.t+1;if(nt>=MAXT)continue;
   for(int j:ovl[e.im]){double u,v,z;if(!proj(cams[j],X,u,v,z))continue;int cc=(int)std::lround(u),rr=(int)std::lround(v);if(cc<0||rr<0||cc>=W||rr>=H)continue;q.push_back({j,rr,cc,nt});}}
  out[3*s]=cnt>=MINP;out[3*s+1]=cnt;out[3*s+2]=a2;}
 std::ofstream f(argv[7],std::ios::binary);f.write((char*)out.data(),out.size()*4);return 0;}
int main(int argc,char**argv){try{std::string m=argc>1?argv[1]:"";if(m=="vis"&&argc==8)return vis(argc,argv);if(m=="fuse"&&argc==8)return fuse(argc,argv);std::cerr<<"usage\n";return 2;}
 catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
