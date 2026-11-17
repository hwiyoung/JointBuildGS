"""Mesh one addendum-5 model with the addendum-4 mesh driver (TRAINERR te_pipeline2 rule, same code), redirected to the addendum5 payload
(shadow addendum5/gtj, /te = addendum5, logs addendum5/logs). usage: TE_FASTWORK=<dir> python3 a5_mesh.py <stem>:<family>:<ply path in the gtj container>:<gpu>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addendum4'))
import a4_launch as A
A.A4O = A.O/'addendum5'; A.LOGS = A.A4O/'logs'
import a4_mesh as M
M.SH = A.A4O/'gtj'
if __name__ == '__main__': M.main(1, *sys.argv[1:])
