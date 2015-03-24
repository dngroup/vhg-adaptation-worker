#!/usr/bin/env python

from setuptools import setup

setup(
    name='vhg-adaptation-worker',
    version='0.1',
    description='Worker for video adaptation',
    author='Nicolas Herbaut && David Bourasseau',
    author_email='nherbaut@labri.fr',
    packages=['adaptation'],
    install_requires=[
        "celery",
    ])

