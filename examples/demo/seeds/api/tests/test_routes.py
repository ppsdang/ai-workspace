import unittest

from api.server import route


class RouteTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(route("/health"), (200, {"ok": True}))

    def test_unknown(self):
        self.assertEqual(route("/nope")[0], 404)
