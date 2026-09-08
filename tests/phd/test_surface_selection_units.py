import unittest
import numpy as np
from src.phd.surface_selection_v1.units import make_units


class UnitBoundaryTests(unittest.TestCase):
    def test_boundary_refinement_keeps_parallel_sources_and_all_area(self):
        xy=np.array([[.1,.1],[.6,.1],[1.1,.1],[1.6,.1]])
        native={'mvs_xyz':np.c_[xy,np.zeros(4)],'als_xyz':np.c_[xy,np.ones(4)*8]}
        memberships={'mvs':np.array([0,0,0,0]),'als':np.array([0,0,1,1])}
        units,rows,graph=make_units(native,memberships,{},dict(x=[0,2],y=[0,.5]),.5)
        self.assertEqual(len(units),2)
        self.assertAlmostEqual(sum(u['area_m2'] for u in units),1)
        self.assertEqual(rows['mvs_unit'].tolist(),[0,0,1,1])
        self.assertTrue(graph['edges'][0]['same_mvs_surface'])
        self.assertFalse(graph['edges'][0]['aggregation_crossing_allowed'])

    def test_vertical_overlap_is_not_silently_disambiguated(self):
        native={'mvs_xyz':np.array([[.1,.1,0],[.1,.1,2]]),'als_xyz':np.array([[.1,.1,0]])}
        units,rows,_=make_units(native,{'mvs':np.array([0,1]),'als':np.array([0])},{},dict(x=[0,1],y=[0,1]),.5)
        self.assertEqual(units[0]['mvs_ids'],[0,1]);self.assertTrue(units[0]['ambiguous'])
        self.assertEqual(sum(len(u['tile_ids']) for u in units),4)
        self.assertEqual(len(rows['mvs_unit']),2)


if __name__=='__main__':unittest.main()
