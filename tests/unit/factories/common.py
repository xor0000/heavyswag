import random
import string


def generate_random_string(length: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))  # noqa: S311
