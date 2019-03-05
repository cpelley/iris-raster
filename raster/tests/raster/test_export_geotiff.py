# (C) British Crown Copyright 2014 - 2019, Met Office
from __future__ import (absolute_import, division, print_function)
from six.moves import (filter, input, map, range, zip)  # noqa

import os
import re

import iris
from iris.coord_systems import GeogCS
from iris.coords import DimCoord
from iris.cube import Cube
import iris.tests as tests
import numpy as np
from osgeo import gdal
import PIL.Image

from raster import export_geotiff


class TestGeoTiffExport(tests.IrisTest):
    def check_tiff_header(self, tiff_filename, expect_keys, expect_entries):
        """
        Checks the given tiff file's metadata contains the expected keys,
        and some matching values (not all).
        """
        with open(tiff_filename, 'rb') as fh:
            im = PIL.Image.open(fh)
            file_keys = im.tag.keys()

            missing_keys = sorted(set(expect_keys) - set(file_keys))
            msg_nokeys = "Tiff header has missing keys : {}."
            self.assertEqual(missing_keys, [],
                             msg_nokeys.format(missing_keys))

            extra_keys = sorted(set(file_keys) - set(expect_keys))
            msg_extrakeys = "Tiff header has extra unexpected keys : {}."
            self.assertEqual(extra_keys, [],
                             msg_extrakeys.format(extra_keys))

            msg_badval = "Tiff header entry {} has value {} != {}."
            for key, value in expect_entries.items():
                content = im.tag[key]
                self.assertEqual(content, value,
                                 msg_badval.format(key, content, value))

    def check_tiff(self, cube, header_keys, header_items):
        # Check that the cube saves correctly to TIFF :
        #   * the header contains expected keys and (some) values
        #   * the data array retrives correctly
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)

            # Check the metadata is correct.
            self.check_tiff_header(temp_filename, header_keys, header_items)

            # Ensure that north is at the top then check the data is correct.
            coord_y = cube.coord(axis='Y', dim_coords=True)
            data = cube.data
            if np.diff(coord_y.bounds[0]) > 0:
                data = cube.data[::-1, :]
            im = PIL.Image.open(temp_filename)
            im_data = np.array(im)
            # Currently we only support writing 32-bit tiff, when comparing
            # the data ensure that it is also 32-bit
            np.testing.assert_array_equal(im_data,
                                          data.astype(np.float32))

    def _check_tiff_export(self, masked, inverted=False):
        tif_header = 'sample_field.nc.tif_header.txt'
        tif_header_keys = [256, 257, 258, 259, 262, 273,
                           277, 278, 279, 284, 339, 33550, 33922]
        tif_header_entries = {
            256: (160,),
            257: (159,),
            258: (32,),
            259: (1,),
            262: (1,),
            # Skip this one: behaviour is not consistent across gdal versions.
            # 273: (354, 8034, 15714, 23394, 31074, 38754, 46434,
            #       54114, 61794, 69474, 77154, 84834, 92514, 100194),
            277: (1,),
            278: (12,),
            279: (7680, 7680, 7680, 7680, 7680, 7680, 7680,
                  7680, 7680, 7680, 7680, 7680, 7680, 1920),
            284: (1,),
            339: (3,),
            33550: (1.125, 1.125, 0.0),
            33922: (0.0, 0.0, 0.0, -0.5625, 89.4375, 0.0)
        }
        fin = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                           'sample_field.nc')
        cube = iris.load_cube(fin)
        # PIL doesn't support float64
        cube.data = cube.data.astype('f4')

        # Ensure longitude values are continuous and monotonically increasing,
        # and discard the 'half cells' at the top and bottom of the UM output
        # by extracting a subset.
        east = iris.Constraint(longitude=lambda cell: cell < 180)
        non_edge = iris.Constraint(latitude=lambda cell: -90 < cell < 90)
        cube = cube.extract(east & non_edge)
        cube.coord('longitude').guess_bounds()
        cube.coord('latitude').guess_bounds()

        if masked:
            # Mask some of the data + expect a slightly different header...
            cube.data = np.ma.masked_where(cube.data <= 380, cube.data)

            # There is an additional key..
            tif_header_keys += [42113]
            # Don't add a check entry for this, as coding changed between gdal
            # version 1 and 2, *and* between Python2 and Python3.
            # tif_header_entries[42113] = (u'1e+20',)

        if inverted:
            # Check with the latitude coordinate (and the corresponding
            # cube.data) inverted.
            # The output should be exactly the same.
            coord = cube.coord('latitude')
            coord.points = coord.points[::-1]
            coord.bounds = None
            coord.guess_bounds()
            cube.data = cube.data[::-1, :]

        self.check_tiff(cube, tif_header_keys, tif_header_entries)

    def test_unmasked(self):
        self._check_tiff_export(masked=False)

    def test_masked(self):
        self._check_tiff_export(masked=True)

    def test_inverted(self):
        self._check_tiff_export(masked=False, inverted=True)


class TestDtypeAndValues(tests.IrisTest):
    def _cube(self, dtype):
        data = np.arange(12).reshape(3, 4).astype(dtype) + 20
        cube = Cube(data, 'air_pressure_anomaly')
        coord = DimCoord(np.arange(3), 'latitude', units='degrees')
        coord.guess_bounds()
        cube.add_dim_coord(coord, 0)
        coord = DimCoord(np.arange(4), 'longitude', units='degrees')
        coord.guess_bounds()
        cube.add_dim_coord(coord, 1)
        return cube

    def _check_dtype(self, dtype, gdal_dtype):
        cube = self._cube(dtype)
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)
            dataset = gdal.Open(temp_filename, gdal.GA_ReadOnly)
            band = dataset.GetRasterBand(1)
            self.assertEqual(band.DataType, gdal_dtype)
            self.assertEqual(band.ComputeRasterMinMax(1), (20, 31))

    def test_int16(self):
        self._check_dtype('<i2', gdal.GDT_Int16)

    def test_int16_big_endian(self):
        self._check_dtype('>i2', gdal.GDT_Int16)

    def test_int32(self):
        self._check_dtype('<i4', gdal.GDT_Int32)

    def test_int32_big_endian(self):
        self._check_dtype('>i4', gdal.GDT_Int32)

    def test_uint8(self):
        self._check_dtype('u1', gdal.GDT_Byte)

    def test_uint16(self):
        self._check_dtype('<u2', gdal.GDT_UInt16)

    def test_uint16_big_endian(self):
        self._check_dtype('>u2', gdal.GDT_UInt16)

    def test_uint32(self):
        self._check_dtype('<u4', gdal.GDT_UInt32)

    def test_uint32_big_endian(self):
        self._check_dtype('>u4', gdal.GDT_UInt32)

    def test_float32(self):
        self._check_dtype('<f4', gdal.GDT_Float32)

    def test_float32_big_endian(self):
        self._check_dtype('>f4', gdal.GDT_Float32)

    def test_float64(self):
        self._check_dtype('<f8', gdal.GDT_Float64)

    def test_float64_big_endian(self):
        self._check_dtype('>f8', gdal.GDT_Float64)

    def test_invalid(self):
        cube = self._cube('i1')
        with self.assertRaises(ValueError):
            with self.temp_filename('.tif') as temp_filename:
                export_geotiff(cube, temp_filename)


class TestProjection(tests.IrisTest):
    def _cube(self, ellipsoid=None):
        data = np.arange(12).reshape(3, 4).astype('u1')
        cube = Cube(data, 'air_pressure_anomaly')
        coord = DimCoord(np.arange(3), 'latitude', units='degrees',
                         coord_system=ellipsoid)
        coord.guess_bounds()
        cube.add_dim_coord(coord, 0)
        coord = DimCoord(np.arange(4), 'longitude', units='degrees',
                         coord_system=ellipsoid)
        coord.guess_bounds()
        cube.add_dim_coord(coord, 1)
        return cube

    def test_no_ellipsoid(self):
        cube = self._cube()
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)
            dataset = gdal.Open(temp_filename, gdal.GA_ReadOnly)
            self.assertEqual(dataset.GetProjection(), '')

    def test_sphere(self):
        cube = self._cube(GeogCS(6377000))
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)
            dataset = gdal.Open(temp_filename, gdal.GA_ReadOnly)
            projection_string = dataset.GetProjection()
            # String has embedded floating point values,
            # Test with values to N decimal places, using a regular expression.
            re_pattern = (
                r'GEOGCS\["unnamed ellipse",DATUM\["unknown",'
                r'SPHEROID\["unnamed",637....,0\]\],PRIMEM\["Greenwich",0\],'
                r'UNIT\["degree",0.01745[0-9]*\]\]')
            re_exp = re.compile(re_pattern)
            self.assertIsNotNone(
                re_exp.match(projection_string),
                'projection string {!r} does not match {!r}'.format(
                    projection_string, re_pattern))

    def test_ellipsoid(self):
        cube = self._cube(GeogCS(6377000, 6360000))
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)
            dataset = gdal.Open(temp_filename, gdal.GA_ReadOnly)
            projection_string = dataset.GetProjection()
            # String has embedded floating point values,
            # Test with values to N decimal places, using a regular expression.
            re_pattern = (
                r'GEOGCS\["unnamed ellipse",DATUM\["unknown",'
                r'SPHEROID\["unnamed",637....,375.117[0-9]*\]\],'
                r'PRIMEM\["Greenwich",0\],UNIT\["degree",0.01745[0-9]*\]\]')
            re_exp = re.compile(re_pattern)
            self.assertIsNotNone(
                re_exp.match(projection_string),
                'projection string {!r} does not match {!r}'.format(
                    projection_string, re_pattern))


class TestGeoTransform(tests.IrisTest):
    def test_(self):
        data = np.arange(12).reshape(3, 4).astype(np.uint8)
        cube = Cube(data, 'air_pressure_anomaly')
        coord = DimCoord([30, 40, 50], 'latitude', units='degrees')
        coord.guess_bounds()
        cube.add_dim_coord(coord, 0)
        coord = DimCoord([-10, -5, 0, 5], 'longitude', units='degrees')
        coord.guess_bounds()
        cube.add_dim_coord(coord, 1)
        with self.temp_filename('.tif') as temp_filename:
            export_geotiff(cube, temp_filename)
            dataset = gdal.Open(temp_filename, gdal.GA_ReadOnly)
            self.assertEqual(dataset.GetGeoTransform(),
                             (-12.5, 5, 0, 55, 0, -10))


if __name__ == "__main__":
    tests.main()
