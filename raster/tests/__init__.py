# (C) British Crown Copyright 2019, Met Office
from __future__ import (absolute_import, division, print_function)
from six.moves import (filter, input, map, range, zip)  # noqa

import os


iris.tests._RESULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'results')
