import unittest
import asyncio

from app.services.cache import InMemoryCache


class TestInMemoryCache(unittest.TestCase):
    def test_set_and_get(self):
        cache = InMemoryCache(max_entries=2)

        async def run():
            await cache.set("key", "value", ttl_seconds=30)
            value = await cache.get("key")
            self.assertEqual(value, "value")

        asyncio.run(run())

    def test_ttl_expiration(self):
        cache = InMemoryCache(max_entries=2)

        async def run():
            await cache.set("key", "value", ttl_seconds=0)
            value = await cache.get("key")
            self.assertIsNone(value)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
