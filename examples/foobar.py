def foo(x, y):
    bar(x)
    bar(y)
    return x + y

def bar(value):
    return value * 2

foo(3, 7)
