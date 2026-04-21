"""Tests para proxy.host_filter."""

from __future__ import annotations

import unittest

from proxy.host_filter import (
    FILTER_DECISION_BYPASS,
    FILTER_DECISION_SHOW,
    FILTER_MODE_BLACKLIST,
    FILTER_MODE_WHITELIST,
    HostFilter,
)


class TestHostFilter(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = HostFilter()

    def test_empty_rules_show_everything(self) -> None:
        self.assertEqual(
            self.filter.decide("example.com", 443),
            FILTER_DECISION_SHOW,
        )

    def test_blacklist_wildcard_hides_matching_host(self) -> None:
        self.filter.set_mode(FILTER_MODE_BLACKLIST)
        self.filter.add_pattern("*.microsoft.com")

        self.assertEqual(
            self.filter.decide("mobile.events.data.microsoft.com", 443),
            FILTER_DECISION_BYPASS,
        )
        self.assertEqual(
            self.filter.decide("youtube.com", 443),
            FILTER_DECISION_SHOW,
        )

    def test_whitelist_allows_only_matching_host(self) -> None:
        self.filter.set_mode(FILTER_MODE_WHITELIST)
        self.filter.add_pattern("localhost:3000")

        self.assertEqual(
            self.filter.decide("localhost", 3000),
            FILTER_DECISION_SHOW,
        )
        self.assertEqual(
            self.filter.decide("localhost", 8080),
            FILTER_DECISION_BYPASS,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
