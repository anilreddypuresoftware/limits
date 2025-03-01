import datetime
import time

import pymongo
import pytest

from limits import RateLimitItemPerMinute, RateLimitItemPerSecond
from limits.storage import MongoDBStorage, storage_from_string
from limits.strategies import FixedWindowRateLimiter, MovingWindowRateLimiter


@pytest.mark.mongodb
class TestMongoDBStorage:
    @pytest.fixture(autouse=True)
    def setup(self, mongodb):
        self.storage_url = "mongodb://localhost:37017"
        self.storage = MongoDBStorage(self.storage_url)

    def test_init_options(self, mocker):
        constructor = mocker.spy(pymongo, "MongoClient")
        assert storage_from_string(self.storage_url, socketTimeoutMS=100).check()
        assert constructor.call_args[1]["socketTimeoutMS"] == 100

    def test_fixed_window(self):
        limiter = FixedWindowRateLimiter(self.storage)
        per_second = RateLimitItemPerSecond(10)
        start = time.time()
        count = 0

        while time.time() - start < 0.5 and count < 10:
            assert limiter.hit(per_second)
            count += 1
        assert not limiter.hit(per_second)

        while time.time() - start <= 1:
            time.sleep(0.1)
        assert all(limiter.hit(per_second) for _ in range(10))

    def test_reset(self):
        limiter = FixedWindowRateLimiter(self.storage)

        for i in range(0, 10):
            rate = RateLimitItemPerMinute(i)
            limiter.hit(rate)
        assert self.storage.reset() == 10

    def test_fixed_window_clear(self):
        limiter = FixedWindowRateLimiter(self.storage)
        per_min = RateLimitItemPerMinute(1)
        limiter.hit(per_min)
        assert not limiter.hit(per_min)
        limiter.clear(per_min)
        assert limiter.hit(per_min)

    def test_moving_window_clear(self):
        limiter = MovingWindowRateLimiter(self.storage)
        per_min = RateLimitItemPerMinute(1)
        limiter.hit(per_min)
        assert not limiter.hit(per_min)
        limiter.clear(per_min)
        assert limiter.hit(per_min)

    def test_moving_window_expiry(self):
        limiter = MovingWindowRateLimiter(self.storage)
        limit = RateLimitItemPerSecond(2)
        assert limiter.hit(limit)
        time.sleep(0.9)
        assert limiter.hit(limit)
        assert not limiter.hit(limit)
        time.sleep(0.1)
        assert limiter.hit(limit)
        last = time.time()

        while time.time() - last <= 1:
            time.sleep(0.05)

        assert [] == list(
            self.storage.storage.limits.windows.find(
                {"expireAt": {"$gt": datetime.datetime.utcnow()}}
            )
        )
