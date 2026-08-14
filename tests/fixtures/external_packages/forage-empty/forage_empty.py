"""Foraging refusal fixture: no viable unary JSON-scalar candidate exists."""

CONSTANT = 7


class Greeter:
    def greet(self, name):
        return f"hello {name}"


def _private(text):
    return text
