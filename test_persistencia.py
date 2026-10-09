import unittest
from unittest.mock import MagicMock, patch

from persistencia import Persistence


class PersistenceMatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = Persistence()
        self.cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = self.cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor_context
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = connection

    def test_create_bot_match_uses_flat_user_records(self) -> None:
        players = [
            {"id": 7, "username": "bruno1"},
            {"id": None, "username": "Bot Truquero"},
        ]

        with patch.object(
            self.database, "_connection", return_value=self.connection_context
        ):
            self.database.create_match("match-id", players, against_bot=True)

        parameters = self.cursor.execute.call_args.args[1]
        self.assertEqual(
            parameters,
            ("match-id", 7, None, "bruno1", "Bot Truquero", True),
        )

    def test_saving_bot_match_updates_only_human_user(self) -> None:
        self.cursor.rowcount = 1
        players = [
            {"id": 7, "username": "bruno1"},
            {"id": None, "username": "Bot Truquero"},
        ]

        with patch.object(
            self.database, "_connection", return_value=self.connection_context
        ):
            self.database.save_match(
                "match-id", players, winner=0, scores=[30, 12],
                against_bot=True,
            )

        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assertEqual(self.cursor.execute.call_args_list[1].args[1], (7,))


if __name__ == "__main__":
    unittest.main()
