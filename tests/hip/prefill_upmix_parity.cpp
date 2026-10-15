// HC upmix against independent FP64 dot products and explicit sigmoid/mix.
// Run in separate processes with STRATA_HC_UPMIX_ROLL=0 and =1: the launch choice is cached.
#include <hip/hip_runtime.h>
#include <hip/hip_fp16.h>
#include "strata/kernels/bf16_bits.hpp"
#include "strata/kernels/gfx_arch.hpp"
#include "strata/prefill/kernels.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

#define CHECK(call) do { const auto e = (call); if (e != hipSuccess) { \
    std::fprintf(stderr, "%s: %s\n", #call, hipGetErrorString(e)); std::exit(2); } } while (0)
struct Buffer {
    void* p = nullptr;
    explicit Buffer(size_t bytes) { CHECK(hipMalloc(&p, bytes)); }
    ~Buffer() { if (p) (void) hipFree(p); }
};
float wide(uint16_t x) {
    const uint32_t u = static_cast<uint32_t>(x) << 16;
    float f; std::memcpy(&f, &u, 4); return f;
}
bool run(int T, bool images) {
    constexpr int N = 2560, HC = 4, D = HC * N, K = 320, guard = 16;
    std::mt19937 rng(20261015 + T);
    std::uniform_real_distribution<float> dist(-1.f, 1.f);
    std::vector<uint16_t> a(T * K), w(D * K);
    std::vector<float> r(T * D), rs(T * HC), norm(D);
    for (auto& x : a) x = strata::kernels::bf16_from_f32(dist(rng));
    for (auto& x : w) x = strata::kernels::bf16_from_f32(.025f * dist(rng));
    for (auto& x : r) x = dist(rng);
    for (auto& x : rs) x = 1.f + .1f * dist(rng);
    for (auto& x : norm) x = 1.f + .1f * dist(rng);
    const size_t size = (size_t) T * N;
    std::vector<float> out(size + 2 * guard, -777.25f);
    std::vector<uint16_t> b16(out.size(), 0x5a5a), h16(out.size(), 0xa5a5);
    Buffer da(a.size()*2), dw(w.size()*2), dr(r.size()*4), ds(rs.size()*4), dn(norm.size()*4),
           dy(out.size()*4), db(b16.size()*2), dh(h16.size()*2);
    CHECK(hipMemcpy(da.p,a.data(),a.size()*2,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(dw.p,w.data(),w.size()*2,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(dr.p,r.data(),r.size()*4,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(ds.p,rs.data(),rs.size()*4,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(dn.p,norm.data(),norm.size()*4,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(dy.p,out.data(),out.size()*4,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(db.p,b16.data(),b16.size()*2,hipMemcpyHostToDevice));
    CHECK(hipMemcpy(dh.p,h16.data(),h16.size()*2,hipMemcpyHostToDevice));
    if (!strata::prefill::gr_upmix((uint16_t*)da.p,(uint16_t*)dw.p,(float*)dr.p,(float*)ds.p,(float*)dn.p,
                                 (float*)dy.p+guard,images?(uint16_t*)db.p+guard:nullptr,
                                 images?(uint16_t*)dh.p+guard:nullptr,T,nullptr)) return false;
    CHECK(hipDeviceSynchronize());
    CHECK(hipMemcpy(out.data(),dy.p,out.size()*4,hipMemcpyDeviceToHost));
    CHECK(hipMemcpy(b16.data(),db.p,b16.size()*2,hipMemcpyDeviceToHost));
    CHECK(hipMemcpy(h16.data(),dh.p,h16.size()*2,hipMemcpyDeviceToHost));
    bool ok = true;
    for (size_t i=0;i<out.size();++i) {
        const bool active = i >= guard && i < guard + size;
        if (!active) ok = ok && out[i] == -777.25f;
        else ok = ok && std::isfinite(out[i]);
        if (active && images) {
            const __half h = __float2half_rn(out[i]); uint16_t bits; std::memcpy(&bits,&h,2);
            ok = ok && b16[i] == strata::kernels::bf16_from_f32(out[i]) && h16[i] == bits;
        } else ok = ok && b16[i] == 0x5a5a && h16[i] == 0xa5a5;
    }
    double maximum = 0;
    // All columns, with rows on both sides of each 16/128-token tile boundary.
    for (int t=0;t<T;++t) {
        if (T > 17 && t != 0 && t != 1 && t != 15 && t != 16 && t != 64 && t != 127 && t != T-1) continue;
        for (int d=0;d<N;++d) {
            double ref = 0;
            for (int c=0;c<HC;++c) {
                double dot = 0;
                for (int k=0;k<K;++k) dot += (double)wide(a[t*K+k])*wide(w[(c*N+d)*K+k]);
                const double x = (double)r[t*D+c*N+d]*rs[t*HC+c]*norm[c*N+d];
                ref += x / (1.0 + std::exp(-dot));
            }
            maximum = std::max(maximum,std::abs(out[guard+t*N+d]-ref/HC));
        }
    }
    ok = ok && maximum < 2e-6;
    std::printf("T %d, images %d: max abs error %.3g, guards/images %s\n",T,images,maximum,ok?"PASS":"FAIL");
    return ok;
}
int main() {
    hipDeviceProp_t p{}; int dev = 0;
    CHECK(hipGetDevice(&dev)); CHECK(hipGetDeviceProperties(&p,dev));
    if (!strata::kernels::gfx_arch_is_gfx11_wmma(p.gcnArchName)) {
        std::printf("SKIP: %s is not gfx11 WMMA\n",p.gcnArchName); return 77;
    }
    strata::prefill::set_act_f16(false);
    if (strata::prefill::gr_upmix(nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,0,nullptr)) return 1;
    bool ok = true;
    for (int t : {1,17,129}) ok = run(t,true) && ok;
    ok = run(17,false) && ok;
    return ok ? 0 : 1;
}
