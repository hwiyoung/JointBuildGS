import argparse

import numpy as np
import open3d as o3d


def main():
    parser = argparse.ArgumentParser(description="Uniformly sample a mesh surface into a point cloud")
    parser.add_argument("--mesh_path", type=str, default="./evaluation_data/example_ply/mesh.ply")
    parser.add_argument("--output_path", type=str, default="./evaluation_data/example_ply/mesh_points.ply")
    parser.add_argument("--num_points", type=int, default=1_000_000)
    args = parser.parse_args()

    mesh = o3d.io.read_triangle_mesh(args.mesh_path)

    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    if not mesh.has_vertex_colors():
        gray_color = np.tile([[0.5, 0.5, 0.5]], (np.asarray(mesh.vertices).shape[0], 1))
        mesh.vertex_colors = o3d.utility.Vector3dVector(gray_color)

    pcd = mesh.sample_points_uniformly(number_of_points=args.num_points)

    o3d.io.write_point_cloud(args.output_path, pcd)
    print(f"Point cloud saved to: {args.output_path}")


if __name__ == "__main__":
    main()
