import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from portfolio_model.env import load_dotenv


class EnvTest(unittest.TestCase):
    def test_load_dotenv_sets_missing_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("APCA_API_KEY_ID='paper-key'\nPORTFOLIO_DRY_RUN=false\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                load_dotenv(path)

                self.assertEqual(os.environ["APCA_API_KEY_ID"], "paper-key")
                self.assertEqual(os.environ["PORTFOLIO_DRY_RUN"], "false")

    def test_load_dotenv_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("PORTFOLIO_DRY_RUN=false\n", encoding="utf-8")

            with patch.dict(os.environ, {"PORTFOLIO_DRY_RUN": "true"}, clear=True):
                load_dotenv(path)

                self.assertEqual(os.environ["PORTFOLIO_DRY_RUN"], "true")


if __name__ == "__main__":
    unittest.main()
