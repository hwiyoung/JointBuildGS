// PHD-MAIN-MVSFILTER-v1 방법 B: Wolff 외 2016 (3DV) 식 1~10 을 깊이 지도의 모든 화소 점에 적용. 학습 없음, CPU(OpenMP). 참값 읽지 않음.
// 점 p (원래 영상 s 의 화소) 마다 다른 깊이 지도 i 의 면(화소 격자를 두 삼각형으로 나눈 삼각망, 꼭짓점 셋이 유효하고 가장 작은 내각 >= 1°)과
// p 의 시선 교차점 깊이 Z_i(p) (1/z 무게중심 보간 = 3차원 삼각형과 광선의 정확한 교차) 를 구해 d_i = Z_i - z.
//  G = [-σ < d_i], 무게 w_i = n(p)·(V_i - p)/|V_i - p| (n 은 영상 공간 3x3 이웃 PCA, 카메라 쪽), 시선 방향 V_j·V_s > 0 인 깊이 지도만.
//  d(p) = Σ G w min(d_i, σ) / Σ G w (p 자신: d = 0 포함), v(p) = Σ [-σ < d_i < σ] (p 자신 포함), p(p) = 그 시점들 색(0~1)의 표준 편차(식 7).
//  남김: -t_d < d < 0, p < t_p, v > t_v. σ = 원래 영상 s 의 (depth_max - depth_min) x 0.01.
// 사용: wolff <n> <W> <H> <fx> <fy> <cx> <cy> <depth_list> <colors.u8> <cams.bin> <sigma.f64> <td_ratio> <tp> <tv_orig> <out_flags.u8> <out_stats.txt> <threads>
// flags: bit0 거리 조건, bit1 색 조건, bit2 v > t_v(원문), bit3 v > t_v(시점: ceil(0.075 x 화면 안 영상 수), 최소 2), bit4 법선 없음, bit7 유효 화소
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <omp.h>
using namespace std;
static int W, H; static double fx, fy, cx, cy;
static vector<float> read_depth(const string& p) {
  vector<float> z;
  ifstream f(p, ios::binary); if (!f) return z;
  string head; int amp = 0; char c; while (amp < 3 && f.get(c)) { head += c; if (c == '&') amp++; }
  int w, h, ch; sscanf(head.c_str(), "%d&%d&%d&", &w, &h, &ch); if (w != W || h != H || ch != 1) { cerr << "size " << p << endl; exit(4); }
  z.resize((size_t)w * h); f.read((char*)z.data(), z.size() * 4); return z;
}
static void jacobi_min(double A[3][3], double out[3]) {  // 3x3 대칭 행렬의 가장 작은 고유값 벡터
  double V[3][3] = {{1,0,0},{0,1,0},{0,0,1}};
  for (int sweep = 0; sweep < 12; sweep++) {
    double off = fabs(A[0][1]) + fabs(A[0][2]) + fabs(A[1][2]); if (off < 1e-14) break;
    for (int p = 0; p < 2; p++) for (int q = p + 1; q < 3; q++) {
      if (fabs(A[p][q]) < 1e-18) continue;
      double th = (A[q][q] - A[p][p]) / (2 * A[p][q]); double t = (th >= 0 ? 1 : -1) / (fabs(th) + sqrt(th * th + 1)); double c = 1 / sqrt(t * t + 1), s = t * c;
      for (int k = 0; k < 3; k++) { double akp = A[k][p], akq = A[k][q]; A[k][p] = c * akp - s * akq; A[k][q] = s * akp + c * akq; }
      for (int k = 0; k < 3; k++) { double apk = A[p][k], aqk = A[q][k]; A[p][k] = c * apk - s * aqk; A[q][k] = s * apk + c * aqk; }
      for (int k = 0; k < 3; k++) { double vkp = V[k][p], vkq = V[k][q]; V[k][p] = c * vkp - s * vkq; V[k][q] = s * vkp + c * vkq; }
    }
  }
  int m = 0; for (int k = 1; k < 3; k++) if (A[k][k] < A[m][m]) m = k;
  for (int k = 0; k < 3; k++) out[k] = V[k][m];
}
static inline double min_angle_deg(const double* a, const double* b, const double* c) {
  auto ang = [](const double* p, const double* q, const double* r) { double u[3], v[3]; for (int k = 0; k < 3; k++) { u[k] = q[k] - p[k]; v[k] = r[k] - p[k]; }
    double nu = sqrt(u[0]*u[0]+u[1]*u[1]+u[2]*u[2]), nv = sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]); if (nu == 0 || nv == 0) return 0.0;
    double cs = (u[0]*v[0]+u[1]*v[1]+u[2]*v[2]) / (nu * nv); cs = max(-1.0, min(1.0, cs)); return acos(cs) * 180 / M_PI; };
  return min(ang(a, b, c), min(ang(b, c, a), ang(c, a, b)));
}
int main(int argc, char** argv) {
  if (argc != 18) { cerr << "args" << endl; return 2; }
  int n = atoi(argv[1]); W = atoi(argv[2]); H = atoi(argv[3]); fx = atof(argv[4]); fy = atof(argv[5]); cx = atof(argv[6]); cy = atof(argv[7]);
  string lst = argv[8], colf = argv[9], camf = argv[10], sigf = argv[11]; double tdr = atof(argv[12]), tp = atof(argv[13]), tvo = atof(argv[14]);
  string outf = argv[15], stf = argv[16]; int threads = atoi(argv[17]); omp_set_num_threads(threads);
  vector<string> paths; { ifstream f(lst); string s; while (getline(f, s)) paths.push_back(s); }
  if ((int)paths.size() != n) { cerr << "list" << endl; return 3; }
  vector<vector<float>> Z(n);
  #pragma omp parallel for schedule(dynamic)
  for (int i = 0; i < n; i++) Z[i] = read_depth(paths[i]);
  size_t P = (size_t)W * H; vector<uint8_t> col(P * 3 * n); { ifstream f(colf, ios::binary); f.read((char*)col.data(), col.size()); if (!f) { cerr << "colors" << endl; return 5; } }
  vector<double> cam(n * 12), sig(n); { ifstream f(camf, ios::binary); f.read((char*)cam.data(), cam.size() * 8); } { ifstream f(sigf, ios::binary); f.read((char*)sig.data(), sig.size() * 8); }
  vector<double> C(n * 3), Vd(n * 3);  // 카메라 중심, 광축 방향 (세계)
  for (int i = 0; i < n; i++) { const double* R = &cam[i * 12]; const double* t = R + 9;
    for (int a = 0; a < 3; a++) { C[i*3+a] = -(R[0*3+a]*t[0] + R[1*3+a]*t[1] + R[2*3+a]*t[2]); Vd[i*3+a] = R[2*3+a]; } }
  vector<uint8_t> flags(P * n, 0); vector<string> stat(n);
  cerr << "loaded" << endl;
  #pragma omp parallel for schedule(dynamic)
  for (int s = 0; s < n; s++) {
    const vector<float>& zs = Z[s]; if (zs.empty()) continue;
    const double* Rs = &cam[s * 12]; const double* ts = Rs + 9; double sg = sig[s], td = tdr * sg;
    vector<int> idx; for (size_t q = 0; q < P; q++) if (zs[q] > 0 && isfinite(zs[q])) idx.push_back((int)q);
    size_t m = idx.size(); vector<double> X(m * 3), Nn(m * 3, 0); vector<uint8_t> hasn(m, 0);
    vector<double> camp(P * 3, NAN);
    for (size_t k = 0; k < m; k++) { int q = idx[k], r = q / W, c = q % W; double z = zs[q]; camp[q*3] = (c - cx) / fx * z; camp[q*3+1] = (r - cy) / fy * z; camp[q*3+2] = z; }
    for (size_t k = 0; k < m; k++) {
      int q = idx[k], r = q / W, c = q % W; const double* pc = &camp[q * 3];
      double w[3]; for (int a = 0; a < 3; a++) w[a] = pc[a] - ts[a];
      for (int a = 0; a < 3; a++) X[k*3+a] = Rs[0*3+a]*w[0] + Rs[1*3+a]*w[1] + Rs[2*3+a]*w[2];
      double mu[3] = {0,0,0}; int cnt = 0; double pts[9][3];
      for (int dr = -1; dr <= 1; dr++) for (int dc = -1; dc <= 1; dc++) { int rr = r + dr, cc = c + dc; if (rr < 0 || rr >= H || cc < 0 || cc >= W) continue; size_t qq = (size_t)rr * W + cc;
        if (!(zs[qq] > 0)) continue; for (int a = 0; a < 3; a++) { pts[cnt][a] = camp[qq*3+a]; mu[a] += camp[qq*3+a]; } cnt++; }
      if (cnt >= 3) {
        for (int a = 0; a < 3; a++) mu[a] /= cnt; double A[3][3] = {{0,0,0},{0,0,0},{0,0,0}};
        for (int i = 0; i < cnt; i++) for (int a = 0; a < 3; a++) for (int b = 0; b < 3; b++) A[a][b] += (pts[i][a]-mu[a])*(pts[i][b]-mu[b]);
        double tr = A[0][0] + A[1][1] + A[2][2]; double nc[3];
        if (tr > 0) { jacobi_min(A, nc); if (nc[0]*pc[0] + nc[1]*pc[1] + nc[2]*pc[2] > 0) for (int a = 0; a < 3; a++) nc[a] = -nc[a];   // 카메라(원점) 쪽
          for (int a = 0; a < 3; a++) Nn[k*3+a] = Rs[a*3+0]*0 + (Rs[0*3+a]*nc[0] + Rs[1*3+a]*nc[1] + Rs[2*3+a]*nc[2]); hasn[k] = 1; }
      }
    }
    vector<float> sw(m, 0), swd(m, 0), csum(m * 3, 0), csq(m, 0); vector<uint16_t> v(m, 1), nin(m, 1);
    for (size_t k = 0; k < m; k++) {  // p 자신
      double cw = 1; if (hasn[k]) { double dv[3], nd = 0; for (int a = 0; a < 3; a++) { dv[a] = C[s*3+a] - X[k*3+a]; nd += dv[a]*dv[a]; } nd = sqrt(nd); cw = (Nn[k*3]*dv[0]+Nn[k*3+1]*dv[1]+Nn[k*3+2]*dv[2]) / nd; if (cw <= 0) cw = 1e-6; }
      sw[k] = cw; int q = idx[k]; float cc = 0; for (int a = 0; a < 3; a++) { float x = col[(size_t)s*P*3 + (size_t)q*3 + a] / 255.f; csum[k*3+a] = x; cc += x*x; } csq[k] = cc;
    }
    // 겹치는 깊이 지도 고르기: 광축 방향 > 0 이고 표본 점이 화면 안에 드는 것
    for (int j = 0; j < n; j++) {
      if (j == s || Z[j].empty()) continue;
      if (Vd[j*3]*Vd[s*3] + Vd[j*3+1]*Vd[s*3+1] + Vd[j*3+2]*Vd[s*3+2] <= 0) continue;
      const double* Rj = &cam[j * 12]; const double* tj = Rj + 9; bool any = false;
      for (size_t k = 0; k < m && !any; k += 37) { const double* x = &X[k*3]; double Q[3]; for (int a = 0; a < 3; a++) Q[a] = Rj[a*3]*x[0]+Rj[a*3+1]*x[1]+Rj[a*3+2]*x[2]+tj[a];
        if (Q[2] <= 0) continue; double u = fx*Q[0]/Q[2]+cx, vv = fy*Q[1]/Q[2]+cy; if (u >= -1 && u <= W && vv >= -1 && vv <= H) any = true; }
      if (!any) continue;
      const vector<float>& zj = Z[j]; const uint8_t* cj = &col[(size_t)j*P*3];
      for (size_t k = 0; k < m; k++) {
        const double* x = &X[k*3]; double Q[3]; for (int a = 0; a < 3; a++) Q[a] = Rj[a*3]*x[0]+Rj[a*3+1]*x[1]+Rj[a*3+2]*x[2]+tj[a];
        if (Q[2] <= 0) continue; double u = fx*Q[0]/Q[2]+cx, vv = fy*Q[1]/Q[2]+cy;
        if (!(u >= 0 && u <= W - 1 && vv >= 0 && vv <= H - 1)) continue;
        nin[k]++;
        int c0 = min((int)floor(u), W - 2), r0 = min((int)floor(vv), H - 2); double fu = u - c0, fv = vv - r0;
        int qa = r0*W + c0, qb, qc = (r0+1)*W + c0 + 1; double wa, wb, wc; int cb_, rb_;
        if (fu >= fv) { qb = r0*W + c0 + 1; cb_ = c0 + 1; rb_ = r0; wa = 1 - fu; wb = fu - fv; wc = fv; } else { qb = (r0+1)*W + c0; cb_ = c0; rb_ = r0 + 1; wa = 1 - fv; wb = fv - fu; wc = fu; }
        float za = zj[qa], zb = zj[qb], zc = zj[qc]; if (!(za > 0 && zb > 0 && zc > 0)) continue;
        double A3[3] = {(c0 - cx)/fx*za, (r0 - cy)/fy*za, za}, B3[3] = {(cb_ - cx)/fx*zb, (rb_ - cy)/fy*zb, zb}, C3[3] = {(c0+1 - cx)/fx*zc, (r0+1 - cy)/fy*zc, zc};
        if (min_angle_deg(A3, B3, C3) < 1.0) continue;
        double Zi = 1.0 / (wa/za + wb/zb + wc/zc); double di = Zi - Q[2];
        if (di <= -sg) continue;
        double wgt = 1; if (hasn[k]) { double dv[3], nd = 0; for (int a = 0; a < 3; a++) { dv[a] = C[j*3+a] - x[a]; nd += dv[a]*dv[a]; } nd = sqrt(nd); wgt = (Nn[k*3]*dv[0]+Nn[k*3+1]*dv[1]+Nn[k*3+2]*dv[2]) / nd; }
        if (wgt <= 0) continue;
        sw[k] += wgt; swd[k] += wgt * min(di, sg);
        if (di < sg) {
          v[k]++; int u0 = min((int)floor(u), W - 2), v0 = min((int)floor(vv), H - 2); double au = u - u0, av = vv - v0; float cc = 0;
          for (int a = 0; a < 3; a++) { double x00 = cj[((size_t)v0*W+u0)*3+a], x10 = cj[((size_t)v0*W+u0+1)*3+a], x01 = cj[((size_t)(v0+1)*W+u0)*3+a], x11 = cj[((size_t)(v0+1)*W+u0+1)*3+a];
            float xc = (float)(((1-au)*(1-av)*x00 + au*(1-av)*x10 + (1-au)*av*x01 + au*av*x11) / 255.0); csum[k*3+a] += xc; cc += xc*xc; }
          csq[k] += cc;
        }
      }
    }
    long c_d = 0, c_p = 0, c_vo = 0, c_vv = 0, k_o = 0, k_v = 0, non = 0; vector<int> vs(m), ns(m);
    for (size_t k = 0; k < m; k++) {
      double dp = swd[k] / sw[k]; double vk = v[k]; double s2 = 0; for (int a = 0; a < 3; a++) s2 += csum[k*3+a]*csum[k*3+a];
      double var = csq[k] / vk - s2 / (vk * vk); double pp = sqrt(max(0.0, var));
      int tvv = max(2, (int)ceil(0.075 * nin[k]));
      uint8_t f = 128; if (dp > -td && dp < 0) { f |= 1; c_d++; } if (pp < tp) { f |= 2; c_p++; } if (vk > tvo) { f |= 4; c_vo++; } if (vk > tvv) { f |= 8; c_vv++; } if (!hasn[k]) { f |= 16; non++; }
      if ((f & 7) == 7) k_o++; if ((f & 11) == 11) k_v++;
      flags[(size_t)s*P + idx[k]] = f; vs[k] = v[k]; ns[k] = nin[k];
    }
    auto med = [](vector<int> a) { if (a.empty()) return 0; nth_element(a.begin(), a.begin() + a.size()/2, a.end()); return a[a.size()/2]; };
    char buf[400]; snprintf(buf, sizeof buf, "%d %zu %ld %ld %ld %ld %ld %ld %ld %d %d %.6f", s, m, c_d, c_p, c_vo, c_vv, k_o, k_v, non, med(vs), med(ns), sg); stat[s] = buf;
    if (s % 50 == 0) { _Pragma("omp critical") cerr << "image " << s << " valid " << m << " keep_orig " << k_o << " keep_view " << k_v << endl; }
  }
  { ofstream f(outf, ios::binary); f.write((char*)flags.data(), flags.size()); }
  ofstream so(stf); so << "image valid dist_ok photo_ok v_gt_tv_orig v_gt_tv_view keep_orig keep_view no_normal median_v median_in_frame sigma\n"; for (auto& s : stat) so << s << "\n";
  return 0;
}
