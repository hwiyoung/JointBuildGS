// PHD-MAIN-JUDGEEVAL-v1 addendum 1 section 4: same step-2 classification as judgevis.cpp (included unchanged), counted separately by camera side.
// side: front = camera centre on the +n side of the patch plane (n . (C - s) > 0), back = the other side. delta 1 % only. No truth is read.
// usage: judgevis2 visside cams.bin maps.txt patches.bin NP out.bin   (patches as in judgevis vis; out per patch 8 doubles:
//        front unseen, pass, block, agree, back unseen, pass, block, agree  (pixel counts, same pixel test as vis))
#define main judgevis_main_unused
#include "judgevis.cpp"
#undef main
int visside(int argc,char**argv){load(argv[2],argv[3],false);size_t NP=std::stoull(argv[5]);std::vector<double> P(NP*10);{std::ifstream f(argv[4],std::ios::binary);f.read((char*)P.data(),P.size()*8);}
 std::vector<std::atomic<long>> cnt(NP*8);for(auto&a:cnt)a=0;
 #pragma omp parallel for schedule(dynamic,1)
 for(int im=0;im<NI;im++){const Cam&c=cams[im];const float*Dm=depth[im].data();double cw[3];{double z[3]={0,0,0};toworld(c,z,cw);}
  for(size_t p=0;p<NP;p++){const double*q=&P[p*10];double sc[3];tocam(c,q,sc);if(sc[2]<=0.05)continue;double uc=c.fx*sc[0]/sc[2]+c.cx,vc=c.fy*sc[1]/sc[2]+c.cy;
   if(uc<-50||vc<-50||uc>W+50||vc>H+50)continue;
   double n[3]={q[3],q[4],q[5]},u[3]={q[6],q[7],q[8]},v[3]={n[1]*u[2]-n[2]*u[1],n[2]*u[0]-n[0]*u[2],n[0]*u[1]-n[1]*u[0]};double h=q[9];
   int side=((cw[0]-q[0])*n[0]+(cw[1]-q[1])*n[1]+(cw[2]-q[2])*n[2])>0?0:1;
   double px[4],py[4];bool ok=true;const double sg[4][2]={{-1,-1},{1,-1},{1,1},{-1,1}};
   for(int k=0;k<4;k++){double X[3],Y[3];for(int r=0;r<3;r++)X[r]=q[r]+sg[k][0]*h*u[r]+sg[k][1]*h*v[r];tocam(c,X,Y);if(Y[2]<=0.05){ok=false;break;}px[k]=c.fx*Y[0]/Y[2]+c.cx;py[k]=c.fy*Y[1]/Y[2]+c.cy;}
   if(!ok)continue;
   double nc[3]={c.R[0]*n[0]+c.R[1]*n[1]+c.R[2]*n[2],c.R[3]*n[0]+c.R[4]*n[1]+c.R[5]*n[2],c.R[6]*n[0]+c.R[7]*n[1]+c.R[8]*n[2]};double rhs=nc[0]*sc[0]+nc[1]*sc[1]+nc[2]*sc[2];
   auto Zat=[&](double uu,double vv){double d[3]={(uu-c.cx)/c.fx,(vv-c.cy)/c.fy,1.};double den=nc[0]*d[0]+nc[1]*d[1]+nc[2]*d[2];if(std::abs(den)<1e-9)return -1.;return rhs/den;};
   int x0=std::max(0,(int)std::floor(std::min({px[0],px[1],px[2],px[3]}))),x1=std::min(W-1,(int)std::ceil(std::max({px[0],px[1],px[2],px[3]})));
   int y0=std::max(0,(int)std::floor(std::min({py[0],py[1],py[2],py[3]}))),y1=std::min(H-1,(int)std::ceil(std::max({py[0],py[1],py[2],py[3]})));
   double area=0;for(int k=0;k<4;k++){int k2=(k+1)%4;area+=px[k]*py[k2]-px[k2]*py[k];}double sgn=area>=0?1:-1;int c4[4]={0,0,0,0};
   for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){double X=x,Y=y;bool in=true;for(int k=0;k<4;k++){int k2=(k+1)%4;double cr=(px[k2]-px[k])*(Y-py[k])-(py[k2]-py[k])*(X-px[k]);if(cr*sgn<0){in=false;break;}}
    if(!in)continue;double Z=Zat(X,Y);if(!(Z>0))continue;c4[cls(Dm[(size_t)y*W+x],Z,0.01)]++;}
   for(int j=0;j<4;j++)if(c4[j])cnt[p*8+4*side+j]+=c4[j];}}
 std::vector<double> o(NP*8);for(size_t i=0;i<o.size();i++)o[i]=cnt[i];std::ofstream f(argv[6],std::ios::binary);f.write((char*)o.data(),o.size()*8);return 0;}
int main(int argc,char**argv){try{std::string m=argc>1?argv[1]:"";if(m=="visside"&&argc==7)return visside(argc,argv);std::cerr<<"usage\n";return 2;}
 catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
