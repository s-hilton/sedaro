# DATA STRUCTURE

import doctest


class QRangeStore:
    """
    A Q-Range KV Store mapping left-inclusive, right-exclusive ranges [low, high) to values.
    Reading from the store returns the collection of values whose ranges contain the query.
    ```
    0  1  2  3  4  5  6  7  8  9
    [A      )[B)            [E)
    [C   )[D   )
           ^       ^        ^  ^
    ```
    >>> store = QRangeStore()
    >>> store[0, 3] = 'Record A'
    >>> store[3, 4] = 'Record B'
    >>> store[0, 2] = 'Record C'
    >>> store[2, 4] = 'Record D'
    >>> store[8, 9] = 'Record E'
    >>> store[2, 0] = 'Record F'
    Traceback (most recent call last):
    IndexError: Invalid Range.
    >>> store[2.1]
    ['Record A', 'Record D']
    >>> store[8]
    ['Record E']
    >>> store[5]
    Traceback (most recent call last):
    IndexError: Not found.
    >>> store[9]
    Traceback (most recent call last):
    IndexError: Not found.
    """

    def __init__(self):
        self.store = []

    def __setitem__(self, rng, value):
        try:
            (low, high) = rng
        except (TypeError, ValueError):
            raise IndexError("Invalid Range: must provide a low and high value.")
        if not low < high:
            raise IndexError("Invalid Range.")
        self.store.append((low, high, value))

    def __getitem__(self, key):
        ret = [v for (l, h, v) in self.store if l <= key < h]
        if not ret:
            raise IndexError("Not found.")
        return ret

    def ending_at_or_after(self, key):
        """
        Return the values whose ranges satisfy `low < key <= high`, i.e. treating each range as
        left-exclusive and right-inclusive. When consecutive ranges [t0, t1), [t1, t2), ... hold
        the value reached at the *end* of each range, this is the value current at exactly `key`.
        ```
        0  1  2  3
        [A   )[B   )
              ^
        ```
        >>> store = QRangeStore()
        >>> store[0, 2] = 'Record A'
        >>> store[2, 4] = 'Record B'
        >>> store.ending_at_or_after(2)
        ['Record A']
        >>> store.ending_at_or_after(2.0000001)
        ['Record B']
        >>> store.ending_at_or_after(0)
        Traceback (most recent call last):
        IndexError: Not found.
        """
        ret = [v for (l, h, v) in self.store if l < key <= h]
        if not ret:
            raise IndexError("Not found.")
        return ret

    def __len__(self):
        return len(self.store)


doctest.testmod()
