import sys
import os
import weakref
from typing import List

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


def format_arguments(frame) -> str:
    """
    Safely format function arguments from the current frame.
    Falls back gracefully if arguments are unavailable.
    """
    if frame is None or frame.f_code is None:
        return ""

    code = frame.f_code
    arg_names: List[str] = []

    argcount = code.co_argcount
    kwonly = code.co_kwonlyargcount
    varnames = code.co_varnames

    # Positional-only + positional-or-keyword arguments
    for i in range(argcount):
        if i < len(varnames):
            arg_names.append(varnames[i])

    idx = argcount

    # *args
    has_varargs = bool(code.co_flags & 0x04)
    if has_varargs and idx < len(varnames):
        arg_names.append(varnames[idx])
        idx += 1

    # Keyword-only
    for i in range(kwonly):
        if idx < len(varnames):
            arg_names.append(varnames[idx])
            idx += 1

    # **kwargs
    has_varkw = bool(code.co_flags & 0x08)
    if has_varkw and idx < len(varnames):
        arg_names.append(varnames[idx])

    parts = []
    locals_ = frame.f_locals or {}

    def safe_repr(value):
        try:
            return repr(value)
        except Exception:
            return f"<unreprable {type(value).__name__}>"

    for name in arg_names:
        if name in locals_:
            parts.append(f"{name}={safe_repr(locals_[name])}")
        else:
            parts.append(f"{name}=<unset>")

    return ", ".join(parts)

