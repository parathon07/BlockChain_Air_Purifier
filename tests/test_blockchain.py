"""Tests for the Local Blockchain module."""

import os
import tempfile

import pytest

from blockchain_compliance.blockchain import LocalBlockchain, Block, ZERO_HASH
from blockchain_compliance.hasher import hash_string


@pytest.fixture
def chain():
    """Create a fresh blockchain in a temp directory."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_blocks.db")
    return LocalBlockchain(db_path=db_path)


class TestGenesisBlock:
    """Test genesis block creation."""

    def test_genesis_exists(self, chain):
        assert chain.get_chain_length() == 1

    def test_genesis_index_zero(self, chain):
        genesis = chain.get_block(0)
        assert genesis is not None
        assert genesis.index == 0

    def test_genesis_zero_hashes(self, chain):
        genesis = chain.get_block(0)
        assert genesis.event_hash == ZERO_HASH
        assert genesis.previous_hash == ZERO_HASH

    def test_genesis_block_hash_is_valid(self, chain):
        genesis = chain.get_block(0)
        assert genesis.block_hash == genesis.compute_hash()


class TestBlockAppending:
    """Test adding blocks and chain linking."""

    def test_add_single_block(self, chain):
        event_hash = hash_string("test event 1")
        block = chain.add_block(event_hash)
        assert block.index == 1
        assert block.event_hash == event_hash

    def test_chain_linking(self, chain):
        h1 = hash_string("event 1")
        h2 = hash_string("event 2")
        b1 = chain.add_block(h1)
        b2 = chain.add_block(h2)
        assert b2.previous_hash == b1.block_hash

    def test_multiple_blocks(self, chain):
        for i in range(10):
            chain.add_block(hash_string(f"event {i}"))
        assert chain.get_chain_length() == 11  # genesis + 10

    def test_latest_block(self, chain):
        last_hash = hash_string("last event")
        chain.add_block(hash_string("first"))
        block = chain.add_block(last_hash)
        latest = chain.get_latest_block()
        assert latest.block_hash == block.block_hash
        assert latest.event_hash == last_hash


class TestChainValidation:
    """Test chain integrity validation."""

    def test_valid_chain(self, chain):
        for i in range(5):
            chain.add_block(hash_string(f"event {i}"))
        assert chain.validate_chain() is True

    def test_tampered_event_hash(self, chain):
        chain.add_block(hash_string("event 1"))
        chain.add_block(hash_string("event 2"))

        # Tamper with block 1's event_hash directly in DB
        import sqlite3
        with sqlite3.connect(chain.db_path) as conn:
            conn.execute(
                "UPDATE blocks SET event_hash = ? WHERE idx = 1",
                ("tampered" + "0" * 57,),
            )

        assert chain.validate_chain() is False

    def test_tampered_block_hash(self, chain):
        chain.add_block(hash_string("event 1"))

        import sqlite3
        with sqlite3.connect(chain.db_path) as conn:
            conn.execute(
                "UPDATE blocks SET block_hash = ? WHERE idx = 1",
                ("f" * 64,),
            )

        assert chain.validate_chain() is False


class TestPersistence:
    """Test that blocks survive database reconnection."""

    def test_blocks_persist(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "persist_test.db")

        # Create chain and add blocks
        chain1 = LocalBlockchain(db_path=db_path)
        chain1.add_block(hash_string("event A"))
        chain1.add_block(hash_string("event B"))
        assert chain1.get_chain_length() == 3

        # Reload from same DB
        chain2 = LocalBlockchain(db_path=db_path)
        assert chain2.get_chain_length() == 3
        assert chain2.validate_chain() is True

        # Verify block content
        block_a = chain2.get_block(1)
        assert block_a.event_hash == hash_string("event A")
