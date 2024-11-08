import sys

if sys.version_info >= (3, 12):
    from .tracer_monitoring import PyftraceMonitoring as Pyftrace
else:
    from .tracer_settrace import PyftraceSettrace as Pyftrace

