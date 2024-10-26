def foo():
    bar()
    bar()
    return 10

def bar():
    return 20

foo()
