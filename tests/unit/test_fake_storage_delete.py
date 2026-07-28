"""Unit tests for FakeStorage.delete — added additively for multitenancy's
DELETE /me/data (see cinemory.api.delete_my_data / _TenantScopedStorage)."""
from __future__ import annotations

from cinemory.adapters import FakeStorage


def test_delete_removes_object_and_index_row():
    s = FakeStorage(bucket="b")
    s.put("k/x", b"data")
    assert s.exists("k/x") is True

    s.delete("k/x")

    assert s.exists("k/x") is False
    assert s.index == []


def test_delete_only_removes_the_matching_key():
    s = FakeStorage()
    s.put("a", b"1")
    s.put("b", b"22")

    s.delete("a")

    assert s.exists("a") is False
    assert s.exists("b") is True
    assert [row["key"] for row in s.index] == ["b"]


def test_delete_of_a_missing_key_is_a_no_op_not_an_error():
    s = FakeStorage()
    s.delete("never-existed")  # must not raise
    assert s.index == []


def test_delete_is_idempotent():
    s = FakeStorage()
    s.put("k", b"v")
    s.delete("k")
    s.delete("k")  # second call: still a clean no-op
    assert s.exists("k") is False
    assert s.index == []
