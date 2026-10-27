"""EIP-4844 blob gas fee simulator in pure Python.

Implements the Cancun blob fee market exactly as specified in EIP-4844:

* Each blob costs ``GAS_PER_BLOB = 131072`` blob gas.
* Target: ``TARGET_BLOB_GAS_PER_BLOCK = 3`` blobs per block.
* Cap: ``MAX_BLOB_GAS_PER_BLOCK = 6`` blobs per block.
* The blob base fee for a block is ``fake_exponential(1, excess_blob_gas,
  3338477)`` -- a Taylor-series approximation of ``e ** (excess / 3338477)``
  in integer arithmetic, so the fee stays at 1 wei while the chain is at or
  below target and grows exponentially once blobs pile up.
* Excess blob gas carries over: ``new_excess = max(0, parent_excess +
  parent_blob_gas_used - TARGET_BLOB_GAS_PER_BLOCK)``.

A blob transaction's data-gas cost is simply
``blob_count * GAS_PER_BLOB * blob_base_fee``.

Run ``python blobfee.py --demo`` for a fee trajectory, or
``python blobfee.py --test`` for the doctests.
"""

import argparse

GAS_PER_BLOB = 131072
TARGET_BLOBS_PER_BLOCK = 3
TARGET_BLOB_GAS_PER_BLOCK = TARGET_BLOBS_PER_BLOCK * GAS_PER_BLOB
MAX_BLOBS_PER_BLOCK = 6
MAX_BLOB_GAS_PER_BLOCK = MAX_BLOBS_PER_BLOCK * GAS_PER_BLOB
BLOB_BASE_FEE_UPDATE_FRACTION = 3338477
MIN_BLOB_BASE_FEE = 1


def fake_exponential(factor, numerator, denominator):
    """Integer approximation of ``factor * e ** (numerator / denominator)``.

    The Taylor series is evaluated until the terms vanish, exactly as in
    EIP-4844's reference implementation.

    >>> fake_exponential(1, 0, 3338477)
    1
    >>> fake_exponential(1, 3338477, 3338477)  # e**1, truncated
    2
    >>> fake_exponential(1, 2 * 3338477, 3338477)  # e**2, truncated
    7
    """
    i = 1
    output = 0
    numerator_accum = factor * denominator
    while numerator_accum > 0:
        output += numerator_accum
        numerator_accum = (numerator_accum * numerator) // (denominator * i)
        i += 1
    return output // denominator


def calc_blob_fee(excess_blob_gas):
    """Blob base fee (wei per blob gas) for a block with this excess.

    >>> calc_blob_fee(0)
    1
    >>> calc_blob_fee(393216)  # one full block of excess over target
    1
    >>> calc_blob_fee(3932160)  # ten blocks of full excess
    3
    >>> calc_blob_fee(39321600)  # sustained congestion: fee explodes
    130392
    """
    return fake_exponential(MIN_BLOB_BASE_FEE, excess_blob_gas,
                            BLOB_BASE_FEE_UPDATE_FRACTION)


def update_excess(parent_excess, parent_blob_gas_used):
    """Excess blob gas carried into the next block (floored at zero).

    >>> update_excess(0, 0)
    0
    >>> update_excess(0, 786432)  # full block: 6 blobs, target 3
    393216
    >>> update_excess(393216, 0)  # empty block drains one target's worth
    0
    >>> update_excess(1000000, 131072)  # partial drain
    737856
    """
    return max(0, parent_excess + parent_blob_gas_used
               - TARGET_BLOB_GAS_PER_BLOCK)


def blob_tx_cost(blob_count, blob_base_fee):
    """Data-gas cost (wei) of a blob transaction at the given fee.

    >>> blob_tx_cost(1, 1)
    131072
    >>> blob_tx_cost(6, 1)
    786432
    >>> blob_tx_cost(2, 1000)
    262144000
    """
    if not 0 <= blob_count <= MAX_BLOBS_PER_BLOCK:
        raise ValueError(
            "blob_count %r outside 0..%d (per-transaction cap is 6 in Cancun)"
            % (blob_count, MAX_BLOBS_PER_BLOCK))
    return blob_count * GAS_PER_BLOB * blob_base_fee


class BlobFeeSimulator:
    """Walk a chain of blocks, tracking excess blob gas and the fee.

    >>> sim = BlobFeeSimulator()
    >>> sim.fee()
    1
    >>> sim.step(0)  # empty block: nothing changes
    1
    >>> sim.step(6)  # full block pushes excess up by one target
    1
    >>> sim.step(6)
    1
    >>> sim.excess
    786432
    >>> sim.step(0)  # empty block drains excess back toward zero
    1
    >>> sim.excess
    393216
    """

    def __init__(self, excess=0):
        self.excess = excess
        self.blocks = []

    def fee(self):
        """Current blob base fee in wei per blob gas."""
        return calc_blob_fee(self.excess)

    def step(self, blob_count):
        """Apply one block carrying ``blob_count`` blobs; return the new fee.

        ``blob_count`` must fit in one block (0..6).
        """
        if not 0 <= blob_count <= MAX_BLOBS_PER_BLOCK:
            raise ValueError("blob_count %r outside 0..%d"
                             % (blob_count, MAX_BLOBS_PER_BLOCK))
        self.excess = update_excess(self.excess,
                                    blob_count * GAS_PER_BLOB)
        self.blocks.append(blob_count)
        return self.fee()

    def run(self, blob_counts):
        """Apply a list of per-block blob counts; return the fee trajectory."""
        return [self.step(n) for n in blob_counts]


def demo():
    """Fee trajectory under a blob surge, then a quiet period."""
    scenarios = {
        "steady at target (3 blobs/block)": [3] * 8,
        "full blocks (6 blobs/block)": [6] * 8,
        "surge then silence": [6] * 6 + [0] * 6,
    }
    for name, counts in scenarios.items():
        sim = BlobFeeSimulator()
        fees = sim.run(counts)
        print("%s:" % name)
        print("  blobs/block: %s" % counts)
        print("  blob base fee (wei/blob gas): %s" % fees)
        print("  final excess blob gas: %d" % sim.excess)
    print("Cost of a 2-blob tx at 1 wei/blob gas: %d wei"
          % blob_tx_cost(2, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        import doctest
        results = doctest.testmod()
        print("doctests: %d passed, %d failed"
              % (results.attempted - results.failed, results.failed))
        raise SystemExit(1 if results.failed else 0)
    demo()


if __name__ == "__main__":
    main()
