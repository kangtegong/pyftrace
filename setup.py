from setuptools import setup, find_packages
import os
import sys

def get_version():
    with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'pyftrace', '__init__.py'), 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('"' if '"' in line else "'")[1]
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
    install_requires=[
    ],
    extras_require={
        ":sys_platform == 'win32'": ["windows-curses"]
    },
    python_requires=">=3.8",
)
