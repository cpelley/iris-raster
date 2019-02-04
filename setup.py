from __future__ import absolute_import, division, print_function

from setuptools import setup, find_packages
import os


DIR = os.path.abspath(os.path.dirname(__file__))
NAME = 'raster'


def extract_version():
    version = None
    fname = os.path.join(DIR, NAME, '__init__.py')
    with open(fname) as fd:
        for line in fd:
            if (line.startswith('__version__')):
                _, version = line.split('=')
                version = version.strip()[1:-1]  # Remove quotations
                break
    return version


if __name__ == '__main__':
    setup(name=NAME,
          description=('An iris extension to import and export raster data '
                       'using the GDAL library.'),
          version=extract_version(),
          packages=find_packages())
