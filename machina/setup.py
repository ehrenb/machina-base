from setuptools import setup, find_packages
from os import path

setup(
    name='machina',
    version='0.1',
    description='A scalable analysis pipeline',
    author='',
    author_email='behren2@protonmail.com',
    keywords='machina',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    python_requires='>=3.5',
    include_package_data=True,
    zip_safe=False # force eggs to be unzipped, otherwise mkdocstrings will fail when looking for module source (if the pkg was zipped into an egg)
)
