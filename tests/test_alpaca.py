import os
import unittest
from unittest.mock import patch

from portfolio_model.alpaca import AlpacaClient, AlpacaConfig, AlpacaConfigError


class AlpacaConfigTest(unittest.TestCase):
    def test_config_requires_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AlpacaConfigError):
                AlpacaConfig.from_env()

    def test_config_defaults_to_paper_endpoint(self):
        with patch.dict(
            os.environ,
            {"APCA_API_KEY_ID": "key", "APCA_API_SECRET_KEY": "secret"},
            clear=True,
        ):
            config = AlpacaConfig.from_env()

        self.assertEqual(config.base_url, "https://paper-api.alpaca.markets")

    def test_clock_uses_trading_api(self):
        client = AlpacaClient(AlpacaConfig("key", "secret", "https://paper.example", "https://data.example"))
        with patch.object(client, "_request", return_value={"is_open": False}) as request:
            clock = client.clock()

        self.assertFalse(clock["is_open"])
        request.assert_called_once_with("GET", "/v2/clock")

    def test_calendar_uses_trading_api(self):
        client = AlpacaClient(AlpacaConfig("key", "secret", "https://paper.example", "https://data.example"))
        with patch.object(client, "_request", return_value=[]) as request:
            calendar = client.calendar(start="2026-05-15", end="2026-05-15")

        self.assertEqual(calendar, [])
        request.assert_called_once_with("GET", "/v2/calendar?start=2026-05-15&end=2026-05-15")


if __name__ == "__main__":
    unittest.main()
