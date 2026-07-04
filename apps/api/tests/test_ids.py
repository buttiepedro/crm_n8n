import time

from app.core.ids import uuid7


def test_version_and_variant():
    u = uuid7()
    assert u.version == 7
    assert u.variant == "specified in RFC 4122"


def test_time_ordered():
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    assert str(a) < str(b)


def test_uniqueness():
    ids = {uuid7() for _ in range(1000)}
    assert len(ids) == 1000
