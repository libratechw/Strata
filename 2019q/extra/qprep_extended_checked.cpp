// tests/hip/prefill_q_prep.cpp - the prompt path's q preparation as one kernel (q_prep, STRATA_QPREP=1) against the three
// kernels it replaces (split_q, rms_rows over the 24 q heads, rope): every float must be BITWISE equal, over chunk
// lengths around the block sizes, from a nonzero start position.  Synthetic q_full [T, 24, 512] (q | gate per head).
#include "strata/prefill/kernels.hpp"
#include "strata/kernels/mrope.hpp"
#include "strata/kernels/rope.hpp"

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

namespace {
void ck(cudaError_t e, const char* w) {
    if (e != cudaSuccess) { std::fprintf(stderr, "%s: %s\n", w, cudaGetErrorString(e)); std::exit(2); }
}
template <typename T> T* dev(const std::vector<T>& h) {
    T* d = nullptr;
    ck(cudaMalloc(&d, h.size() * sizeof(T)), "malloc");
    ck(cudaMemcpy(d, h.data(), h.size() * sizeof(T), cudaMemcpyHostToDevice), "upload");
    return d;
}
}  // namespace

int main() {
    namespace pf = strata::prefill;
    constexpr int HEADS = 24, DIM = 256;
    std::mt19937 rng(7);
    std::normal_distribution<float> nd(0.f, 3.f);
    std::uniform_real_distribution<float> ud(0.5f, 1.5f);
    const float eps = 1e-6f;
    setenv("STRATA_ROPE_TABLE", "1", 1);
    int failures = 0;
    for (int mode : {0, 1, 2})
    for (int table : {0, 1})
    for (int mr : {0, 1})
    for (const int64_t T : {1, 65, 513}) {
        for (const int64_t pos0 : {0, 8190}) {
            std::vector<float> full((size_t) T * HEADS * 2 * DIM), w(DIM);
            for (auto& x : full) x = nd(rng);
            for (auto& x : w) x = ud(rng);
            const float* dfull = dev(full);
            const float* dw = dev(w);
            float *q_ref = nullptr, *q_new = nullptr;
            const size_t n = (size_t) T * HEADS * DIM;
            ck(cudaMalloc(&q_ref, n * 4), "malloc");
            ck(cudaMalloc(&q_new, n * 4), "malloc");
            auto sc = strata::kernels::rope_scaling();
            if (mode == 1) { sc.type = strata::kernels::RopeScalingType::Linear; sc.factor = 4.0; sc.attn_factor = 1.1; }
            if (mode == 2) { sc.type = strata::kernels::RopeScalingType::YaRN; sc.factor = 4.0; sc.orig_ctx = 4096; sc.ext_factor = 1.0; sc.attn_factor = 1.15; }
            const float *dc = nullptr, *ds = nullptr;
            if (table) {
                std::vector<float> c(8192 * 32), sn(8192 * 32);
                strata::kernels::build_rope_table(64, sc, 8192, c.data(), sn.data());
                dc = dev(c); ds = dev(sn);
                strata::kernels::rope_table_set(dc, ds, 8192, sc);
            }
            const int32_t* dm = nullptr;
            if (mr) {
                std::vector<int32_t> mt((size_t) (pos0 + T + 1) * 3);
                for (size_t i = 0; i < mt.size() / 3; ++i) { mt[3*i] = (int32_t) (2*i+1); mt[3*i+1] = (int32_t) ((7*i)%1021); mt[3*i+2] = (int32_t) ((11*i)%2047); }
                dm = dev(mt); strata::kernels::mrope_table_set(dm);
            }
            const auto registered = strata::kernels::rope_table_for(sc);
            if ((table && (registered.cos != dc || registered.sin != ds || registered.max_pos != 8192)) ||
                (!table && registered.cos != nullptr) || strata::kernels::mrope_table() != dm) {
                std::fprintf(stderr, "requested table/MRoPE registration was not active\n"); return 2;
            }
            pf::split_q(dfull, q_ref, T, nullptr);
            pf::rms_rows(q_ref, dw, T * HEADS, DIM, DIM, eps, nullptr);
            pf::rope(q_ref, T, HEADS, DIM, HEADS * DIM, pos0, sc, nullptr);
            pf::q_prep(dfull, dw, q_new, T, eps, pos0, sc, nullptr);
            ck(cudaDeviceSynchronize(), "run");
            std::vector<float> a(n), b(n);
            ck(cudaMemcpy(a.data(), q_ref, n * 4, cudaMemcpyDeviceToHost), "download");
            ck(cudaMemcpy(b.data(), q_new, n * 4, cudaMemcpyDeviceToHost), "download");
            size_t diff = 0;
            for (size_t i = 0; i < n; ++i) diff += std::memcmp(&a[i], &b[i], 4) != 0;
            failures += diff != 0;
            std::printf("mode=%d table=%d mrope=%d ", mode, table, mr);
            std::printf("%s T %lld pos0 %lld: %zu of %zu values differ\n", diff ? "FAIL" : "PASS", (long long) T,
                        (long long) pos0, diff, n);
            strata::kernels::mrope_table_set(nullptr);
            if (dc) strata::kernels::rope_table_release(dc);
            cudaFree((void*) dc); cudaFree((void*) ds); cudaFree((void*) dm);
            cudaFree((void*) dfull); cudaFree((void*) dw); cudaFree(q_ref); cudaFree(q_new);
        }
    }
    std::printf("hip_prefill_q_prep: %s\n", failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
