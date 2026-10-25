"""Capacity eviction preserves seen times, stable ties, and reconnect handoff."""

from gateway.platforms import helpers


def test_capacity_eviction_uses_seen_time_with_stable_ties(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(helpers.time, "time", lambda: now[0])
    cache = helpers.MessageDeduplicator(max_size=3, ttl_seconds=60)
    assert [cache.is_duplicate(key) for key in ("first", "second", "third")] == [False, False, False]

    now[0] = 99.0
    assert cache.is_duplicate("clock-went-back") is False
    assert cache.contains("clock-went-back") is False
    now[0] = 101.0
    assert cache.is_duplicate("first") is True  # A duplicate does not refresh its seen time.
    assert cache.is_duplicate("newest") is False
    assert [cache.contains(key) for key in ("first", "second", "third", "newest")] == [False, True, True, True]


def test_reconnect_handoff_then_capacity_eviction_keeps_newest_ids(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(helpers.time, "time", lambda: now[0])
    predecessor = helpers.MessageDeduplicator(max_size=4, ttl_seconds=10)
    assert predecessor.is_duplicate("expired") is False
    now[0] = 105.0
    assert predecessor.is_duplicate("middle") is False
    now[0] = 109.0
    assert predecessor.is_duplicate("fresh") is False
    replacement = helpers.MessageDeduplicator(max_size=2, ttl_seconds=10)
    assert replacement.is_duplicate("own") is False
    now[0] = 110.0
    replacement.absorb(predecessor)
    assert replacement.contains("expired") is False
    assert replacement.is_duplicate("next") is False
    assert [replacement.contains(key) for key in ("own", "middle", "fresh", "next")] == [False, False, True, True]
    now[0] = 111.0
    assert replacement.is_duplicate("latest") is False
    assert [replacement.contains(key) for key in ("fresh", "next", "latest")] == [False, True, True]
