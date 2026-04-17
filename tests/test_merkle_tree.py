"""Tests for the Merkle Tree module."""

import pytest

from blockchain_compliance.merkle_tree import MerkleTree
from blockchain_compliance.hasher import hash_string, hash_pair


class TestMerkleTreeConstruction:
    """Test tree building."""

    def test_single_leaf(self):
        h = hash_string("only leaf")
        tree = MerkleTree([h])
        assert tree.get_root() == h  # root = the single leaf
        assert tree.depth == 0

    def test_two_leaves(self):
        a = hash_string("A")
        b = hash_string("B")
        tree = MerkleTree([a, b])
        expected_root = hash_pair(a, b)
        assert tree.get_root() == expected_root
        assert tree.depth == 1

    def test_four_leaves(self):
        leaves = [hash_string(f"leaf-{i}") for i in range(4)]
        tree = MerkleTree(leaves)
        h01 = hash_pair(leaves[0], leaves[1])
        h23 = hash_pair(leaves[2], leaves[3])
        expected_root = hash_pair(h01, h23)
        assert tree.get_root() == expected_root
        assert tree.depth == 2

    def test_odd_leaves_padding(self):
        """Odd number of leaves → last leaf duplicated."""
        leaves = [hash_string(f"leaf-{i}") for i in range(3)]
        tree = MerkleTree(leaves)
        # Level 0: [L0, L1, L2] → padded to [L0, L1, L2, L2]
        h01 = hash_pair(leaves[0], leaves[1])
        h22 = hash_pair(leaves[2], leaves[2])
        expected_root = hash_pair(h01, h22)
        assert tree.get_root() == expected_root

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            MerkleTree([])

    def test_deterministic(self):
        leaves = [hash_string(f"event-{i}") for i in range(8)]
        t1 = MerkleTree(leaves)
        t2 = MerkleTree(leaves)
        assert t1.get_root() == t2.get_root()

    def test_leaf_count(self):
        leaves = [hash_string(str(i)) for i in range(7)]
        tree = MerkleTree(leaves)
        assert tree.leaf_count == 7


class TestMerkleProof:
    """Test proof generation and verification."""

    def test_proof_for_each_leaf(self):
        """Every leaf in the tree should produce a valid proof."""
        leaves = [hash_string(f"event-{i}") for i in range(8)]
        tree = MerkleTree(leaves)
        root = tree.get_root()

        for i in range(len(leaves)):
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(leaves[i], proof, root)

    def test_proof_small_tree(self):
        a = hash_string("A")
        b = hash_string("B")
        tree = MerkleTree([a, b])
        root = tree.get_root()

        proof_a = tree.get_proof(0)
        assert MerkleTree.verify_proof(a, proof_a, root)

        proof_b = tree.get_proof(1)
        assert MerkleTree.verify_proof(b, proof_b, root)

    def test_proof_odd_tree(self):
        leaves = [hash_string(f"x{i}") for i in range(5)]
        tree = MerkleTree(leaves)
        root = tree.get_root()

        for i in range(len(leaves)):
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(leaves[i], proof, root)

    def test_invalid_proof_wrong_leaf(self):
        leaves = [hash_string(f"event-{i}") for i in range(4)]
        tree = MerkleTree(leaves)
        root = tree.get_root()

        proof = tree.get_proof(0)
        wrong_leaf = hash_string("WRONG")
        assert not MerkleTree.verify_proof(wrong_leaf, proof, root)

    def test_invalid_proof_wrong_root(self):
        leaves = [hash_string(f"event-{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.get_proof(0)
        wrong_root = hash_string("WRONG_ROOT")
        assert not MerkleTree.verify_proof(leaves[0], proof, wrong_root)

    def test_proof_index_out_of_range(self):
        leaves = [hash_string("a"), hash_string("b")]
        tree = MerkleTree(leaves)
        with pytest.raises(IndexError):
            tree.get_proof(5)

    def test_proof_negative_index(self):
        leaves = [hash_string("a")]
        tree = MerkleTree(leaves)
        with pytest.raises(IndexError):
            tree.get_proof(-1)

    def test_large_tree(self):
        """Test with 100 leaves — realistic batch size."""
        leaves = [hash_string(f"event-{i}") for i in range(100)]
        tree = MerkleTree(leaves)
        root = tree.get_root()

        # Verify a sample of proofs
        for i in [0, 1, 49, 50, 99]:
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(leaves[i], proof, root)
