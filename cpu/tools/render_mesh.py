"""Quick offscreen-ish render of a mesh to PNG for visual confirmation."""
import sys
import numpy as np
import open3d as o3d

path, out = sys.argv[1], sys.argv[2]
mesh = o3d.io.read_triangle_mesh(path)
mesh.compute_vertex_normals()

vis = o3d.visualization.Visualizer()
vis.create_window(visible=False, width=1100, height=900)
vis.add_geometry(mesh)
opt = vis.get_render_option()
opt.mesh_show_back_face = True
opt.background_color = np.array([1, 1, 1])
opt.light_on = True
vc = vis.get_view_control()
vc.set_front([0.3, -0.2, -1.0])
vc.set_up([0, 1, 0])
vc.set_zoom(0.7)
vis.poll_events()
vis.update_renderer()
vis.capture_screen_image(out, do_render=True)
vis.destroy_window()
print("wrote", out)
