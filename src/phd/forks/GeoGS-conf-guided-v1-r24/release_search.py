"""Exact CPU target search used for case A/B classification and pull only."""
import ctypes, os
import numpy as np
class TangentTree:
    def __init__(self,points,normals,width,ids):
        self.lib=ctypes.CDLL(os.environ.get('JBGS_RELEASE_SEARCH','/release/bin/release_search.so'))
        dp=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS');ip=np.ctypeslib.ndpointer(dtype=np.int64,flags='C_CONTIGUOUS')
        self.lib.release_tree.argtypes=[dp,dp,dp,ip,ctypes.c_int64];self.lib.release_tree.restype=ctypes.c_void_p
        self.lib.release_query.argtypes=[ctypes.c_void_p,dp,ctypes.c_int64,dp,dp,ip]
        self.lib.release_free.argtypes=[ctypes.c_void_p]
        self.handle=self.lib.release_tree(np.ascontiguousarray(points,dtype='f8'),np.ascontiguousarray(normals,dtype='f8'),np.ascontiguousarray(width,dtype='f8'),np.ascontiguousarray(ids,dtype='i8'),len(points))
    def query(self,xyz):
        xyz=np.ascontiguousarray(xyz,dtype='f8');n=len(xyz);d=np.empty(n);e=np.empty(n);i=np.empty(n,'i8')
        self.lib.release_query(self.handle,xyz,n,d,e,i);return d,e,i
    def __del__(self):
        if getattr(self,'handle',None):self.lib.release_free(self.handle);self.handle=None
