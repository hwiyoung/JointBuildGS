/*
Copyright (C) 2017  Liangliang Nan
https://3d.bk.tudelft.nl/liangliang/ - liangliang.nan@gmail.com

P0 audit CLI adaptation:
- accepts point cloud, footprint, and output paths as arguments;
- preserves City3D/CLI_Example_1 default reconstruction parameters.
*/

#include "../model/point_set.h"
#include "../model/map.h"
#include "../model/map_io.h"
#include "../model/point_set_io.h"
#include "../method/method_global.h"
#include "../method/reconstruction.h"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

void print_usage(const char* exe) {
    std::cerr
        << "Usage: " << exe << " <point_cloud.{ply,las,laz}> <footprint.{geojson,obj}> <output.obj>\n"
        << "       " << exe << " --version\n";
}

}  // namespace

int main(int argc, char **argv)
{
    if (argc == 2 && std::string(argv[1]) == "--version") {
        std::cout << "City3D CLI p0-wrapper; default Method::min_points=40 Method::pixel_size=0.15" << std::endl;
        return EXIT_SUCCESS;
    }
    if (argc != 4) {
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }

    // City3D CLI_Example_1 defaults.
    Method::min_points = 40;
    Method::pixel_size = 0.15;

    const std::string input_cloud_file = argv[1];
    const std::string input_footprint_file = argv[2];
    const std::string output_file = argv[3];

    std::cout << "loading input point cloud data from file: " << input_cloud_file << std::endl;
    PointSet *pset = PointSetIO::read(input_cloud_file);
    if (!pset) {
        std::cerr << "failed loading point cloud data from file: " << input_cloud_file << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << "loading input footprint data from file: " << input_footprint_file << std::endl;
    const vec3& offset = pset->offset();
    Map *footprint = MapIO::read(input_footprint_file, vec3(offset.x, offset.y, -pset->bbox().z_min()));
    if (!footprint) {
        std::cerr << "failed loading footprint data from file: " << input_footprint_file << std::endl;
        delete pset;
        return EXIT_FAILURE;
    }

    Reconstruction recon;

    std::cout << "segmenting individual buildings..." << std::endl;
    recon.segmentation(pset, footprint);

    std::cout << "extracting roof planes..." << std::endl;
    if (!recon.extract_roofs(pset, footprint)) {
        std::cerr << "no roofs could be extracted from the point cloud" << std::endl;
        delete pset;
        delete footprint;
        return EXIT_FAILURE;
    }

    Map *result = new Map;
#ifdef HAS_GUROBI
    std::cout << "reconstructing the buildings (using the Gurobi solver)..." << std::endl;
    bool status = recon.reconstruct(pset, footprint, result, LinearProgramSolver::GUROBI);
#else
    std::cout << "reconstructing the buildings (using the SCIP solver)..." << std::endl;
    bool status = recon.reconstruct(pset, footprint, result, LinearProgramSolver::SCIP);
#endif

    if (status && result->size_of_facets() > 0) {
        if (MapIO::save(output_file, result)) {
            std::cout << "reconstruction result saved to file: " << output_file << std::endl;
            delete pset;
            delete footprint;
            delete result;
            return EXIT_SUCCESS;
        }
        std::cerr << "failed to save reconstruction result to file: " << output_file << std::endl;
    } else {
        std::cerr << "reconstruction failed" << std::endl;
    }

    delete pset;
    delete footprint;
    delete result;

    return EXIT_FAILURE;
}
