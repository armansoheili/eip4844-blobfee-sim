# eip4844-blobfee-sim

EIP-4844 blob gas fee simulator in pure Python — no dependencies.

Implements the Cancun blob fee market exactly as specified:

- Each blob costs `131072` blob gas; target is 3 blobs/block, cap is 6.
- The blob base fee is `fake_exponential(1, excess_blob_gas, 3338477)` —
  an integer Taylor-series approximation of `e ** (excess / 3338477)`, so
  the fee sits at 1 wei while the chain runs at or below target and grows
  exponentially under sustained congestion.
- Excess blob gas carries over block to block:
  `new_excess = max(0, parent_excess + parent_blob_gas_used - target)`.
- A blob transaction's data-gas cost is
  `blob_count * 131072 * blob_base_fee`.

## Usage

```bash
python blobfee.py --demo   # fee trajectories: steady / full / surge-then-silence
python blobfee.py --test   # 22 doctests
```

```python
from blobfee import BlobFeeSimulator, blob_tx_cost

sim = BlobFeeSimulator()
sim.run([6] * 6)          # six full blocks
sim.fee()                 # blob base fee in wei per blob gas
blob_tx_cost(2, sim.fee())  # data-gas cost of a 2-blob transaction
```

## What the demo shows

- At target (3 blobs/block) the fee never moves off 1 wei.
- Full blocks (6 blobs/block) push excess up slowly — the fee only reaches
  2 wei after five full blocks, because the update fraction is large.
- After a surge, empty blocks drain excess back to zero and the fee
  collapses just as fast as it rose.
