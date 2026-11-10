"""Unit tests for the pure helpers in mint_scout.py (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mint_scout import (  # noqa: E402
    build_calldata,
    decode_uint,
    encode_address,
    encode_uint,
    verdict,
)


class TestEncoding(unittest.TestCase):
    def test_encode_address(self):
        self.assertEqual(
            encode_address("0x0000000000000000000000000000000000000001"),
            "0" * 24 + "0000000000000000000000000000000000000001",
        )
        # Mixed case is fine; output is lowercase.
        self.assertEqual(
            encode_address("0xF3730995890F9E5712C38D1F3834F1f9EA60F7b7"),
            "0" * 24 + "f3730995890f9e5712c38d1f3834f1f9ea60f7b7",
        )

    def test_encode_address_rejects_garbage(self):
        with self.assertRaises(ValueError):
            encode_address("not-an-address")
        with self.assertRaises(ValueError):
            encode_address("0x1234")

    def test_encode_uint(self):
        self.assertEqual(encode_uint(0), "0" * 64)
        self.assertEqual(encode_uint(1), "0" * 63 + "1")
        self.assertEqual(encode_uint(2487), "0" * 61 + "9b7")
        with self.assertRaises(ValueError):
            encode_uint(-1)

    def test_decode_uint_roundtrip(self):
        for n in (0, 1, 2487, 5656, 10**18):
            self.assertEqual(decode_uint("0x" + encode_uint(n)), n)

    def test_decode_uint_rejects_short_data(self):
        with self.assertRaises(ValueError):
            decode_uint("0x1234")

    def test_build_calldata(self):
        # totalSupply() = 0x18160ddd, no args.
        self.assertEqual(build_calldata("totalSupply()", []), "0x18160ddd")
        # balanceOf(address) with the zero address.
        self.assertEqual(
            build_calldata("balanceOf(address)",
                           [encode_address("0x" + "00" * 20)]),
            "0x70a08231" + "0" * 64,
        )
        # mint(uint256) with amount 1.
        self.assertEqual(
            build_calldata("mint(uint256)", [encode_uint(1)]),
            "0xa0712d68" + "0" * 63 + "1",
        )


class TestVerdict(unittest.TestCase):
    def test_not_a_mint_contract(self):
        self.assertEqual(
            verdict(None, None, None, None, True),
            "NOT A MINT CONTRACT (no totalSupply)",
        )

    def test_sold_out(self):
        self.assertEqual(
            verdict(5000, 5000, None, 0, True), "SOLD OUT")
        self.assertEqual(
            verdict(5045, 5000, None, 0, True), "SOLD OUT")

    def test_not_simulated(self):
        self.assertEqual(
            verdict(5656, 10000, None, None, False),
            "NOT SIMULATED (pass --wallet to check the free path)",
        )

    def test_free_mint_closed(self):
        self.assertEqual(
            verdict(5656, 10000, None, 0, True),
            "FREE MINT CLOSED (every free path reverts)",
        )

    def test_free_mint_live(self):
        self.assertEqual(
            verdict(5656, 10000, "mint()", 0, True),
            "FREE MINT LIVE via mint()",
        )
        self.assertEqual(
            verdict(5656, 10000, "mint()", 2, True),
            "FREE MINT LIVE via mint() (already hold 2)",
        )


if __name__ == "__main__":
    unittest.main()
