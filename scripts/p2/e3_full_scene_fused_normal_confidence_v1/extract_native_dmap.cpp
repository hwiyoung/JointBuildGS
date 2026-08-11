#include <MVS.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>

namespace {

bool WriteHeader(std::ofstream& output, const std::string& shape) {
    const std::string magic("\x93NUMPY", 6);
    const unsigned char major = 1, minor = 0;
    std::string header = "{'descr': '<f4', 'fortran_order': False, 'shape': " + shape + ", }";
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
    return output.good();
}

bool WriteC1(const std::string& path, const cv::Mat& matrix) {
    if (matrix.type() != CV_32FC1 || !matrix.isContinuous()) return false;
    std::ofstream output(path, std::ios::binary);
    if (!output || !WriteHeader(output, "(" + std::to_string(matrix.rows) + ", " + std::to_string(matrix.cols) + ")")) return false;
    output.write(reinterpret_cast<const char*>(matrix.ptr<float>(0)),
                 static_cast<std::streamsize>(matrix.total() * sizeof(float)));
    return output.good();
}

bool WriteC3(const std::string& path, const cv::Mat& matrix) {
    if (matrix.type() != CV_32FC3 || !matrix.isContinuous()) return false;
    std::ofstream output(path, std::ios::binary);
    if (!output || !WriteHeader(output, "(" + std::to_string(matrix.rows) + ", " + std::to_string(matrix.cols) + ", 3)")) return false;
    output.write(reinterpret_cast<const char*>(matrix.ptr<float>(0)),
                 static_cast<std::streamsize>(matrix.total() * 3 * sizeof(float)));
    return output.good();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 5) {
        std::cerr << "usage: extract_native_dmap input.dmap depth.npy confidence.npy normal.npy\n";
        return 2;
    }
    MVS::DepthData data;
    if (!data.Load(argv[1])) {
        std::cerr << "failed to load " << argv[1] << "\n";
        return 3;
    }
    if (data.depthMap.empty() || data.confMap.empty() || data.normalMap.empty()) {
        std::cerr << "DMAP depth/confidence/normal payload incomplete: " << argv[1] << "\n";
        return 4;
    }
    if (!WriteC1(argv[2], data.depthMap) || !WriteC1(argv[3], data.confMap) || !WriteC3(argv[4], data.normalMap)) {
        std::cerr << "failed to write NPY outputs\n";
        return 5;
    }
    std::cout << "{\"width\":" << data.depthMap.cols
              << ",\"height\":" << data.depthMap.rows
              << ",\"normal_present\":true}\n";
    return 0;
}
