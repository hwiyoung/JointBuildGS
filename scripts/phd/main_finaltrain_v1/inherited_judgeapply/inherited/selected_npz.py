"""Select NPZ rows before decoding any measurement values.

ZIP streams may inflate skipped compressed blocks internally. Only selected
row byte ranges are passed to NumPy. Membership is read from IDs alone.
"""
import numpy as np

def selected(z, key, mask):
    mask = np.asarray(mask, dtype=bool)
    with z.open(key+'.npy') as f:
        version = np.lib.format.read_magic(f)
        shape, fortran, dtype = np.lib.format._read_array_header(f, version)
        assert shape[0] == len(mask) and not fortran and not dtype.hasobject
        start = f.tell()
        rowbytes = dtype.itemsize * int(np.prod(shape[1:], dtype=np.int64))
        changes = np.diff(np.r_[False, mask, False].astype(np.int8))
        result = np.empty((int(mask.sum()),)+shape[1:], dtype=dtype)
        cursor = 0
        for a, b in zip(np.flatnonzero(changes==1), np.flatnonzero(changes==-1)):
            f.seek(start+int(a)*rowbytes)
            data = f.read(int(b-a)*rowbytes)
            assert len(data) == int(b-a)*rowbytes
            result[cursor:cursor+b-a] = np.frombuffer(data, dtype=dtype).reshape((b-a,)+shape[1:])
            cursor += b-a
        assert cursor == len(result)
        return result

def building_ids(z):
    with z.open('building.npy') as f:
        return np.lib.format.read_array(f, allow_pickle=False)
