import unittest

from truco import Card, TrucoGame, card_rank, envido_value


class TrucoRulesTests(unittest.TestCase):
    def game(self) -> TrucoGame:
        game = TrucoGame(["Ana", "Beto"])
        game.hands = [
            [Card(3, "oros"), Card(7, "copas"), Card(4, "oros")],
            [Card(2, "bastos"), Card(7, "bastos"), Card(5, "copas")],
        ]
        return game

    def test_argentine_card_hierarchy(self) -> None:
        cards = [Card(1, "espadas"), Card(1, "bastos"), Card(7, "espadas"),
                 Card(7, "oros"), Card(3, "copas"), Card(2, "oros"),
                 Card(1, "oros"), Card(12, "bastos"), Card(11, "oros"),
                 Card(10, "copas"), Card(7, "copas"), Card(6, "oros"),
                 Card(5, "oros"), Card(4, "oros")]
        self.assertEqual(sorted(cards, key=card_rank, reverse=True), cards)

    def test_envido_counts_two_highest_cards_of_same_suit(self) -> None:
        cards = [Card(7, "oros"), Card(6, "oros"), Card(12, "bastos")]
        self.assertEqual(envido_value(cards), 33)
        self.assertEqual(envido_value([Card(7, "oros"), Card(12, "bastos"),
                                       Card(10, "copas")]), 7)

    def test_wins_hand_after_first_trick_and_tied_second(self) -> None:
        game = self.game()
        game.play_card(0, 0)
        game.play_card(1, 0)
        self.assertFalse(game.hand_over)
        game.play_card(0, 0)
        game.play_card(1, 0)
        self.assertTrue(game.hand_over)
        self.assertEqual(game.winner, 0)
        self.assertEqual(game.scores, [1, 0])

    def test_burning_a_card_is_hidden_and_limits_the_hand_to_two_tricks(self) -> None:
        game = self.game()
        game.burn_card(0, 2)
        self.assertEqual(game.turn, 1)
        self.assertTrue(game.snapshot(1)["burned"][0])
        self.assertEqual(game.snapshot(1)["opponent_card_count"], 2)
        game.hands = [
            [Card(1, "espadas"), Card(4, "oros")],
            [Card(1, "bastos"), Card(3, "oros"), Card(5, "copas")],
        ]
        game.play_card(1, 0)
        game.play_card(0, 0)
        game.play_card(0, 0)
        game.play_card(1, 0)
        self.assertTrue(game.hand_over)
        self.assertEqual(game.winner, 1)

    def test_split_third_trick_ending_goes_to_first_trick_winner(self) -> None:
        game = self.game()
        game.hands = [
            [Card(3, "oros"), Card(4, "oros"), Card(7, "copas")],
            [Card(2, "bastos"), Card(3, "bastos"), Card(7, "bastos")],
        ]
        for player, index in [(0, 0), (1, 0), (0, 0), (1, 0),
                              (1, 0), (0, 0)]:
            game.play_card(player, index)
        self.assertTrue(game.hand_over)
        self.assertEqual(game.winner, 0)

    def test_third_trick_winner_seat_zero_is_not_treated_as_a_tie(self) -> None:
        game = self.game()
        game.hands = [
            [Card(2, "bastos"), Card(3, "oros"), Card(7, "espadas")],
            [Card(3, "bastos"), Card(4, "oros"), Card(5, "copas")],
        ]
        for player, index in [(0, 0), (1, 0), (1, 0), (0, 0),
                              (0, 0), (1, 0)]:
            game.play_card(player, index)
        self.assertEqual(game.trick_winners, [1, 0, 0])
        self.assertEqual(game.winner, 0)

    def test_cannot_play_out_of_turn(self) -> None:
        game = self.game()
        with self.assertRaisesRegex(ValueError, "No es tu turno"):
            game.play_card(1, 0)

    def test_rejected_truco_awards_previous_stake(self) -> None:
        game = self.game()
        game.call_truco(0, "truco")
        game.respond_truco(1, False)
        self.assertTrue(game.hand_over)
        self.assertEqual(game.scores, [1, 0])

    def test_accepted_truco_keeps_the_caller_turn(self) -> None:
        game = self.game()
        game.call_truco(0, "truco")
        game.respond_truco(1, True)
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.truco_level, 2)
        self.assertFalse(game.hand_over)

    def envido_game(self) -> TrucoGame:
        game = self.game()
        game.hands = [
            [Card(1, "copas"), Card(2, "bastos"), Card(4, "espadas")],
            [Card(7, "oros"), Card(6, "oros"), Card(12, "bastos")],
        ]
        game.envido_hands = [list(game.hands[0]), list(game.hands[1])]
        game.call_envido(0, "envido")
        game.respond_envido(1, True)
        return game

    def test_hidden_envido_claim_can_be_challenged(self) -> None:
        game = self.envido_game()
        game.report_tanto(0, 4)
        game.report_tanto(1, 33, show=False)
        self.assertEqual(game.scores, [0, 0])
        self.assertIsNone(game.snapshot(0)["envido_resolution"]["reports"][1])
        self.assertEqual(game.snapshot(1)["envido_resolution"]["reports"][1], 33)
        game.challenge_tanto()
        self.assertEqual(game.scores, [0, 2])
        self.assertIn("4 a 33", game.event)

    def test_declaring_only_one_tanto_does_not_resume_the_hand(self) -> None:
        game = self.envido_game()
        game.report_tanto(0, 4)
        with self.assertRaisesRegex(ValueError, "Ambos deben declarar"):
            game.play_card(1, 0)

    def test_uncontested_lie_wins_until_rival_challenges(self) -> None:
        game = self.envido_game()
        game.report_tanto(0, 33)
        game.report_tanto(1, 33)
        game.play_card(1, 0)
        self.assertEqual(game.scores, [2, 0])

    def test_challenge_penalizes_one_false_tanto(self) -> None:
        game = self.envido_game()
        game.report_tanto(0, 33)
        game.report_tanto(1, 33)
        game.challenge_tanto()
        self.assertEqual(game.scores, [0, 2])
        self.assertIn("tanto falso", game.event)

    def test_envido_can_finish_the_match_at_thirty_points(self) -> None:
        game = self.envido_game()
        game.hands = [
            [Card(7, "oros"), Card(6, "oros"), Card(12, "bastos")],
            [Card(1, "copas"), Card(2, "bastos"), Card(4, "espadas")],
        ]
        game.envido_hands = [list(game.hands[0]), list(game.hands[1])]
        game.scores = [29, 0]
        game.envido_resolution = None
        game.envido_closed = False
        game.envido_pending = {"caller": 0, "offer": 2, "call": "envido"}
        game.respond_envido(1, True)
        game.report_tanto(0, 33)
        game.report_tanto(1, 4)
        game.challenge_tanto()
        self.assertTrue(game.match_over)
        self.assertTrue(game.hand_over)
        self.assertEqual(game.winner, 0)
        self.assertEqual(game.scores, [31, 0])

    def test_snapshot_never_discloses_opponents_hand(self) -> None:
        state = self.game().snapshot(0)
        self.assertEqual(len(state["hands"]), 3)
        self.assertNotIn("opponent_hand", state)
        self.assertEqual(state["opponent_card_count"], 3)


if __name__ == "__main__":
    unittest.main()
