"""
lib.probability
~~~~~~~~~~~~~~~

This module contains functions for working with probability.
"""

__all__ = [
    "num_compositions",
    "random_composition",
    "random_iv_sum",
    "random_iv_composition",
]

import random
from functools import cache


@cache
def num_compositions(n: int, k: int, *, lower_bound: int = 0, upper_bound: int = float("inf")) -> int:
    """Computes the number of k-compositions of n, where each element of the
    composition is in the range [lower_bound, upper_bound].

    If lower_bound and upper_bound are not specified, they default to 0 and n.

    >>> num_compositions(3, 2)  # (0, 3), (1, 2), (2, 1), (3, 0)
    4
    >>> num_compositions(120, 6)
    234531275
    >>> num_compositions(120, 6, upper_bound=31)
    9565682
    """
    if k <= 0:
        return int(k == n == 0)
    return sum(
        num_compositions(n - i, k - 1, lower_bound=lower_bound, upper_bound=upper_bound)
        for i in range(max(lower_bound, 0), min(n, upper_bound) + 1)
    )


def random_composition(n: int, k: int, *, lower_bound: int = 0, upper_bound: int = float("inf")) -> list[int]:
    """Returns a random k-composition of n, where each element of the
    composition is in the range [lower_bound, upper_bound].

    Each composition has equal probability of being chosen. If lower_bound and
    upper_bound are not specified, they default to 0 and n.

    >>> random.seed(0)
    >>> random_composition(3, 2)
    [3, 0]
    >>> random_composition(120, 6)
    [12, 7, 21, 18, 49, 13]
    >>> random_composition(120, 6, upper_bound=31)
    [21, 23, 29, 16, 9, 22]
    """
    if n == k == 0:
        return []

    # First, randomly choose the first element of the composition.
    # To maintain uniformity, we weight each choice by the number of
    # compositions that would be possible if that choice were made.

    kwargs = {"lower_bound": lower_bound, "upper_bound": upper_bound}
    head_choices = range(lower_bound, min(n, upper_bound) + 1)
    head_weights = [num_compositions(n - i, k - 1, **kwargs) for i in head_choices]
    head = random.choices(population=head_choices, weights=head_weights)[0]

    # Now, recursively choose the remaining elements.
    return [head, *random_composition(n - head, k - 1, **kwargs)]


def random_iv_sum(*, lower_bound: int = 0, upper_bound: int = 186) -> int:
    """Returns a random IV sum in the range [lower_bound, upper_bound], weighted
    by the number of ways to achieve that IV as the sum of 6 individual IVs,
    where each individual IV is in the range [0, 31].

    If lower_bound and upper_bound are not specified, they default to 0 and 186.
    """
    choices = range(lower_bound, min(upper_bound, 186) + 1)
    weights = [num_compositions(i, 6, upper_bound=31) for i in choices]
    return random.choices(population=choices, weights=weights)[0]


def random_iv_composition(*, sum_lower_bound: int = 0, sum_upper_bound: int = 186) -> list[int]:
    """Returns a random IV composition, where each element of the composition is
    in the range [0, 31], and the sum of the composition is in the range
    [sum_lower_bound, sum_upper_bound].

    Each composition has equal probability of being chosen. If sum_lower_bound
    and sum_upper_bound are not specified, they default to 0 and 186.
    """
    if sum_lower_bound == 0 and sum_upper_bound == 186:
        # If no bounds are specified, we can just choose each IV randomly.
        return random.choices(range(32), k=6)
    total = random_iv_sum(lower_bound=sum_lower_bound, upper_bound=sum_upper_bound)
    return random_composition(total, 6, upper_bound=31)
