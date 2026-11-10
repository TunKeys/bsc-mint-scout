# bsc-mint-scout

Check whether a free mint is still live on BNB Smart Chain — by asking the
chain, not the website.

Mint pages lie. I have seen "500 spots left" on a page whose contract was
already sold out, and a "mint closed" banner on a contract that still
minted fine. This tool skips the frontend and runs read-only `eth_call`s
against the contract: `totalSupply`, your `balanceOf`, and a simulation of
each free-mint function with value 0. It prints one verdict and exits.

It never signs anything and never asks for a private key.

## Requirements

- Python 3.9+
- No dependencies (standard library only)

## Usage

```bash
# Supply only — no wallet needed
python3 mint_scout.py 0x01c106835091c09D5c69737631Af133530093C89 --max-supply 10000

# Full check: simulate the free mint from your wallet (read-only)
python3 mint_scout.py 0x01c106835091c09D5c69737631Af133530093C89 \
    --wallet 0xYourWalletAddress --max-supply 10000

# Machine-readable output
python3 mint_scout.py 0xYourContractAddress --wallet 0xYourWallet --json

# Use your own RPC instead of the public defaults
python3 mint_scout.py 0xYourContractAddress --rpc https://your-rpc.example
```

Example output:

```
contract:    0x01c106835091c09D5c69737631Af133530093C89
totalSupply: 5656 / 10000
remaining:   4344
balanceOf:   0 (wallet 0x12345678...)
free path:   mint()
verdict:     FREE MINT LIVE via mint()
```

## Why `--wallet` matters

Many mints gate on the caller (Agent ID, allowlist, per-wallet quota), so
simulating from the zero address gives false negatives. Without `--wallet`
the tool reports supply only and says so plainly instead of guessing.

## How the free-mint simulation works

It tries each candidate in order and reports the first one that does not
revert (all with value 0):

1. `mint(uint256)` with amount 1
2. `mint()`
3. `freeMint()`
4. `claimFree()`
5. `claim()`

Function names lie — `freeMint()` often reverts while plain `mint()` with
value 0 is the real free path. That is why the order above exists.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `FREE MINT LIVE via <fn>` | The named function simulates OK from your wallet |
| `SOLD OUT` | `totalSupply` reached `--max-supply` |
| `FREE MINT CLOSED` | Every free path reverts from your wallet |
| `NOT SIMULATED` | No `--wallet` was given, so no simulation ran |
| `NOT A MINT CONTRACT` | The contract has no `totalSupply` |

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Roadmap

- [ ] `--watch` mode: poll every N minutes until a mint opens
- [ ] Multi-chain support (Base, Ethereum)
- [ ] Detect the free quota per wallet (`mintedBy` / `MAX_PER_WALLET`)

## License

MIT — see [LICENSE](LICENSE).
