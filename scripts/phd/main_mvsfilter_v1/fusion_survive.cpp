// PHD-MAIN-MVSFILTER-v1 방법 A: 융합 점(.ply + .vis)을 그 점을 만든 영상마다 투영해, 가장 가까운 화소(반올림, COLMAP 융합과 같은 화소 규약)의
// 깊이가 융합 점 깊이와 상대 tol 안이면 그 화소를 살아남은 것으로 표시한다. 학습 없음, CPU.
// 사용: fusion_survive <ply> <vis> <cams.bin> <depth_list.txt> <W> <H> <fx> <fy> <cx> <cy> <tol> <out_mask.u8> <out_stats.txt> <sample_every> <out_sample.bin>
//  cams.bin: 영상마다 (모형 차례) R 9 double + t 3 double (세계->카메라). depth_list: 모형 차례의 깊이 지도 경로(없으면 '-').
//  out_mask: 영상(모형 차례) x H x W 바이트(0/1). out_sample: (점 번호 u32, 영상 u32, 행 u32, 열 u32, x y z float) 레코드.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using namespace std;
static vector<float> read_depth(const string& p, int W, int H) {
  vector<float> z;
  if (p == "-") return z;
  ifstream f(p, ios::binary); if (!f) { cerr << "missing " << p << endl; exit(3); }
  string head; int amp = 0; char c;
  while (amp < 3 && f.get(c)) { head += c; if (c == '&') amp++; }
  int w, h, ch; sscanf(head.c_str(), "%d&%d&%d&", &w, &h, &ch);
  if (w != W || h != H || ch != 1) { cerr << "bad size " << p << endl; exit(4); }
  z.resize((size_t)w * h); f.read((char*)z.data(), z.size() * 4);   // row-major: z[row*w+col]
  return z;
}
int main(int argc, char** argv) {
  if (argc != 16) { cerr << "args" << endl; return 2; }
  string ply = argv[1], vis = argv[2], camf = argv[3], lst = argv[4];
  int W = atoi(argv[5]), H = atoi(argv[6]); double fx = atof(argv[7]), fy = atof(argv[8]), cx = atof(argv[9]), cy = atof(argv[10]), tol = atof(argv[11]);
  string outm = argv[12], outs = argv[13]; long every = atol(argv[14]); string outsm = argv[15];
  vector<string> paths; { ifstream f(lst); string s; while (getline(f, s)) paths.push_back(s); }
  size_t NI = paths.size(); vector<double> cam(NI * 12);
  { ifstream f(camf, ios::binary); f.read((char*)cam.data(), cam.size() * 8); if (!f) { cerr << "cams" << endl; return 5; } }
  vector<vector<float>> Z(NI); for (size_t i = 0; i < NI; i++) Z[i] = read_depth(paths[i], W, H);
  cerr << "depth loaded " << NI << endl;
  // ply header
  ifstream fp(ply, ios::binary); string line; long np_ = 0; int rec = 0, ox = -1; bool inv = false;
  while (getline(fp, line)) {
    if (line.rfind("element vertex", 0) == 0) { np_ = atol(line.substr(15).c_str()); inv = true; }
    else if (line.rfind("element", 0) == 0) inv = false;
    else if (line.rfind("property", 0) == 0 && inv) {
      istringstream ss(line); string a, t, n; ss >> a >> t >> n; int sz = (t == "float" || t == "float32" || t == "int" || t == "uint") ? 4 : (t == "double" ? 8 : (t == "uchar" || t == "uint8" ? 1 : (t == "short" || t == "ushort" ? 2 : -1)));
      if (sz < 0) { cerr << "type " << t << endl; return 6; }
      if (n == "x") { if (t != "float" && t != "float32") { cerr << "x not float" << endl; return 7; } ox = rec; }
      rec += sz;
    } else if (line == "end_header") break;
  }
  ifstream fv(vis, ios::binary); uint64_t nv; fv.read((char*)&nv, 8);
  if ((long)nv != np_) { cerr << "vis count " << nv << " vs " << np_ << endl; return 8; }
  vector<uint8_t> mask(NI * (size_t)W * H, 0);
  FILE* fs = fopen(outsm.c_str(), "wb");
  vector<char> buf(rec); uint64_t entries = 0, inside = 0, matched = 0, nodepth = 0, pts_with_match = 0; vector<uint64_t> hist(8, 0);
  for (long k = 0; k < np_; k++) {
    fp.read(buf.data(), rec); float X[3]; memcpy(X, buf.data() + ox, 12);
    uint32_t n; fv.read((char*)&n, 4); vector<uint32_t> ids(n); fv.read((char*)ids.data(), 4 * n);
    int got = 0;
    for (uint32_t j = 0; j < n; j++) {
      uint32_t im = ids[j]; entries++; if (im >= NI) { cerr << "image index " << im << endl; return 9; }
      const double* c = &cam[im * 12]; double q[3];
      for (int a = 0; a < 3; a++) q[a] = c[3 * a] * X[0] + c[3 * a + 1] * X[1] + c[3 * a + 2] * X[2] + c[9 + a];
      if (q[2] <= 0) continue;
      long col = lround(fx * q[0] / q[2] + cx), row = lround(fy * q[1] / q[2] + cy);
      if (col < 0 || col >= W || row < 0 || row >= H) continue;
      inside++; if (Z[im].empty()) { nodepth++; continue; }
      float d = Z[im][(size_t)row * W + col];
      if (!(d > 0)) { nodepth++; continue; }
      if (fabs(d - q[2]) <= tol * q[2]) {
        matched++; got++; mask[(size_t)im * W * H + (size_t)row * W + col] = 1;
        if (every > 0 && k % every == 0) { uint32_t r4[4] = {(uint32_t)k, im, (uint32_t)row, (uint32_t)col}; fwrite(r4, 4, 4, fs); fwrite(X, 4, 3, fs); }
      }
    }
    if (got) pts_with_match++; hist[min(got, 7)]++;
    if (k % 20000000 == 0) cerr << "points " << k << " / " << np_ << endl;
  }
  fclose(fs);
  { ofstream f(outm, ios::binary); f.write((char*)mask.data(), mask.size()); }
  ofstream so(outs); so << "points " << np_ << "\nvis_entries " << entries << "\ninside " << inside << "\nno_depth " << nodepth << "\nmatched " << matched << "\npoints_with_match " << pts_with_match << "\nhist_matched_per_point";
  for (auto h : hist) so << " " << h; so << "\n";
  return 0;
}
