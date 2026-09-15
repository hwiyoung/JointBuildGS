"""Apply the verified memory raster path during extraction as well as training."""
import runpy
import memory_raster
memory_raster.install()
runpy.run_path('/source/render.py',run_name='__main__')
