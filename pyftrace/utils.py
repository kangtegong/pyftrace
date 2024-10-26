import sys
import os
import functools
import time

def get_site_packages_modules():
    site_packages_dirs = [d for d in sys.path if 'site-packages' in d]
    modules = set()
    for directory in site_packages_dirs:
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, name)):
                    modules.add(name.split('-')[0])
                elif name.endswith('.dist-info'):
                    modules.add(name.split('-')[0])
    return modules

def timeit(method):
    """
    Decorator to measure the execution time of methods.

    Args:
        method (callable): The method to be wrapped.

    Returns:
        callable: The wrapped method with timing.
    """
    @functools.wraps(method)
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        return result
    return timed

