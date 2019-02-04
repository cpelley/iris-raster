# (C) British Crown Copyright 2015 - 2019, Met Office
# Refer to README.md of this project for license details.
#
# This file is part of ANTS.
import iris.tests as tests
import mock
import numpy as np

from raster._raster_import import _GdalDataProxy


class Test___init__(tests.IrisTest):
    def test_all(self):
        # Ensure that the properties of the object are expected, in particular
        # that the fill_value dtype matches the specified dtype.
        shape = (2, 3)
        dtype = np.int16
        path = mock.sentinel.path
        raster_band_index = mock.sentinel.raster_band_index
        fill_value = True
        proxy = _GdalDataProxy(shape, dtype, path, raster_band_index,
                               fill_value)
        self.assertEqual(proxy.shape, (3, 2))
        self.assertIs(proxy.path, path)
        self.assertIs(proxy.dtype, np.dtype(dtype))
        self.assertIs(proxy.raster_band_index, raster_band_index)
        target_fill_value = np.int16(1)
        self.assertEqual(proxy.fill_value.dtype, target_fill_value.dtype)
        self.assertEqual(proxy.fill_value, target_fill_value)

    def test_dtype_conversion(self):
        # Ensure that dtype promotion occurs for unsigned integers.
        shape = (2, 3)
        dtype = np.uint8
        path = mock.sentinel.path
        raster_band_index = mock.sentinel.raster_band_index
        fill_value = True
        proxy = _GdalDataProxy(shape, dtype, path, raster_band_index,
                               fill_value)
        self.assertIs(proxy.dtype, np.dtype('int16'))


class Test_ndim(tests.IrisTest):
    @staticmethod
    def gen_gdalproxy(shape):
        dtype = None
        path = None
        raster_band_index = None
        fill_value = True
        return _GdalDataProxy(shape, dtype, path, raster_band_index,
                              fill_value)

    def test_2d(self):
        shape = [0]*2
        proxy = self.gen_gdalproxy(shape)
        self.assertIs(proxy.ndim, 2)

    def test_3d(self):
        shape = [0]*3
        msg = ('Raster image shape describes 3 dimensions, expecting 2 '
               'dimensions')
        with self.assertRaisesRegexp(ValueError, msg):
            self.gen_gdalproxy(shape)


class Test___repr__(tests.IrisTest):
    def test_all(self):
        proxy = _GdalDataProxy((2, 3), np.int8, 'some_path.bil', 0, -999)
        target = ("<_GdalDataProxy shape=(3, 2) dtype=dtype('int8') "
                  "path='some_path.bil' raster_band_index=0>")
        self.assertEqual(proxy.__repr__(), target)


class Test___getitem__(tests.IrisTest):
    def setUp(self):
        self.data = np.array([[1, 2, 3], [4, 5, 6]])

        self.iband = mock.Mock(name='iband')
        self.iband.ReadAsArray.return_value = self.data[::-1, :]

        self.dataset = mock.Mock(name='dataset')
        self.dataset.GetRasterBand.return_value = self.iband

        gdal_patch = mock.patch('osgeo.gdal.Open',
                                return_value=self.dataset)
        self.gdal_patch = gdal_patch.start()
        self.addCleanup(gdal_patch.stop)

    def _init_proxy(self):
        return _GdalDataProxy(self.data.shape, np.int16, mock.sentinel.path,
                              3, 10)

    def test_negative_index_x(self):
        proxy = self._init_proxy()
        proxy[:, 0:-1]
        self.iband.ReadAsArray.assert_called_once_with(0, 0, 1, 3)

    def test_single_index_x(self):
        proxy = self._init_proxy()
        proxy[slice(None), slice(1, None)]
        self.iband.ReadAsArray.assert_called_once_with(1, 0, 1, 3)

    def test_single_index_y_explicit(self):
        proxy = self._init_proxy()
        proxy[slice(1, 2), slice(None)]
        self.iband.ReadAsArray.assert_called_once_with(0, 1, 2, 1)

    def test_single_beyond_extent_alternative(self):
        # Ensure that if we index beyond the shape that we still request
        # suitable indices.
        proxy = self._init_proxy()
        proxy[slice(None), slice(1, 3)]
        self.iband.ReadAsArray.assert_called_once_with(1, 0, 1, 3)

    def test_index_range(self):
        proxy = self._init_proxy()
        proxy[slice(None), slice(None, 3)]
        self.iband.ReadAsArray.assert_called_once_with(0, 0, 2, 3)

    def test_index_single(self):
        # Ensure that we handle indexing by a single number.  The final 'y'
        # index is requested which is inverted and so the first gdal index is
        # requested.
        proxy = self._init_proxy()
        proxy[2, slice(None, 3)]
        self.iband.ReadAsArray.assert_called_once_with(0, 0, 2, 1)

    def test_index_single_beyond(self):
        proxy = self._init_proxy()
        msg = 'Raster index out of range'
        with self.assertRaisesRegexp(IndexError, msg):
            proxy[3, slice(None, 3)]

    def test_multiple_iterable_index_keys(self):
        proxy = self._init_proxy()
        proxy[(0, 1, 2), slice(None, 3)]
        self.iband.ReadAsArray.assert_called_once_with(0, 0, 2, 3)

    def test_discontiguous_extraction(self):
        # The case where multiple separate pieces are extracted and merged is
        # not yet supported.
        proxy = self._init_proxy()
        msg = 'Currently no support for discontiguous extraction.'
        with self.assertRaisesRegexp(ValueError, msg):
            proxy[(0, 2), slice(None, 3)]

    def test_step_size_unsupported(self):
        proxy = self._init_proxy()
        msg = 'Step size not currently supported for gdal indexing'
        with self.assertRaisesRegexp(IndexError, msg):
            proxy[slice(None), slice(None, 3, 2)]

    def test_step_size_positive_one(self):
        # Ensure that a step size of 1 is equivalent to None.
        proxy = self._init_proxy()
        proxy[slice(None, None, 1), slice(None, None, 1)]
        self.iband.ReadAsArray.assert_called_once_with(0, 0, 2, 3)

    def test_gdal_open(self):
        proxy = self._init_proxy()
        proxy[slice(None), slice(None)]
        self.gdal_patch.assert_called_once_with(mock.sentinel.path, 0)

    def test_getrasterband(self):
        # Ensure that the Python/C zero based indexing is converted to 1
        # based.
        proxy = self._init_proxy()
        proxy[slice(None), slice(None)]
        self.dataset.GetRasterBand.assert_called_once_with(4)

    def test_unmasked(self):
        proxy = self._init_proxy()
        data = proxy[slice(None), slice(None)]
        target = self.data.copy()
        self.assertArrayEqual(data, target)

    def test_masked(self):
        proxy = self._init_proxy()
        proxy.fill_value = 5
        data = proxy[slice(None), slice(None)]
        target = self.data.copy()
        np.ma.masked_values(target, 5, copy=False)
        self.assertArrayEqual(data, target)


if __name__ == "__main__":
    tests.main()
