def numbers():
    yield 1
    yield 2

def show(n):
    return n

for n in numbers():
    show(n)
