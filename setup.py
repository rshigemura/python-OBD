#!/bin/env python
# -*- coding: utf8 -*-

from setuptools import setup, find_packages

setup(
    name="obd",
    version="0.4.1",
    description=("Serial module for handling live sensor data from a vehicle's OBD-II port"),
    classifiers=[
        "Operating System :: POSIX :: Linux",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Topic :: System :: Monitoring",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Development Status :: 3 - Alpha",
        "Topic :: System :: Logging",
        "Intended Audience :: Developers",
    ],
    keywords="obd obd-II obd-ii obd2 car serial vehicle diagnostic",
    author="Rafael Shigemura",
    author_email="rafael.shigemura@gmail.com",
    url="http://github.com/rshigemura/python-OBD",
    license="GNU GPLv2",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    #install_requires=["pyserial"],
)
