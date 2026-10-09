import unittest
from unittest.mock import MagicMock

from Servidor import Client, GameServer, Match
from truco import Card, TrucoGame


class BotTrucoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = Client(MagicMock(), ("127.0.0.1", 1))
        self.bot = Client(MagicMock(), ("127.0.0.1", 1))
        self.game = TrucoGame(["Ana", "Bot Truquero"])
        self.game.hands = [
            [Card(3, "oros"), Card(7, "copas"), Card(4, "oros")],
            [Card(2, "bastos"), Card(7, "bastos"), Card(5, "copas")],
        ]
        self.match = Match("match-id", [self.user, self.bot], self.game,
                           against_bot=True)
        self.server = GameServer(MagicMock())

    def test_bot_accepts_truco_and_waits_for_user_card(self) -> None:
        self.game.call_truco(0, "truco")

        self.server._run_bot(self.match)

        self.assertIsNone(self.game.truco_pending)
        self.assertEqual(self.game.turn, 0)
        self.assertEqual([len(hand) for hand in self.game.hands], [3, 3])

        self.game.play_card(0, 0)
        self.server._run_bot(self.match)

        self.assertEqual([len(hand) for hand in self.game.hands], [2, 2])
        self.assertEqual(len(self.game.played[0]), 1)
        self.assertEqual(len(self.game.played[1]), 1)

    def test_bot_rejects_truco_and_awards_caller_one_point(self) -> None:
        self.game.hands[1] = [
            Card(4, "oros"), Card(5, "copas"), Card(6, "bastos"),
        ]
        self.game.call_truco(0, "truco")

        self.server._run_bot(self.match)

        self.assertTrue(self.game.hand_over)
        self.assertEqual(self.game.scores, [1, 0])
        self.assertEqual([len(hand) for hand in self.game.hands], [3, 3])

    def test_bot_opens_the_second_hand_when_it_is_mano(self) -> None:
        self.game.hand_over = True

        self.server._new_hand(self.match)

        self.assertEqual(self.game.mano, 1)
        self.assertEqual(self.game.turn, 0)
        self.assertEqual(len(self.game.played[1]), 1)
        self.assertEqual(len(self.game.hands[1]), 2)
        self.assertEqual(len(self.game.hands[0]), 3)


if __name__ == "__main__":
    unittest.main()
