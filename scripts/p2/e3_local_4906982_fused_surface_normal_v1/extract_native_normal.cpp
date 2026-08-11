#include <MVS.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>

namespace {

bool WriteNpyFloat32C3(const std::string& path, const cv::Mat& matrix) {
    if (matrix.type() != CV_32FC3 || !matrix.isContinuous()) {
        std::cerr << "expected continuous CV_32FC3 native normal map\n";
        return false;
    }
    std::ofstream output(path, std::ios::binary);
    if (!output) return false;
    const std::string magic("\x93NUMPY", 6);
    const unsigned char major = 1, minor = 0;
    std::string header = "{'descr': '<f4', 'fortran_order': False, 'shape': (" +
        std::to_string(matrix.rows) + ", " + std::to_string(matrix.cols) + ", 3), }";
    const std::size_t preamble = magic.size() + 2 + 2;
    const std::size_t padding = 16 - ((preamble + header.size() + 1) % 16);
    header.append(padding, ' ');
    header.push_back('\n');
    const std::uint16_t size = static_cast<std::uint16_t>(header.size());
    const unsigned char bytes[2] = {
        static_cast<unsigned char>(size & 0xff),
        static_cast<unsigned char>((size >> 8) & 0xff),
    };
    output.write(magic.data(), magic.size());
    output.put(static_cast<char>(major));
    output.put(static_cast<char>(minor));
    output.write(reinterpret_cast<const char*>(bytes), 2);
    output.write(header.data(), header.size());
    output.write(reinterpret_cast<const char*>(matrix.ptr<float>(0)),
                 static_cast<std::streamsize>(matrix.total() * 3 * sizeof(float)));
    return output.good();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: extract_native_normal input.dmap output.npy\n";
        return 2;
    }
    MVS::DepthData data;
    if (!data.Load(argv[1])) {
        std::cerr << "failed to load " << argv[1] << "\n";
        return 1;
    }
    if (data.normalMap.empty()) {
        std::cerr << "DMAP has no native normal map: " << argv[1] << "\n";
        return 3;
    }
    if (!WriteNpyFloat32C3(argv[2], data.normalMap)) return 4;
    std::cout << "{\"width\":" << data.normalMap.cols
              << ",\"height\":" << data.normalMap.rows
              << ",\"normal_present\":true}\n";
    return 0;
}
