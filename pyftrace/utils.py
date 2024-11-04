import sys
import os
import weakref

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

def resolve_filename(code, callable_obj):
    filename = ''
    if code and code.co_filename:
        filename = code.co_filename
        if filename.startswith('<frozen ') and filename.endswith('>'):
            module_name = filename[len('<frozen '):-1]
            module = sys.modules.get(module_name)
            if module and hasattr(module, '__file__'):
                filename = module.__file__
    if not filename and callable_obj:
        if isinstance(callable_obj, weakref.ReferenceType):
            callable_obj = callable_obj()
        module_name = getattr(callable_obj, '__module__', None)
        if module_name:
            module = sys.modules.get(module_name)
            if module and hasattr(module, '__file__'):
                filename = module.__file__
    return filename

def get_line_number(code, instruction_offset):
    if code is None:
        return 0
    for start, end, lineno in code.co_lines():
        if start <= instruction_offset < end:
            return lineno
    return code.co_firstlineno

