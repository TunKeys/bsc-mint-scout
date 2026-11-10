#!/usr/bin/env python3
"""bsc-mint-scout: check whether a free mint is still live on BNB Smart Chain.

A mint page can say "500 spots left" while the contract is already sold
out. This tool skips the website and asks the chain directly, using
read-only eth_call. It never signs anything and never asks for keys.

Usage:
    python3 mint_scout.py 0xYourContractAddress [--wallet 0xYourWallet]
    python3 mint_scout.py 0xYourContractAddress --max-supply 10000 --json

Pass --wallet to simulate the free mint from your address. The wallet
matters: many mints gate on the caller (Agent ID, allowlist, quota),
so without it the tool reports supply only and skips the simulation
rather than guessing from the zero address.

Requires Python 3.9+ and nothing else (standard library only).
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

# Function selectors (first 4 bytes of keccak256 of the signature).
# Verified against keccak256; kept as constants so the tool stays
# dependency-free.
SELECTORS = {
    "totalSupply()": "18160ddd",
    "balanceOf(address)": "70a08231",
    "mint(uint256)": "a0712d68",
    "mint()": "1249c58b",
    "freeMint()": "5b70ea9f",
    "claimFree()": "f366afc9",
    "claim()": "4e71d92d",
}

# Free-mint candidates, tried in order. The first one that does not
# revert is the working free path. (Function names lie: freeMint()
# often reverts while plain mint() with value 0 is the real free path.)
FREE_CANDIDATES = [
    ("mint(uint256)", 1),
    ("mint()", None),
    ("freeMint()", None),
    ("claimFree()", None),
    ("claim()", None),
]

DEFAULT_RPCS = [
    "https://bsc-dataseed1.bnbchain.org",
    "https://bsc-dataseed2.bnbchain.org",
    "https://bsc-dataseed3.bnbchain.org",
    "https://rpc-bsc.48.club",
]


def encode_address(address: str) -> str:
    """Encode an address as a 32-byte ABI word (hex, no 0x)."""
    addr = address.lower().removeprefix("0x")
    if len(addr) != 40 or any(c not in "0123456789abcdef" for c in addr):
        raise ValueError(f"not an address: {address}")
    return "0" * 24 + addr


def encode_uint(value: int) -> str:
    """Encode an integer as a 32-byte ABI word (hex, no 0x)."""
    if value < 0 or value >= 1 << 256:
        raise ValueError(f"uint256 out of range: {value}")
    return f"{value:064x}"


def decode_uint(data: str) -> int:
    """Decode an ABI uint256 return value."""
    data = data.removeprefix("0x")
    if len(data) < 64:
        raise ValueError(f"short return data: {data!r}")
    return int(data[-64:], 16)


def build_calldata(signature: str, args: list[str]) -> str:
    """Build calldata: 0x + selector + encoded args."""
    return "0x" + SELECTORS[signature] + "".join(args)


def eth_call(rpc: str, to: str, data: str, from_addr: str | None = None) -> str:
    """One eth_call. Returns the raw hex result.

    Raises RuntimeError on transport errors and ValueError when the
    call reverts (the node returns an error object for reverts).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }
    if from_addr:
        payload["params"][0]["from"] = from_addr
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        rpc, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.load(resp)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"RPC {rpc} unreachable: {exc}") from exc
    if "error" in result:
        raise ValueError(result["error"].get("message", "call reverted"))
    return result.get("result", "0x")


def call_with_fallback(rpcs: list[str], to: str, data: str,
                       from_addr: str | None = None) -> tuple[str, str]:
    """Try each RPC in order; return (result, rpc_used)."""
    last_error: Exception | None = None
    for rpc in rpcs:
        try:
            return eth_call(rpc, to, data, from_addr), rpc
        except RuntimeError as exc:
            last_error = exc
    raise RuntimeError(f"all RPCs failed (last: {last_error})")


def read_uint(rpcs: list[str], contract: str, signature: str,
              args: list[str], from_addr: str | None = None) -> int | None:
    """Call a uint-returning view function; None if it does not exist."""
    data = build_calldata(signature, args)
    try:
        result, _ = call_with_fallback(rpcs, contract, data, from_addr)
    except (ValueError, RuntimeError):
        return None
    try:
        return decode_uint(result)
    except ValueError:
        return None


def simulate_free_mint(rpcs: list[str], contract: str,
                       wallet: str) -> tuple[str | None, str | None]:
    """Find a working free-mint path. Returns (function, rpc) or (None, None)."""
    for signature, amount in FREE_CANDIDATES:
        args = [encode_uint(amount)] if amount is not None else []
        data = build_calldata(signature, args)
        try:
            _, rpc = call_with_fallback(rpcs, contract, data, wallet)
            return signature, rpc
        except (ValueError, RuntimeError):
            continue
    return None, None


def verdict(supply: int | None, max_supply: int | None,
            free_fn: str | None, balance: int | None,
            simulated: bool) -> str:
    """One-line verdict from the on-chain facts."""
    if supply is None:
        return "NOT A MINT CONTRACT (no totalSupply)"
    if max_supply is not None and supply >= max_supply:
        return "SOLD OUT"
    if not simulated:
        return "NOT SIMULATED (pass --wallet to check the free path)"
    if free_fn is None:
        return "FREE MINT CLOSED (every free path reverts)"
    if balance is not None and balance > 0:
        return f"FREE MINT LIVE via {free_fn} (already hold {balance})"
    return f"FREE MINT LIVE via {free_fn}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a free mint is still live on BSC.")
    parser.add_argument("contract", help="NFT contract address (0x...)")
    parser.add_argument("--wallet", default=None,
                        help="wallet to simulate from (0x...); "
                             "read-only, no signing")
    parser.add_argument("--max-supply", type=int, default=None,
                        help="max supply, to show remaining spots")
    parser.add_argument("--rpc", action="append", default=None,
                        help="RPC endpoint (repeatable; defaults to "
                             "public BSC endpoints)")
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON")
    args = parser.parse_args(argv)

    rpcs = args.rpc or DEFAULT_RPCS
    contract = args.contract

    # The wallet matters: many mints gate on the caller (Agent ID,
    # allowlist, per-wallet quota), so simulating from the zero address
    # gives false negatives. No wallet -> no simulation, just the facts.
    simulated = args.wallet is not None
    wallet = args.wallet or "0x0000000000000000000000000000000000000000"

    supply = read_uint(rpcs, contract, "totalSupply()", [])
    balance = (read_uint(rpcs, contract, "balanceOf(address)",
                         [encode_address(wallet)])
               if args.wallet else None)
    free_fn, _ = (simulate_free_mint(rpcs, contract, wallet)
                  if simulated else (None, None))
    result = verdict(supply, args.max_supply, free_fn, balance, simulated)

    if args.json:
        print(json.dumps({
            "contract": contract,
            "totalSupply": supply,
            "maxSupply": args.max_supply,
            "remaining": (args.max_supply - supply
                          if supply is not None and args.max_supply
                          else None),
            "balanceOf": balance,
            "simulated": simulated,
            "freeMintFunction": free_fn,
            "verdict": result,
        }, indent=2))
        return 0

    print(f"contract:    {contract}")
    print(f"totalSupply: {supply if supply is not None else 'n/a'}"
          + (f" / {args.max_supply}" if args.max_supply else ""))
    if args.max_supply and supply is not None:
        print(f"remaining:   {args.max_supply - supply}")
    if balance is not None:
        print(f"balanceOf:   {balance} (wallet {wallet[:10]}...)")
    print(f"free path:   {free_fn or ('not simulated (pass --wallet)'
                                       if not simulated
                                       else 'none (all revert)')}")
    print(f"verdict:     {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
