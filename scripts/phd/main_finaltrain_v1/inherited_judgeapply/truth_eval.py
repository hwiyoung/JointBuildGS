"""Bind the unchanged source module constant before evaluation-only execution."""
import sys
import truth
truth.scope['NMAD_K']=1.4826
if __name__=='__main__':truth.main(sys.argv[1])
