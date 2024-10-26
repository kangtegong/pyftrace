def foo():
    result1 = bar()
    result2 = baz()
    return result1 + result2

def bar():
    result = qux()
    return result * 2

def baz():
    result = quux()
    return result - 5

def qux():
    return corge()

def quux():
    return 30

def corge():
    return 10

# Main call
foo()

