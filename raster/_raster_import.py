# (C) British Crown Copyright 2015 - 2018, Met Office
# Refer to README.md of this project for license details.
#
# This file is part of ANTS.
"""
Module for importing raster data to Iris cubes using the GDAL library.

See also: `GDAL - Geospatial Data Abstraction Library <http://www.gdal.org>`_.

"""
import copy
import warnings

import ants
import ants.coord_systems as acoord
import biggus
from gdalconst import GA_ReadOnly
import numpy as np
from osgeo import gdal, osr
import iris.coord_systems


from ._raster import _GDAL_DATATYPES


class _GdalDataProxy(object):
    """A reference to the data payload of a single gdal raster band."""

    __slots__ = ('shape', 'dtype', 'path', 'raster_band_index', 'fill_value')

    def __init__(self, shape, dtype, path, raster_band_index, fill_value):
        # Convert to numpy y-x order (gdal uses and always assumes x-y
        # ordering)
        if len(shape) != 2:
            raise ValueError('Raster image shape describes {} dimensions, '
                             'expecting 2 dimensions'.format(len(shape)))
        self.shape = shape[::-1]
        # Ensure that we always return signed data - CF compliance
        #     - this should be handled in iris netcdf at some point, handling
        #       the saving of netcdf3 output properly (auto type-casting etc.)
        dtype = np.dtype(dtype)
        if dtype.name.startswith('uint'):
            dtype = np.dtype(np.typeDict[dtype.num + 1])
        self.dtype = dtype
        self.path = path
        self.raster_band_index = raster_band_index

        self.fill_value = np.ma.array(0, self.dtype).fill_value
        if fill_value is not None and fill_value is not np.nan:
            self.fill_value = np.array(fill_value, dtype)

    @property
    def ndim(self):
        return len(self.shape)

    def __getitem__(self, keys):
        def _offset_winsize(key, size):
            # Handle slices
            if hasattr(key, '__iter__'):
                slices = ants.utils.ndarray.group_indices(key)
                if len(slices) > 1:
                    msg = 'Currently no support for discontiguous extraction.'
                    raise ValueError(msg)
                key = slices[0]

            if isinstance(key, slice):
                if key.step not in (None, 1):
                    raise IndexError('Step size not currently supported for '
                                     'gdal indexing')
                wstart = key.start or 0
                wstop = key.stop if key.stop is not None else size

                # Convert Python slice notation to an offest and size
                if wstart < 0:
                    wstart += size
                if wstop < 0:
                    wstop += size
                wstop = min(wstop, size)
                wsize = wstop - wstart

                z_offset = wstart
                z_winsize = wsize
            else:
                if key < 0 or key >= size:
                    raise IndexError('Raster index out of range')
                z_offset = key
                z_winsize = 1
            return (z_offset, z_winsize)

        xind, yind = 1, 0
        if keys:
            x_offset, x_winsize = _offset_winsize(keys[xind], self.shape[xind])
            y_offset, y_winsize = _offset_winsize(keys[yind], self.shape[yind])
            # Note that gdal y-indexing is opposite
            y_offset = (self.shape[yind] - y_offset) - y_winsize
        else:
            x_offset = 0
            x_winsize = self.shape[xind]
            y_offset = 0
            y_winsize = self.shape[yind]

        dataset = gdal.Open(self.path, GA_ReadOnly)
        iband = dataset.GetRasterBand(self.raster_band_index+1)
        data = iband.ReadAsArray(x_offset, y_offset, x_winsize, y_winsize)
        # Again, y-indexing is opposite
        data = data[::-1, :]

        # Mask the array?
        if self.fill_value in data:
            data = np.ma.masked_values(data, self.fill_value, copy=False)
        # Ensure that we always return signed data - CF compliance
        if data.dtype.name.startswith('uint'):
            data = data.astype(data.dtype.name.lstrip('u'))
        return data

    def __repr__(self):
        fmt = '<{self.__class__.__name__} shape={self.shape}' \
              ' dtype={self.dtype!r} path={self.path!r}' \
              ' raster_band_index={self.raster_band_index!r}>'
        return fmt.format(self=self)

    def __getstate__(self):
        # Required to support pickling
        return [(name, getattr(self, name)) for name in self.__slots__]

    def __setstate__(self, state):
        # Required to support unpickling
        for (key, value) in state:
            setattr(self, key, value)


def _get_crs(projection):
    """
    Derive a suitable iris crs based on a supplied gdal projection.

    """
    crs = None
    if projection:
        srs = osr.SpatialReference(wkt=projection)
        srs.AutoIdentifyEPSG()
        try:
            # STAGE1: Identity via EPSG code
            epsg_code = int(srs.GetAuthorityCode(None))
            crs = acoord.EPSG_2_CRS[epsg_code]
        except (TypeError, KeyError):
            # STAGE2: Identify via name/proj4 parameters
            crs_name = srs.GetAttrValue('projcs')
            if crs_name:
                crs = acoord.Name2CRS.get_crs(crs_name)
            if crs is None:
                crs = acoord.Proj2CRS.get_crs(srs.ExportToProj4())
        if crs is None:
            msg = 'Projection information not currently in lookup table: {}'
            raise RuntimeError(msg.format(projection))
    return crs


def load_cubes(filenames, callback=None):
    """
    Imports raster images using gdal and constructs a cube.

    Parameters
    ----------
    filename : str/list
        Input file name(s).
    callback : callable function, optional
        Function which can be passed on to :func:`iris.io.run_callback`.

    Returns
    -------
    cube : iris.cube.Cube
        A 2D regularly gridded cube.  The resulting cube has regular,
        contiguous bounds.

    Notes
    -----
        Unsigned integers are loaded as signed integers.

    """
    def _coord(ax_dir, origin_xy, pixel_width, num_xy, crs):
        """Return an iris coordinate for the axis direction"""
        dim_info = dict(x=(0, None), y=(1, slice(None, None, -1)))

        ax_ind, aslice = dim_info[ax_dir]
        pnt_origin = origin_xy[ax_ind] + pixel_width[ax_ind]/2.
        points = np.arange(pnt_origin, pnt_origin +
                           pixel_width[ax_ind] * num_xy[ax_ind],
                           pixel_width[ax_ind])
        if aslice:
            points = points[aslice]

        if crs is not None:
            metadata = getattr(crs, ax_dir)
            coord = iris.coords.DimCoord(points,
                                         standard_name=metadata.standard_name,
                                         units=metadata.units,
                                         coord_system=copy.copy(crs.crs))
        else:
            standard_name = 'projection_{}_coordinate'.format(ax_dir.lower())
            coord = iris.coords.DimCoord(points, standard_name=standard_name)
        ants.utils.coord.guess_bounds(coord)
        return coord

    gdal.UseExceptions()

    if isinstance(filenames, basestring):
        filenames = [filenames]
    for fname in filenames:
        dataset = gdal.Open(fname, GA_ReadOnly)
        if dataset is None:
            raise IOError('gdal failed to open raster image')

        # Get metadata applies to all raster bands
        transform = dataset.GetGeoTransform()
        origin_xy = (transform[0], transform[3])
        num_xy = (dataset.RasterXSize, dataset.RasterYSize)

        # This effectively indicates the bounds of the cells.
        pixel_width = (transform[1], transform[5])
        num_raster = dataset.RasterCount
        if not num_raster:
            return

        # Position of North 0, 0 is north-up
        rotation = (transform[2], transform[4])
        if rotation[0] != 0 or rotation[1] != 0:
            msg = ('Rotation not supported: ({}, {})'.format(rotation[0],
                                                             rotation[1]))
            raise ValueError(msg)

        # http://www.gdal.org/gdal_datamodel.html
        projection = dataset.GetProjection()
        crs = _get_crs(projection)

        # Calculate coordinate points
        x = _coord('x', origin_xy, pixel_width, num_xy, crs)
        y = _coord('y', origin_xy, pixel_width, num_xy, crs)

        # Create proxy data for each raster band.
        for iraster in range(num_raster):
            iband = dataset.GetRasterBand(iraster+1)
            # BUG: Currently iris _GDAL_DATATYPES for gdal type byte is mapped
            # to u1, but u1 is lookup for an 8 bit unsigned integer.
            if iband.DataType == 1:
                dtype = np.dtype('byte')
            else:
                dtype = np.dtype(
                    [key for key, value in _GDAL_DATATYPES.items() if
                     value == iband.DataType][0])
            proxy = _GdalDataProxy(num_xy, dtype, fname, iraster,
                                   iband.GetNoDataValue())
            data = biggus.OrthoArrayAdapter(proxy)
            cube = iris.cube.Cube(data)
            cube.add_dim_coord(x, 1)
            cube.add_dim_coord(y, 0)

            # Perform any user registered callback function.
            cube = iris.io.run_callback(callback, cube, iband, fname)

            # Callback mechanism may return None, which must not be yielded
            if cube is None:
                continue

            yield cube
