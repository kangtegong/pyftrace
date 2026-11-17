import sys
import os
import weakref
import dis
import fnmatch
import importlib.util

# A frame that returns or yields normally stops at one of these
EXIT_OPCODES = frozenset(
    dis.opmap[name]
    for name in ("RETURN_VALUE", "RETURN_CONST", "YIELD_VALUE", "RESUME")
    if name in dis.opmap
)
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

def callable_name(callable_obj):
    """
    Name a traced callable without calling into user code: str() and
    repr() may be overridden and can raise or have side effects.
    """
    name = getattr(callable_obj, '__name__', None)
    if isinstance(name, str):
        return name
    return type(callable_obj).__name__

def safe_str(value):
    """
    str() that cannot fail: __str__ of a traced object is user code.
    """
    try:
        return shorten(str(value))
    except Exception:
        return f"<unprintable {type(value).__name__}>"

# A value is cut off beyond this many characters
MAX_VALUE_LENGTH = 200

def shorten(text):
    """
    Fit a value into a line of trace: on a single line and not
    arbitrarily long.
    """
    text = " ".join(text.split())
    if len(text) > MAX_VALUE_LENGTH:
        text = text[:MAX_VALUE_LENGTH] + "..."
    return text

def format_exception(exception):
    """
    Describe an exception like the last line of a traceback does.
    """
    name = type(exception).__name__
    message = safe_str(exception)
    return f"{name}: {message}" if message else name

YIELD_FROM = dis.opmap.get("YIELD_FROM")

def is_unwinding(frame, retval):
    """
    sys.setprofile() reports an exception leaving a frame as a return
    of None.  Tell the two apart by the instruction the frame stopped at.
    """
    if retval is not None:
        return False
    code = frame.f_code.co_code
    if code[frame.f_lasti] in EXIT_OPCODES:
        return False
    # Up to Python 3.10, a frame suspended in 'await' or 'yield from'
    # is left pointing at the instruction before its YIELD_FROM.  One
    # that points at the YIELD_FROM itself had an exception come out of it.
    following = frame.f_lasti + 2
    return following >= len(code) or code[following] != YIELD_FROM

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


def normalize_patterns(patterns):
    """
    Prepare the paths given with -F and -E for path_matches().
    """
    return tuple(os.path.normcase(os.path.abspath(p)) for p in patterns or ())

def path_matches(path, patterns):
    """
    True if path is one of the patterns, lies in a directory that is,
    or matches one as a glob.
    """
    for pattern in patterns:
        if path == pattern or path.startswith(os.path.join(pattern, '')):
            return True
        if fnmatch.fnmatchcase(path, pattern):
            return True
    return False

def find_module_file(module_name):
    """
    Return the file that 'python -m module_name' would run, or None.
    """
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.submodule_search_locations is not None:
            spec = importlib.util.find_spec(module_name + ".__main__")
    except ImportError:
        return None
    if spec is None or not spec.has_location:
        return None
    return spec.origin


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
            return shorten(repr(value))
        except Exception:
            return f"<unreprable {type(value).__name__}>"

    for name in arg_names:
        if name in locals_:
            parts.append(f"{name}={safe_repr(locals_[name])}")
        else:
            parts.append(f"{name}=<unset>")

    return ", ".join(parts)

