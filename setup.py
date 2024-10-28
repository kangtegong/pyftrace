from setuptools import setup, find_packages
import os
import sys

def get_version():
    here = os.path.abspath(os.path.dirname(__file__))
    init_path = os.path.join(here, 'pyftrace', '__init__.py')
    with open(init_path, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                delim = '"' if '"' in line else "'"
                version = line.split(delim)[1]
                return version
    raise RuntimeError("Unable to find version string.")

setup(
    name="pyftrace",
    version=get_version(),
    description="Python function tracing tool.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Kang Minchul",
    author_email="tegongkang@gmail.com",
    url="https://github.com/kangtegong/pyftrace",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "pyftrace=pyftrace.main:main",
        ],
    },
    python_requires=">=3.12",
)

