"""Tests for DuckDB lock retry logic."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from threading import Thread
from unittest.mock import Mock, patch

import duckdb
import pytest

from spvx.open_sea.db import DuckDBWriter


def test_duckdb_writer_successful_connection():
    """Test that DuckDBWriter connects successfully when no lock exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        # Create a simple database
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        con.close()
        
        # Writer should connect successfully
        writer = DuckDBWriter(db_path, max_retries=3, retry_delay=0.1)
        assert writer.con is not None
        writer.close()


def test_duckdb_writer_lock_retry_success():
    """Test that DuckDBWriter retries and succeeds when lock is released."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        # Create database
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        con.close()
        
        # Hold lock in background thread, release after 1 second
        lock_holder = duckdb.connect(str(db_path))
        
        def release_lock():
            time.sleep(1)
            lock_holder.close()
        
        thread = Thread(target=release_lock)
        thread.start()
        
        # Writer should retry and succeed
        start = time.time()
        writer = DuckDBWriter(db_path, max_retries=10, retry_delay=0.2)
        elapsed = time.time() - start
        
        assert writer.con is not None
        assert elapsed >= 1.0  # Should have waited for lock
        
        writer.close()
        thread.join()


def test_duckdb_writer_lock_failure_after_retries():
    """Test that DuckDBWriter fails after exhausting retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        # Create database
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        con.close()
        
        # Hold lock permanently
        lock_holder = duckdb.connect(str(db_path))
        
        try:
            # Writer should fail after retries
            with pytest.raises(RuntimeError) as exc_info:
                DuckDBWriter(db_path, max_retries=3, retry_delay=0.1)
            
            assert "Could not acquire DuckDB lock" in str(exc_info.value)
            assert str(db_path) in str(exc_info.value)
        finally:
            lock_holder.close()


def test_duckdb_writer_non_lock_error_fails_immediately():
    """Test that non-lock errors fail immediately without retry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "nonexistent" / "test.duckdb"
        
        # This should fail immediately (directory doesn't exist)
        start = time.time()
        with pytest.raises(Exception):  # Could be IOError or other
            DuckDBWriter(db_path, max_retries=5, retry_delay=1.0)
        elapsed = time.time() - start
        
        # Should fail quickly, not retry for 5+ seconds
        assert elapsed < 2.0


def test_duckdb_writer_exponential_backoff():
    """Test that retry delays follow exponential backoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        # Create database
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        con.close()
        
        # Hold lock permanently
        lock_holder = duckdb.connect(str(db_path))
        
        try:
            start = time.time()
            with pytest.raises(RuntimeError):
                # retry_delay=0.5: waits 0.5, 1.0, 2.0, 4.0 = 7.5s total
                DuckDBWriter(db_path, max_retries=5, retry_delay=0.5)
            elapsed = time.time() - start
            
            # Should have waited approximately: 0.5 + 1.0 + 2.0 + 4.0 = 7.5s
            # Allow some tolerance for execution time
            assert 7.0 <= elapsed <= 9.0
        finally:
            lock_holder.close()


def test_duckdb_writer_close_idempotent():
    """Test that close() can be called multiple times safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        writer = DuckDBWriter(db_path)
        
        # Multiple closes should not raise
        writer.close()
        writer.close()
        writer.close()


def test_duckdb_writer_logging(caplog):
    """Test that appropriate log messages are generated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        writer = DuckDBWriter(db_path, max_retries=2)
        
        # Should log successful connection
        assert any("Successfully connected to DuckDB" in record.message for record in caplog.records)
        assert any(str(db_path) in record.message for record in caplog.records)
        
        writer.close()


def test_duckdb_writer_lock_logging_on_retry(caplog):
    """Test that lock warnings are logged during retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        
        # Create and lock database
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        con.close()
        
        lock_holder = duckdb.connect(str(db_path))
        
        try:
            with pytest.raises(RuntimeError):
                DuckDBWriter(db_path, max_retries=2, retry_delay=0.1)
            
            # Should have logged warnings about locks
            log_messages = [record.message for record in caplog.records]
            assert any("DuckDB file is locked" in msg for msg in log_messages)
            assert any("Failed to connect to DuckDB after" in msg for msg in log_messages)
        finally:
            lock_holder.close()
