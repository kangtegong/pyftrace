import sys
import os
import weakref

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

def find_import_end_line(script_path):
    """
    Finds the last line number of import statements in the script.
    """
    import_line_numbers = []
    with open(script_path, 'r') as f:
        for lineno, line in enumerate(f, 1):
            stripped_line = line.strip()
            if stripped_line.startswith('import ') or stripped_line.startswith('from '):
                import_line_numbers.append(lineno)
    if import_line_numbers:
        return max(import_line_numbers)
    else:
        return 0

