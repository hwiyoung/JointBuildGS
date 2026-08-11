#include <MVS.h>

#include <cmath>
#include <cstdint>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {

bool WriteNpyFloat32(const std::string& path, const cv::Mat& matrix) {
    if (matrix.type() != CV_32FC1 || !matrix.isContinuous()) {
        std::cerr << "expected a continuous CV_32FC1 matrix\n";
        return false;
    }
    std::ofstream output(path, std::ios::binary);
    if (!output) {
        std::cerr << "failed to open " << path << "\n";
        return false;
    }
    const std::string magic("\x93NUMPY", 6);
    const unsigned char major = 1;
    const unsigned char minor = 0;
    std::string header = "{'descr': '<f4', 'fortran_order': False, 'shape': (" +
        std::to_string(matrix.rows) + ", " + std::to_string(matrix.cols) + "), }";
    const std::size_t preamble = magic.size() + 2 + 2;
    const std::size_t padding = 16 - ((preamble + header.size() + 1) % 16);
    header.append(padding, ' ');
    header.push_back('\n');
    const std::uint16_t header_size = static_cast<std::uint16_t>(header.size());
    const unsigned char header_bytes[2] = {
        static_cast<unsigned char>(header_size & 0xff),
        static_cast<unsigned char>((header_size >> 8) & 0xff),
    };
    output.write(magic.data(), magic.size());
    output.put(static_cast<char>(major));
    output.put(static_cast<char>(minor));
    output.write(reinterpret_cast<const char*>(header_bytes), 2);
    output.write(header.data(), header.size());
    output.write(reinterpret_cast<const char*>(matrix.ptr<float>(0)),
                 static_cast<std::streamsize>(matrix.total() * sizeof(float)));
    return output.good();
}

double Quantile(std::vector<float> values, double probability) {
    if (values.empty()) return 0.0;
    const double position = probability * static_cast<double>(values.size() - 1);
    const std::size_t lower = static_cast<std::size_t>(std::floor(position));
    const std::size_t upper = static_cast<std::size_t>(std::ceil(position));
    std::nth_element(values.begin(), values.begin() + lower, values.end());
    const double low_value = values[lower];
    if (upper == lower) return low_value;
    std::nth_element(values.begin(), values.begin() + upper, values.end());
    return low_value + (values[upper] - low_value) * (position - lower);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2 && argc != 4) {
        std::cerr << "usage: inspect_openmvs_dmap <depthNNNN.dmap> [depth.npy confidence.npy]\n";
        return 2;
    }

    MVS::DepthData data;
    if (!data.Load(argv[1])) {
        std::cerr << "failed to load " << argv[1] << "\n";
        return 1;
    }

    std::uint64_t depth_valid = 0;
    std::uint64_t confidence_positive = 0;
    double confidence_sum = 0.0;
    float confidence_min = std::numeric_limits<float>::infinity();
    float confidence_max = -std::numeric_limits<float>::infinity();
    std::vector<float> positive_confidence;
    positive_confidence.reserve(data.depthMap.total());

    for (int y = 0; y < data.depthMap.rows; ++y) {
        const float* depth = data.depthMap.ptr<float>(y);
        const float* confidence = data.confMap.empty() ? nullptr : data.confMap.ptr<float>(y);
        for (int x = 0; x < data.depthMap.cols; ++x) {
            if (std::isfinite(depth[x]) && depth[x] > 0.f) {
                ++depth_valid;
            }
            if (confidence && std::isfinite(confidence[x]) && confidence[x] > 0.f) {
                ++confidence_positive;
                confidence_sum += confidence[x];
                confidence_min = std::min(confidence_min, confidence[x]);
                confidence_max = std::max(confidence_max, confidence[x]);
                positive_confidence.push_back(confidence[x]);
            }
        }
    }

    if (argc == 4) {
        if (!WriteNpyFloat32(argv[2], data.depthMap) ||
            !WriteNpyFloat32(argv[3], data.confMap)) {
            return 1;
        }
    }

    std::cout << "{"
              << "\"path\":\"" << argv[1] << "\","
              << "\"width\":" << data.depthMap.cols << ","
              << "\"height\":" << data.depthMap.rows << ","
              << "\"depth_valid\":" << depth_valid << ","
              << "\"confidence_present\":" << (!data.confMap.empty() ? "true" : "false") << ","
              << "\"confidence_positive\":" << confidence_positive << ","
              << "\"confidence_mean_positive\":"
              << (confidence_positive ? confidence_sum / static_cast<double>(confidence_positive) : 0.0) << ","
              << "\"confidence_min_positive\":"
              << (confidence_positive ? confidence_min : 0.0f) << ","
              << "\"confidence_max_positive\":"
              << (confidence_positive ? confidence_max : 0.0f) << ","
              << "\"confidence_p10_positive\":" << Quantile(positive_confidence, 0.10) << ","
              << "\"confidence_p25_positive\":" << Quantile(positive_confidence, 0.25) << ","
              << "\"confidence_p50_positive\":" << Quantile(positive_confidence, 0.50) << ","
              << "\"confidence_p75_positive\":" << Quantile(positive_confidence, 0.75) << ","
              << "\"confidence_p90_positive\":" << Quantile(positive_confidence, 0.90)
              << "}\n";
    return 0;
}
