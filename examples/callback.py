def square(n):
    return n * n

def total(values):
    return sum(map(square, values))

total([1, 2])
