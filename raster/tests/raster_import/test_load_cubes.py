# (C) British Crown Copyright 2015 - 2019, Met Office
import iris.tests as tests
import raster.tests

from collections import namedtuple
import copy

import iris
import mock
import numpy as np

from raster._raster_import import load_cubes


class CFCRS(object):
    """
    Encapsulation of coordinate system and metadata corresponding to grid
    metadata.

    """
    _AxisMeta = namedtuple('AxisMeta', 'standard_name units')

    def __init__(self, crs):
        """
        Return an object describing a coordinate system along with metadata
        required for a grid defined on this coordinate system.

        Parameters
        ----------
        crs : :class:`iris.coord_systems.CoordSystem`
        x_metadata : dict
            Metadata describing the x axis of a grid with corresponding
            coordinate system.  Of the form
            {'standard_name': ..., 'units':, ...}.
        y_metatada : dict
            Metadata describing the x axis of a grid with corresponding
            coordinate system.  Of the form
            {'standard_name': ..., 'units':, ...}.

        """
        self._crs = crs

        if isinstance(crs, iris.coord_systems.GeogCS):
            x_metadata = {'standard_name': 'longitude', 'units': 'degree_east'}
            y_metadata = {'standard_name': 'latitude', 'units': 'degree_north'}
        elif isinstance(crs, iris.coord_systems.RotatedGeogCS):
            x_metadata = {'standard_name': 'grid_longitude', 'units':
                          'degrees'}
            y_metadata = {'standard_name': 'grid_latitude', 'units': 'degrees'}
        else:
            x_metadata = {'standard_name': 'projection_x_coordinate', 'units':
                          'm'}
            y_metadata = {'standard_name': 'projection_y_coordinate', 'units':
                          'm'}

        self._x_metadata = self._set_metadata(x_metadata)
        self._y_metadata = self._set_metadata(y_metadata)

    def __str__(self):
        fmt = '{!s}, x_meatadata={!s}, y_metadata={!s}'
        return fmt.format(self.crs, self.x, self.y)

    def __repr__(self):
        return '{!r}'.format(self.crs)

    def _set_metadata(self, value):
        return self._AxisMeta(**value)

    @property
    def crs(self):
        """Return coordinate system."""
        return copy.deepcopy(self._crs)

    @property
    def x(self):
        """Return metadata corresponding to the x axis."""
        return self._x_metadata

    @property
    def y(self):
        """Return metadata corresponding to the y axis."""
        return self._y_metadata


WGS84_GEODETIC = CFCRS(
    iris.coord_systems.GeogCS(semi_major_axis=6378137.0,
                              inverse_flattening=298.257223563))


OSGB = CFCRS(iris.coord_systems.TransverseMercator(
    49, -2, 400000, -100000, 0.9996012717,
    iris.coord_systems.GeogCS(6377563.396, 6356256.909)))


class TestAll(tests.IrisTest):
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

        self.assertCRS(cube, WGS84_GEODETIC)

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

        self.assertCRS(cube, OSGB)

    def test_multiple_raster_bands(self):
        # Ensure that CubeList of length corresponding to the number of bands
        # is returned and that each has associated coordinates.
        self.dataset.RasterCount = 3
        cubes = list(load_cubes('some_filename'))
        self.assertEqual(len(cubes), self.dataset.RasterCount)
        self.assertCML(cubes, ('raster_import',
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


if __name__ == "__main__":
    tests.main()
