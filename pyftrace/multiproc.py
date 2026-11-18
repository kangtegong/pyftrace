"""
Follow the traced program into the processes it starts through
multiprocessing.

A forked process inherits the tracer.  A process started with the
spawn or forkserver method is a new interpreter that knows nothing
about pyftrace, so the tracer's settings are sent along with the data
multiprocessing passes to it.
"""
import multiprocessing.process
import multiprocessing.spawn

# The tracer of this process
active_tracer = None

class Stowaway:
    """
    Travels inside multiprocessing's preparation data.  Unpickling it
    in the new process is what sets the tracer up there.
    """
    def __init__(self, config):
        self.config = config

    def __getstate__(self):
        return self.config

    def __setstate__(self, config):
        # Imported late: tracer.py imports this module
        from .tracer import tracer_from_config

        self.config = config
        follow(tracer_from_config(config))

def follow(tracer):
    """
    Make every process started from this one trace itself.
    """
    global active_tracer

    active_tracer = tracer
    if getattr(multiprocessing.process.BaseProcess._bootstrap, "traced", False):
        return

    original_bootstrap = multiprocessing.process.BaseProcess._bootstrap
    original_preparation = multiprocessing.spawn.get_preparation_data

    def bootstrap(self, *args, **kwargs):
        # Runs in the child: this is where the process does its work
        active_tracer.start_child()
        try:
            return original_bootstrap(self, *args, **kwargs)
        finally:
            active_tracer.finish_child()

    def get_preparation_data(name):
        data = original_preparation(name)
        data["pyftrace"] = Stowaway(active_tracer.child_config())
        return data

    bootstrap.traced = True
    multiprocessing.process.BaseProcess._bootstrap = bootstrap
    multiprocessing.spawn.get_preparation_data = get_preparation_data
