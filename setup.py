# (C) British Crown Copyright 2019, Met Office
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
          packages=find_packages(),
          classifiers=[
             'Development Status :: 3 - Alpha',
             'License :: OSI Approved :: LGPLv3 License',
             'Operating System :: MacOS :: MacOS X',
             'Operating System :: POSIX',
             'Operating System :: POSIX :: AIX',
             'Operating System :: POSIX :: Linux',
             'Operating System :: Microsoft :: Windows',
             'Programming Language :: Python',
             'Programming Language :: Python :: 2',
             'Programming Language :: Python :: 2.7',
             'Programming Language :: Python :: 3',
             'Programming Language :: Python :: 3.4',
             'Programming Language :: Python :: 3.5',
             'Topic :: Scientific/Engineering',
             'Topic :: Scientific/Engineering :: GIS'],
          )
