# (C) British Crown Copyright 2019, Met Office
from __future__ import (absolute_import, division, print_function)
from six.moves import (filter, input, map, range, zip)  # noqa

import gdal
import iris
import iris.fileformats as ifmt

from ._raster import export_geotiff
from ._raster_import import load_cubes


__version__ = '0.1.dev0'


class _GdalIdentify(iris.io.format_picker.FileElement):
    """A :class:`FileElement` that queries 'gdalinfo' for the file."""
    def get_element(self, basename, file_handle):
        result = False
        if gdal is not None:
            result = True
            gdal.UseExceptions()
            try:
                gdal.Open(file_handle.name)
            except RuntimeError as err:
                if 'not recognized as a supported file format' in err.args[0]:
                    result = False
        return result


ifmt.FORMAT_AGENT.add_spec(
    ifmt.FormatSpecification('gdal', _GdalIdentify(), True,
                             load_cubes, priority=2,
                             constraint_aware_handler=False))
