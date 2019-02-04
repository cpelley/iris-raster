# (C) British Crown Copyright 2015 - 2018, Met Office
# Refer to README.md of this project for license details.
#
# This file is part of ANTS.
import mock
import numpy as np

import ants
import ants.tests as tests


try:
    from ants.fileformats.raster import load_cubes
except Exception:
    pass


@tests.skip_gdal
class TestAll(tests.TestCase):
    def setUp(self):
        self.dataset = mock.Mock(name='dataset')
        self.dataset.RasterCount = 1
        self.dataset.GetGeoTransform.return_value = (-180, 25, 0,
                                                     -90, 0, 25)
        self.dataset.RasterXSize = 5
        self.dataset.RasterYSize = 5
        self.dataset.GetProjection.return_value = ''
        getdata = mock.Mock()
        getdata.ReadAsArray.return_value = np.arange(
            5*5, dtype='int16').reshape(5, 5)
        getdata.GetNoDataValue.return_value = -999
        getdata.DataType = 3
        self.dataset.GetRasterBand.return_value = getdata

        # Set WGS84 as our projection
        gdal_projection = ('GEOGCS["GCS_WGS_1984",DATUM["WGS_1984",'
                           'SPHEROID["WGS_84",6378137,298.257223563]],'
                           'PRIMEM["Greenwich",0],UNIT["Degree",'
                           '0.017453292519943295]]')
        self.dataset.GetProjection.return_value = gdal_projection

        # TODO: Patch the module import so that these unittests do not require
        # the gdal library, see http://www.voidspace.org.uk/python/mock/
        # examples.html#mocking-imports-with-patch-dict
        gdal_patch = mock.patch('osgeo.gdal.Open', return_value=self.dataset)
        self.gdal_patch = gdal_patch.start()
        self.addCleanup(gdal_patch.stop)

    def test_dataset_is_none(self):
        self.gdal_patch.return_value = None
        with self.assertRaisesRegexp(IOError, 'gdal failed to open raster '
                                     'image'):
            load_cubes('some_filename').next()

    def test_unsupported_projection(self):
        gdal_projection = ('GEOGCS["unnamed ellipse",DATUM["unknown",'
                           'SPHEROID["unnamed",637122]],'
                           'PRIMEM["Greenwich",0],UNIT["degree",'
                           '0.019]]')
        self.dataset.GetProjection.return_value = gdal_projection
        msg = 'Projection information not currently in lookup table:'
        with self.assertRaisesRegexp(RuntimeError, msg):
            load_cubes('some_filename').next()

    def assertCRS(self, cube, crs):
        for axis in ['x', 'y']:
            coord = cube.coord(axis=axis)
            self.assertEqual(coord.coord_system, crs.crs)
            self.assertEqual(coord.standard_name,
                             getattr(crs, axis).standard_name)
            self.assertEqual(coord.units, getattr(crs, axis).units)

    def test_crs_wgs84_geodetic(self):
        # Ensure that we correctly interpret the crs from igbp source data.
        gdal_projection = ('GEOGCS["GCS_WGS_1984",DATUM["WGS_1984",'
                           'SPHEROID["WGS_84",6378137,298.257223563]],'
                           'PRIMEM["Greenwich",0],UNIT["Degree",'
                           '0.017453292519943295]]')
        self.dataset.GetProjection.return_value = gdal_projection
        cube = load_cubes('some_filename').next()

        target_crs = ants.coord_systems.WGS84_GEODETIC
        self.assertCRS(cube, target_crs)

    def test_crs_osgb(self):
        # Ensure that we correctly interpret the crs from ite source data.
        gdal_projection = ('PROJCS["OSGB 1936 / British National Grid",'
                           'GEOGCS["OSGB 1936",DATUM["OSGB_1936",'
                           'SPHEROID["Airy_1830",6377563.396,299.3249646]],'
                           'PRIMEM["Greenwich",0],UNIT["Degree",'
                           '0.017453292519943295]],PROJECTION['
                           '"Transverse_Mercator"],PARAMETER['
                           '"latitude_of_origin",49],PARAMETER['
                           '"central_meridian",-2],PARAMETER["scale_factor",'
                           '0.9996012717],PARAMETER["false_easting",400000],'
                           'PARAMETER["false_northing",-100000],'
                           'UNIT["Meter",1]]')
        self.dataset.GetProjection.return_value = gdal_projection
        cube = load_cubes('some_filename').next()

        target_crs = ants.coord_systems.OSGB
        self.assertCRS(cube, target_crs)

    def test_multiple_raster_bands(self):
        # Ensure that CubeList of length corresponding to the number of bands
        # is returned and that each has associated coordinates.
        self.dataset.RasterCount = 3
        cubes = list(load_cubes('some_filename'))
        self.assertEqual(len(cubes), self.dataset.RasterCount)
        self.assertCML(cubes, ('fileformats', 'raster',
                               'raster_multiple_band_import.cml'),
                       checksum=False)

    def test_no_raster_bands(self):
        self.dataset.RasterCount = 0
        with self.assertRaises(StopIteration):
            load_cubes('some_filename').next()

    def test_rotated_raster(self):
        # Rotated is where a non north-up image is defined.
        # No test data to-hand to develop interpretation of rotation so an
        # exception is raised.
        rotation = [1, 1]
        self.dataset.GetGeoTransform.return_value = (
            -200000, 50000, rotation[0], -200000, rotation[1], 50000)
        msg = r'Rotation not supported: \({}, {}\)'
        msg = msg.format(rotation[0], rotation[1])
        with self.assertRaisesRegexp(ValueError, msg):
            load_cubes('some_filename').next()

    def test_no_gdal_library(self):
        # Ensure that we raise a suitable exception when there is no gdal
        # library present.
        msg = 'gdal error'
        ants.fileformats.raster._GDAL_IMPORT_ERROR = ImportError('gdal error')
        with mock.patch('ants.fileformats.raster.gdal', new=None):
            with self.assertRaisesRegexp(ImportError, msg):
                load_cubes('some_filename').next()


if __name__ == "__main__":
    tests.main()
