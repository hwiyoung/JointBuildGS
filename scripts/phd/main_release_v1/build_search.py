from common import *
import subprocess
cfg()
p=R/'src/phd/forks/GeoGS-conf-guided-v1-r24/release_search.cpp'
subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC','-fopenmp',str(p),'-o',str(O/'bin/release_search.so')],check=True)
dump(O/'verification/search_build.json',dict(source_sha256=sha(p),binary_sha256=sha(O/'bin/release_search.so'),scientific_verdict=None))
