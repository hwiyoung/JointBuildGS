import unittest
import numpy as np
import torch
from src.phd.p2_ab_v4.appearance_probe import validate_mvs_initial,freeze_except_color


class MVSInitializationTest(unittest.TestCase):
    def fixture(self):
        native=dict(mvs_xyz=np.arange(15,dtype=np.float32).reshape(5,3),mvs_tile_rows=np.arange(100,105),mvs_patch_id=np.arange(5),mvs_unit_index=np.arange(5)+20)
        ids=np.array([1,4]);seed=dict(seed_id=ids,xyz=native["mvs_xyz"][ids],native_row=native["mvs_tile_rows"][ids],native_patch_id=native["mvs_patch_id"][ids],unit_index=native["mvs_unit_index"][ids])
        return seed,{k:v.copy() for k,v in seed.items()},native

    def test_exact_native_rows_and_geometry_required(self):
        seed,g0,native=self.fixture()
        self.assertTrue(all(validate_mvs_initial(seed,g0,native,2)["checks"].values()))
        g0["xyz"][0,2]+=.1
        with self.assertRaises(ValueError):validate_mvs_initial(seed,g0,native,2)

    def test_wrong_source_membership_rejected(self):
        seed,g0,native=self.fixture();seed["native_row"][0]=999
        with self.assertRaises(ValueError):validate_mvs_initial(seed,g0,native,2)
        seed,g0,native=self.fixture();seed["seed_id"][1]=seed["seed_id"][0]
        with self.assertRaises(ValueError):validate_mvs_initial(seed,g0,native,2)

    def test_sh_degree_does_not_unlock_geometry(self):
        model=torch.nn.Module()
        for name in ["xyz","sh0","sh_rest"]:model.register_parameter(name,torch.nn.Parameter(torch.ones(2)))
        self.assertEqual(len(freeze_except_color(model,0)),1)
        self.assertFalse(model.sh_rest.requires_grad)
        self.assertEqual(len(freeze_except_color(model,3)),2)
        self.assertFalse(model.xyz.requires_grad)
        self.assertTrue(model.sh_rest.requires_grad)


if __name__=="__main__":unittest.main()
