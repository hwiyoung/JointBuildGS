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
#include <CGAL/Polygon_mesh_processing/polygon_soup_to_polygon_mesh.h>
#include <CGAL/Polygon_mesh_processing/polygon_mesh_to_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/repair_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/orient_polygon_soup.h>
#include <CGAL/Polygon_mesh_processing/merge_border_vertices.h>
#include <CGAL/Polygon_mesh_processing/triangulate_faces.h>

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

    namespace PMP = CGAL::Polygon_mesh_processing;

    std::cerr << "[polyfit] mip output: n_faces=" << model.number_of_faces()
              << " n_verts=" << model.number_of_vertices() << "\n";

    // === Phase 1 dominant cause A: PolyFit emits per-face independent vertices,
    // so stitch_borders alone fails on float-precision boundaries. The standard
    // CGAL repair is to convert to a polygon soup, dedup + repair + orient,
    // then rebuild the polygon mesh.

    std::vector<Point> soup_points;
    std::vector<std::vector<std::size_t>> soup_polygons;
    PMP::polygon_mesh_to_polygon_soup(model, soup_points, soup_polygons);
    std::cerr << "[polyfit] soup: " << soup_points.size() << " pts, "
              << soup_polygons.size() << " polys\n";

    PMP::merge_duplicate_points_in_polygon_soup(soup_points, soup_polygons);
    std::cerr << "[polyfit] after merge_dup: " << soup_points.size() << " pts, "
              << soup_polygons.size() << " polys\n";

    PMP::repair_polygon_soup(soup_points, soup_polygons);
    std::cerr << "[polyfit] after repair: " << soup_points.size() << " pts, "
              << soup_polygons.size() << " polys\n";

    bool oriented = PMP::orient_polygon_soup(soup_points, soup_polygons);
    std::cerr << "[polyfit] orient_polygon_soup: oriented="
              << (oriented ? "true" : "false") << "\n";

    Surface_mesh repaired;
    PMP::polygon_soup_to_polygon_mesh(soup_points, soup_polygons, repaired);
    std::cerr << "[polyfit] rebuilt mesh: n_faces=" << repaired.number_of_faces()
              << " n_verts=" << repaired.number_of_vertices() << "\n";

    // Existing close+orient on the repaired mesh
    PMP::stitch_borders(repaired);
    bool closed = CGAL::is_closed(repaired);
    std::cerr << "[polyfit] after stitch: is_closed=" << closed
              << " n_faces=" << repaired.number_of_faces() << "\n";

    if (closed) {
        // orient_to_bound_a_volume requires triangle mesh. Triangulate first.
        // We then keep the triangulated form for export — val3dity accepts
        // triangulated faces, and downstream reads OFF face-by-face anyway.
        bool tri_ok = PMP::triangulate_faces(repaired);
        std::cerr << "[polyfit] triangulate_faces: ok=" << tri_ok
                  << " n_faces=" << repaired.number_of_faces() << "\n";
        if (tri_ok) {
            PMP::orient_to_bound_a_volume(repaired);
            std::cerr << "[polyfit] orient_to_bound_a_volume done\n";
        }
    }

    std::ofstream out(argv[2]);
    CGAL::IO::write_OFF(out, repaired);
    std::cerr << "[polyfit] OK: " << repaired.number_of_faces() << " faces -> " << argv[2] << "\n";
    return 0;
}
