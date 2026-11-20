// PHD-MAIN-MVSFILTER-v1 덧붙임 1 방법 A2: 화소마다 일치 시점 수 (솎아내기 없음, 세션이 정한 판). 학습 없음, CPU(OpenMP). 참값 읽지 않음.
// 화소 p (영상 i, 기하 깊이 z, 기하 법선 n_i) → 세계 점 X. 다른 영상 j 마다 (X 가 j 화면 안이고 j 기하 깊이 지도의 그 화소(반올림) 값 zj > 0 일 때만 봄; m++):
//   δ = (zj − Zx)/Zx, Zx = X 의 j 카메라 깊이.
//   |δ| ≤ 1 %  이고  j 화소를 깊이 zj 로 세계로 옮겨 i 에 비춘 자리가 p 에서 2 화소 안  이고  n_i·n_j ≥ cos 10°  → 일치 c++
//   δ < −1 %  → 앞에 다른 면 o++ ;  δ > +1 %  → 지나쳐 봄 f++ ;  |δ| ≤ 1 % 인데 되비춤·법선 조건을 못 넘으면 셋 어디에도 넣지 않음(q 로 셈).
// c, m 은 자기 자신 포함(c ≥ 1, m ≥ 1). 값 1 %·2 화소·10° = COLMAP stereo_fusion 기본값(max_depth_error·max_reproj_error·max_normal_error).
// 화소 좌표 규약은 mfcommon.unproject / wolff.cpp 와 같음(정수 화소 = 중심, (c − cx)/fx).
// 사용: a2_count <n> <W> <H> <fx> <fy> <cx> <cy> <depth_list> <normal_list> <cams.bin> <out_prefix> <stats.txt> <threads> [<깊이 일치 문턱, 기본 0.01>]
// (회신 1, 11/20 23시: 문턱 인자와 qr·qn·qb 를 더함. 문턱 0.01 에서 c·f·o·m·q 는 앞 판과 같아야 함 — mf15 가 확인)
// 출력: <out_prefix>_{c,f,o,m,q,qr,qn,qb}.u16 (qr = 되비춤만 못 넘은 영상 수, qn = 법선만, qb = 둘 다) : n x H x W (행 우선), 깊이 없는 화소는 0.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <omp.h>
#include <fcntl.h>
#include <unistd.h>
using namespace std;
static int W, H; static double fx, fy, cx, cy;
static vector<float> read_map(const string& p, int ch) {
  vector<float> z; if (p == "-") return z;
  ifstream f(p, ios::binary); if (!f) return z;
  string head; int amp = 0; char c; while (amp < 3 && f.get(c)) { head += c; if (c == '&') amp++; }
  int w, h, cc; sscanf(head.c_str(), "%d&%d&%d&", &w, &h, &cc); if (w != W || h != H || cc != ch) { cerr << "size " << p << endl; exit(4); }
  z.resize((size_t)w * h * ch); f.read((char*)z.data(), z.size() * 4); return z;   // 채널마다 평면, 행 우선(mfcommon.read_bin 과 같음)
}
int main(int argc, char** argv) {
  if (argc != 14 && argc != 15) { cerr << "args" << endl; return 2; }
  int n = atoi(argv[1]); W = atoi(argv[2]); H = atoi(argv[3]); fx = atof(argv[4]); fy = atof(argv[5]); cx = atof(argv[6]); cy = atof(argv[7]);
  string dl = argv[8], nl = argv[9], camf = argv[10], outp = argv[11], stf = argv[12]; int threads = atoi(argv[13]); omp_set_num_threads(threads);
  const double TOL = argc == 15 ? atof(argv[14]) : 0.01, REPROJ = 2.0, COSN = cos(10.0 * M_PI / 180.0);
  vector<string> dp, np_; { ifstream f(dl); string s; while (getline(f, s)) dp.push_back(s); } { ifstream f(nl); string s; while (getline(f, s)) np_.push_back(s); }
  if ((int)dp.size() != n || (int)np_.size() != n) { cerr << "list" << endl; return 3; }
  vector<vector<float>> Z(n), NM(n);
  #pragma omp parallel for schedule(dynamic)
  for (int i = 0; i < n; i++) { Z[i] = read_map(dp[i], 1); if (!Z[i].empty()) { NM[i] = read_map(np_[i], 3); if (NM[i].empty()) { cerr << "normal missing " << np_[i] << endl; exit(6); } } }
  vector<double> cam(n * 12); { ifstream f(camf, ios::binary); f.read((char*)cam.data(), cam.size() * 8); if (!f) { cerr << "cams" << endl; return 5; } }
  vector<double> Vd(n * 3); for (int i = 0; i < n; i++) for (int a = 0; a < 3; a++) Vd[i*3+a] = cam[i*12 + 2*3 + a];
  size_t P = (size_t)W * H;
  const char* names[8] = {"c", "f", "o", "m", "q", "qr", "qn", "qb"}; int fds[8];
  for (int k = 0; k < 8; k++) { string p = outp + "_" + names[k] + ".u16"; fds[k] = open(p.c_str(), O_CREAT | O_TRUNC | O_WRONLY, 0644); if (fds[k] < 0 || ftruncate(fds[k], (off_t)(P * n * 2)) != 0) { cerr << "out" << endl; return 7; } }
  vector<string> stat(n);
  cerr << "loaded" << endl;
  #pragma omp parallel for schedule(dynamic)
  for (int s = 0; s < n; s++) {
    if (Z[s].empty()) continue;
    const vector<float>& zs = Z[s]; const vector<float>& ns = NM[s]; const double* Rs = &cam[s*12]; const double* ts = Rs + 9;
    vector<int> idx; for (size_t q = 0; q < P; q++) if (zs[q] > 0 && isfinite(zs[q])) idx.push_back((int)q);
    size_t m = idx.size(); vector<double> X(m * 3), Nw(m * 3);
    for (size_t k = 0; k < m; k++) {
      int q = idx[k], r = q / W, c = q % W; double z = zs[q]; double pc[3] = {(c - cx) / fx * z, (r - cy) / fy * z, z}; double w[3];
      for (int a = 0; a < 3; a++) w[a] = pc[a] - ts[a];
      for (int a = 0; a < 3; a++) X[k*3+a] = Rs[0*3+a]*w[0] + Rs[1*3+a]*w[1] + Rs[2*3+a]*w[2];
      double nc[3] = {ns[q], ns[P + q], ns[2*P + q]};
      for (int a = 0; a < 3; a++) Nw[k*3+a] = Rs[0*3+a]*nc[0] + Rs[1*3+a]*nc[1] + Rs[2*3+a]*nc[2];
    }
    vector<uint16_t> C(m, 1), F(m, 0), Oc(m, 0), M(m, 1), Q(m, 0), QR(m, 0), QN(m, 0), QB(m, 0);
    for (int j = 0; j < n; j++) {
      if (j == s || Z[j].empty()) continue;
      const double* Rj = &cam[j*12]; const double* tj = Rj + 9; bool any = false;
      for (size_t k = 0; k < m && !any; k += 7) { const double* x = &X[k*3]; double Qj[3]; for (int a = 0; a < 3; a++) Qj[a] = Rj[a*3]*x[0]+Rj[a*3+1]*x[1]+Rj[a*3+2]*x[2]+tj[a];
        if (Qj[2] <= 0) continue; double u = fx*Qj[0]/Qj[2]+cx, vv = fy*Qj[1]/Qj[2]+cy; if (u >= -1 && u <= W && vv >= -1 && vv <= H) any = true; }
      if (!any) continue;   // 표본 점(7 개마다 하나)이 하나도 화면 안에 들지 않는 영상은 건너뜀 (wolff.cpp 와 같은 고르기)
      const vector<float>& zj = Z[j]; const vector<float>& nj = NM[j];
      for (size_t k = 0; k < m; k++) {
        const double* x = &X[k*3]; double Qj[3]; for (int a = 0; a < 3; a++) Qj[a] = Rj[a*3]*x[0]+Rj[a*3+1]*x[1]+Rj[a*3+2]*x[2]+tj[a];
        if (Qj[2] <= 0) continue; double u = fx*Qj[0]/Qj[2]+cx, vv = fy*Qj[1]/Qj[2]+cy;
        int cc = (int)lround(u), rr = (int)lround(vv); if (cc < 0 || cc >= W || rr < 0 || rr >= H) continue;
        size_t qj = (size_t)rr * W + cc; float d = zj[qj]; if (!(d > 0 && isfinite(d))) continue;
        M[k]++; double del = (d - Qj[2]) / Qj[2];
        if (del < -TOL) { Oc[k]++; continue; }
        if (del > TOL) { F[k]++; continue; }
        // 되비춤: j 화소(cc, rr) 를 깊이 d 로 세계 → i 에 투영
        double pj[3] = {(cc - cx) / fx * d, (rr - cy) / fy * d, d}, w[3], Y[3], Qi[3];
        for (int a = 0; a < 3; a++) w[a] = pj[a] - tj[a];
        for (int a = 0; a < 3; a++) Y[a] = Rj[0*3+a]*w[0] + Rj[1*3+a]*w[1] + Rj[2*3+a]*w[2];
        for (int a = 0; a < 3; a++) Qi[a] = Rs[a*3]*Y[0]+Rs[a*3+1]*Y[1]+Rs[a*3+2]*Y[2]+ts[a];
        bool rp = Qi[2] > 0;   // 되비춤 조건
        if (rp) { int q = idx[k]; double du = fx*Qi[0]/Qi[2]+cx - (q % W), dv = fy*Qi[1]/Qi[2]+cy - (q / W); rp = du*du + dv*dv <= REPROJ*REPROJ; }
        bool nk;               // 법선 조건 (회신 1: 되비춤과 따로 셈; c 는 둘 다 맞을 때만 — 앞 판과 같은 값)
        { double ncj[3] = {nj[qj], nj[P + qj], nj[2*P + qj]}, nw[3]; for (int a = 0; a < 3; a++) nw[a] = Rj[0*3+a]*ncj[0] + Rj[1*3+a]*ncj[1] + Rj[2*3+a]*ncj[2];
          double dd = nw[0]*Nw[k*3] + nw[1]*Nw[k*3+1] + nw[2]*Nw[k*3+2]; nk = dd >= COSN; }
        if (rp && nk) C[k]++; else { Q[k]++; if (!rp && nk) QR[k]++; else if (rp && !nk) QN[k]++; else QB[k]++; }
      }
    }
    vector<uint16_t> buf(P);
    vector<uint16_t>* arr[8] = {&C, &F, &Oc, &M, &Q, &QR, &QN, &QB};
    for (int a = 0; a < 8; a++) { fill(buf.begin(), buf.end(), 0); for (size_t k = 0; k < m; k++) buf[idx[k]] = (*arr[a])[k];
      if (pwrite(fds[a], buf.data(), P * 2, (off_t)((size_t)s * P * 2)) != (ssize_t)(P * 2)) { cerr << "write" << endl; exit(8); } }
    long c2 = 0, c5 = 0; vector<int> cv(m); for (size_t k = 0; k < m; k++) { c2 += C[k] >= 2; c5 += C[k] >= 5; cv[k] = C[k]; }
    int medc = 0; if (m) { nth_element(cv.begin(), cv.begin() + m/2, cv.end()); medc = cv[m/2]; }
    char b[200]; snprintf(b, sizeof b, "%d %zu %ld %ld %d", s, m, c2, c5, medc); stat[s] = b;
    if (s % 50 == 0) { _Pragma("omp critical") cerr << "image " << s << " valid " << m << " c>=2 " << c2 << " c>=5 " << c5 << endl; }
  }
  for (int k = 0; k < 8; k++) close(fds[k]);
  ofstream so(stf); so << "image valid c_ge2 c_ge5 median_c\n"; for (auto& s : stat) if (!s.empty()) so << s << "\n";
  return 0;
}
