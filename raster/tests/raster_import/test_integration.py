# (C) British Crown Copyright 2015 - 2019, Met Office
import cPickle as pickle
import tempfile

import iris.tests as tests
import numpy as np

import raster._raster_import as raster_import
from raster import export_geotiff


class Test_pickleable(tests.IrisTest):
    def assertProxyEqual(self, proxy1, proxy2):
        for item in proxy1.__slots__:
            self.assertEqual(getattr(proxy1, item), getattr(proxy2, item))

    def test_all(self):
        # Ensure that the __getstate__ and __setstate__ special methods
        # provide pickleable gdal proxies.  See
        # https://docs.python.org/2/library/pickle.html
        proxy = raster_import._GdalDataProxy((2, 3), np.uint8, 'some_path.bil',
                                             0, -999)
        proxy_pickled = pickle.dumps(proxy)
        proxy_unpickled = pickle.loads(proxy_pickled)
        self.assertProxyEqual(proxy_unpickled, proxy)


class Test_global_field(tests.IrisTest):
    def assertCubeEqual(self, cube1, cube2):
        self.assertArrayEqual(cube1.data, cube2.data)
        for ax in ['x', 'y']:
            c1_coord = cube1.coord(axis=ax)
            c2_coord = cube2.coord(axis=ax)
            self.assertEqual(cube1.coord_dims(c1_coord),
                             cube2.coord_dims(c2_coord))
            self.assertArrayEqual(c1_coord.points,
                                  c2_coord.points)
            self.assertArrayEqual(c1_coord.bounds,
                                  c2_coord.bounds)

    def test_yx_increasing_coord(self):
        cube = tests.stock.geodetic((6, 3))
        fh = tempfile.NamedTemporaryFile(suffix='.bil')

        raster.export_geotiff(cube, fh.name)
        res_cube = raster_import.load_cubes(fh.name).next()

        self.assertCubeEqual(res_cube, cube)


class Test_deferred_loading(tests.IrisTest):
    def setUp(self):
        self.cube = tests.stock.geodetic((6, 3))
        self.fh = tempfile.NamedTemporaryFile(suffix='.bil')

        raster.export_geotiff(self.cube, self.fh.name)
        self.res_cube = raster_import.load_cubes(self.fh.name).next()

    def test_no_touch_defer_status(self):
        self.assertTrue(self.res_cube.has_lazy_data())

    def test_touch_defer_status(self):
        self.res_cube.data
        self.assertFalse(self.res_cube.has_lazy_data())

    def test_partial_touch(self):
        res_cube = self.res_cube[3:, 1:]
        res = res_cube.data
        tar = self.cube[3:, 1:].data
        self.assertArrayEqual(res, tar)
        self.assertFalse(res_cube.has_lazy_data())
        self.assertTrue(self.res_cube.has_lazy_data())

    def test_partial_touch_alt(self):
        res_cube = self.res_cube[1:]
        res = res_cube.data
        tar = self.cube[1:].data
        self.assertArrayEqual(res, tar)
        self.assertFalse(res_cube.has_lazy_data())
        self.assertTrue(self.res_cube.has_lazy_data())


if __name__ == "__main__":
    tests.main()
