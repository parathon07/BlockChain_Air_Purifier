"""
Merkle Tree Module.

Implements a binary Merkle tree for cryptographic batching of event hashes.
Provides tree construction, root computation, proof generation, and
proof verification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from .hasher import hash_pair


# Direction constants for Merkle proofs
LEFT = "L"
RIGHT = "R"


@dataclass
class MerkleTree:
    """
    Binary Merkle tree built from a list of leaf hashes.

    The tree is constructed bottom-up using pairwise SHA-256 hashing.
    If a level has an odd number of nodes, the last node is duplicated
    to make it even.
    """

    leaves: List[str]
    _levels: List[List[str]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.leaves:
            raise ValueError("Cannot build a Merkle tree with zero leaves.")
        self._build_tree()

    # ------------------------------------------------------------------ #
    #  Tree construction
    # ------------------------------------------------------------------ #

    def _build_tree(self) -> None:
        """Build the Merkle tree bottom-up."""
        # Level 0 = leaf hashes
        current_level = list(self.leaves)
        self._levels = [current_level]

        while len(current_level) > 1:
            next_level: List[str] = []

            # Pad odd-count level by duplicating the last element
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            for i in range(0, len(current_level), 2):
                parent = hash_pair(current_level[i], current_level[i + 1])
                next_level.append(parent)

            self._levels.append(next_level)
            current_level = next_level

    # ------------------------------------------------------------------ #
    #  Root
    # ------------------------------------------------------------------ #

    def get_root(self) -> str:
        """Return the Merkle root (top of the tree)."""
        return self._levels[-1][0]

    # ------------------------------------------------------------------ #
    #  Proof generation
    # ------------------------------------------------------------------ #

    def get_proof(self, leaf_index: int) -> List[Tuple[str, str]]:
        """
        Generate a Merkle proof for a leaf at the given index.

        Parameters
        ----------
        leaf_index : int
            Zero-based index into the original ``leaves`` list.

        Returns
        -------
        list of (hash, direction) tuples
            Each tuple contains a sibling hash and its position relative
            to the node being proved:
            - ``("abc...def", "L")`` means the sibling is on the left.
            - ``("abc...def", "R")`` means the sibling is on the right.

        Raises
        ------
        IndexError
            If ``leaf_index`` is out of range.
        """
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError(
                f"Leaf index {leaf_index} out of range [0, {len(self.leaves) - 1}]"
            )

        proof: List[Tuple[str, str]] = []
        idx = leaf_index

        for level in self._levels[:-1]:  # skip the root level
            # Ensure the level is even (as it was during build)
            working_level = list(level)
            if len(working_level) % 2 != 0:
                working_level.append(working_level[-1])

            if idx % 2 == 0:
                # Current node is on the left — sibling is on the right
                sibling = working_level[idx + 1]
                proof.append((sibling, RIGHT))
            else:
                # Current node is on the right — sibling is on the left
                sibling = working_level[idx - 1]
                proof.append((sibling, LEFT))

            # Move up to the parent index
            idx = idx // 2

        return proof

    # ------------------------------------------------------------------ #
    #  Proof verification (static)
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], root: str) -> bool:
        """
        Verify that a leaf is part of the tree with the given root.

        Parameters
        ----------
        leaf_hash : str
            SHA-256 hex digest of the leaf to verify.
        proof : list of (hash, direction) tuples
            The Merkle proof as returned by ``get_proof()``.
        root : str
            The expected Merkle root.

        Returns
        -------
        bool
            True if the proof is valid and the leaf is included.
        """
        current = leaf_hash

        for sibling_hash, direction in proof:
            if direction == LEFT:
                current = hash_pair(sibling_hash, current)
            else:  # RIGHT
                current = hash_pair(current, sibling_hash)

        return current == root

    # ------------------------------------------------------------------ #
    #  Introspection
    # ------------------------------------------------------------------ #

    @property
    def depth(self) -> int:
        """Number of levels in the tree (excluding the leaf level)."""
        return len(self._levels) - 1

    @property
    def leaf_count(self) -> int:
        """Number of original leaves."""
        return len(self.leaves)

    def __repr__(self) -> str:
        return (
            f"MerkleTree(leaves={self.leaf_count}, "
            f"depth={self.depth}, root={self.get_root()[:16]}...)"
        )
