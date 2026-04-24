// CGAL PolyFit wrapper — per-building polygonal surface reconstruction.
//
// Input format (argv[1], plain text):
//   n_points n_planes
//   px py pz nx ny nz plane_id     (one per line, n_points lines)
//   (plane_id in [0, n_planes))
//
// Output: OFF mesh written to argv[2].

#define CGAL_USE_SCIP

#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/property_map.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygonal_surface_reconstruction.h>
#include <CGAL/SCIP_mixed_integer_program_traits.h>
#include <CGAL/IO/OFF.h>
#include <CGAL/Polygon_mesh_processing/orientation.h>
#include <CGAL/Polygon_mesh_processing/stitch_borders.h>

#include <fstream>
#include <iostream>
#include <vector>
#include <boost/tuple/tuple.hpp>

typedef CGAL::Exact_predicates_inexact_constructions_kernel Kernel;
typedef Kernel::Point_3  Point;
typedef Kernel::Vector_3 Vector;

typedef boost::tuple<Point, Vector, int> PNI;
typedef std::vector<PNI> Point_vector;
typedef CGAL::Nth_of_tuple_property_map<0, PNI> Point_map;
typedef CGAL::Nth_of_tuple_property_map<1, PNI> Normal_map;
typedef CGAL::Nth_of_tuple_property_map<2, PNI> Plane_index_map;

typedef CGAL::SCIP_mixed_integer_program_traits<double>       MIP_Solver;
typedef CGAL::Polygonal_surface_reconstruction<Kernel>        Polygonal_surface_reconstruction;
typedef CGAL::Surface_mesh<Point>                             Surface_mesh;

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " input.txt output.off [fitting coverage complexity]\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) { std::cerr << "Cannot open " << argv[1] << "\n"; return 2; }

    int n_pts, n_planes;
    in >> n_pts >> n_planes;

    Point_vector points;
    points.reserve(n_pts);
    for (int i = 0; i < n_pts; ++i) {
        double px, py, pz, nx, ny, nz;
        int pid;
        in >> px >> py >> pz >> nx >> ny >> nz >> pid;
        points.push_back(boost::make_tuple(Point(px, py, pz), Vector(nx, ny, nz), pid));
    }

    double w_fit = (argc >= 4) ? std::atof(argv[3]) : 0.43;
    double w_cov = (argc >= 5) ? std::atof(argv[4]) : 0.27;
    double w_cmp = (argc >= 6) ? std::atof(argv[5]) : 0.30;
    std::cerr << "[polyfit] " << n_pts << " pts, " << n_planes << " planes, "
              << "w=(" << w_fit << "," << w_cov << "," << w_cmp << ")\n";

    Polygonal_surface_reconstruction algo(points, Point_map(), Normal_map(), Plane_index_map());

    Surface_mesh model;
    if (!algo.reconstruct<MIP_Solver>(model, w_fit, w_cov, w_cmp)) {
        std::cerr << "[polyfit] FAIL: " << algo.error_message() << "\n";
        return 1;
    }

    // Stitch coincident border edges: PolyFit emits duplicate vertices per-face,
    // so adjacent faces share coords but not vertex indices. After stitching,
    // the mesh uses shared halfedges where faces meet.
    CGAL::Polygon_mesh_processing::stitch_borders(model);

    bool closed = CGAL::is_closed(model);
    std::cerr << "[polyfit] after stitch: is_closed=" << closed
              << " n_faces=" << model.number_of_faces() << "\n";

    if (closed) {
        // orient_to_bound_a_volume requires closed mesh. Makes all face normals
        // consistent (outward). Fixes val3dity 303 NON_MANIFOLD / 307 ORIENT.
        CGAL::Polygon_mesh_processing::orient_to_bound_a_volume(model);
    }

    std::ofstream out(argv[2]);
    CGAL::IO::write_OFF(out, model);
    std::cerr << "[polyfit] OK: " << model.number_of_faces() << " faces -> " << argv[2] << "\n";
    return 0;
}
