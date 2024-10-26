from setuptools import setup, find_packages

setup(
    name="pyftrace",
    version="0.1.0",
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

