#!/usr/bin/env python3

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

if __name__ == "__main__":
    print(add(2, 3)) # Should output 5
    print(subtract(5, 2)) # Should output 3
    print(multiply(4, 6)) # Should output 24
    print(divide(10, 2)) # Should output 5.0
