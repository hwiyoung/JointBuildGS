// PHD-MAIN-FILL-v1 (tsdf_tiled.py 'order'): the iteration order of Open3D 0.19's ScalableTSDFVolume::volume_units_
// (std::unordered_map<Eigen::Vector3i, VolumeUnit, utility::hash_eigen<Eigen::Vector3i>>) after a given sequence of first insertions.
// ScalableTSDFVolume::ExtractTriangleMesh walks the units in this order, so it is the triangle order of the one-piece TSDF mesh.
//   umap_order <insertion sequence, int32 x y z per unit> <output, int32 x y z per unit in iteration order>
// Built with the image's g++ and run against the libstdc++ that Open3D loads (/opt/geogs/lib, LD_LIBRARY_PATH): the rehash policy
// (_Prime_rehash_policy::_M_need_rehash, _M_next_bkt) is taken from that library at run time, as in Open3D.
// Only keys, hash and insertion order decide the order; the mapped value is a stand-in of VolumeUnit. scientific_verdict: null.
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <unordered_map>
#include <vector>

struct Key {
    int v[3];
    bool operator==(const Key &o) const { return v[0] == o.v[0] && v[1] == o.v[1] && v[2] == o.v[2]; }
};

// = open3d::utility::hash_eigen<Eigen::Vector3i> (Open3D 0.19, cpp/open3d/utility/Helper.h); not noexcept, as there.
struct HashEigen {
    std::size_t operator()(Key const &matrix) const {
        size_t hash_seed = 0;
        for (int i = 0; i < 3; i++) {
            auto elem = matrix.v[i];
            hash_seed ^= std::hash<int>()(elem) + 0x9e3779b9 + (hash_seed << 6) + (hash_seed >> 2);
        }
        return hash_seed;
    }
};

// stand-in of ScalableTSDFVolume::VolumeUnit (a shared_ptr and an Eigen::Vector3i)
struct VolumeUnit {
    std::shared_ptr<int> volume_;
    int index_[3];
};

int main(int argc, char **argv) {
    if (argc != 3) {
        std::fprintf(stderr, "usage: umap_order <sequence.i32> <order.i32>\n");
        return 2;
    }
    std::FILE *f = std::fopen(argv[1], "rb");
    if (!f) return 3;
    std::vector<int32_t> buf;
    int32_t tmp[4096 * 3];
    size_t n;
    while ((n = std::fread(tmp, sizeof(int32_t), 4096 * 3, f)) > 0) buf.insert(buf.end(), tmp, tmp + n);
    std::fclose(f);
    if (buf.size() % 3) return 4;
    std::unordered_map<Key, VolumeUnit, HashEigen> volume_units_;
    size_t inserted = 0;
    for (size_t i = 0; i < buf.size(); i += 3) {
        Key k{{buf[i], buf[i + 1], buf[i + 2]}};
        size_t before = volume_units_.size();
        auto &unit = volume_units_[k];   // = ScalableTSDFVolume::OpenVolumeUnit: volume_units_[index]
        (void)unit;
        inserted += volume_units_.size() - before;
    }
    std::FILE *o = std::fopen(argv[2], "wb");
    if (!o) return 5;
    for (const auto &unit : volume_units_) std::fwrite(unit.first.v, sizeof(int32_t), 3, o);
    std::fclose(o);
    std::printf("{\"sequence\": %zu, \"inserted\": %zu, \"size\": %zu, \"bucket_count\": %zu}\n", buf.size() / 3, inserted,
                volume_units_.size(), volume_units_.bucket_count());
    return 0;
}
