"""Reglas y estado de una partida de Truco Argentino mano a mano."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

SUITS = ("oros", "copas", "espadas", "bastos")
VALUES = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)
CARD_NAMES = {1: "As", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco",
              6: "Seis", 7: "Siete", 10: "Sota", 11: "Caballo", 12: "Rey"}
SUIT_NAMES = {"oros": "Oro", "copas": "Copa", "espadas": "Espada",
              "bastos": "Basto"}


@dataclass(frozen=True)
class Card:
    value: int
    suit: str

    @property
    def name(self) -> str:
        return f"{CARD_NAMES[self.value]} de {SUIT_NAMES[self.suit]}"

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "suit": self.suit, "name": self.name}


def card_rank(card: Card) -> int:
    """Orden de fuerza argentino; los valores altos ganan."""
    if card.value == 1 and card.suit == "espadas":
        return 14
    if card.value == 1 and card.suit == "bastos":
        return 13
    if card.value == 7 and card.suit == "espadas":
        return 12
    if card.value == 7 and card.suit == "oros":
        return 11
    if card.value == 3:
        return 10
    if card.value == 2:
        return 9
    if card.value == 1:
        return 8
    if card.value == 12:
        return 7
    if card.value == 11:
        return 6
    if card.value == 10:
        return 5
    if card.value == 7:
        return 4
    return card.value - 3


def envido_value(cards: list[Card]) -> int:
    """Calcula el tanto de tres cartas para Envido."""
    best = max((card.value if card.value < 10 else 0 for card in cards), default=0)
    for suit in SUITS:
        same_suit = [card.value if card.value < 10 else 0
                     for card in cards if card.suit == suit]
        if len(same_suit) >= 2:
            best = max(best, 20 + sum(sorted(same_suit, reverse=True)[:2]))
    return best


def _winning_team(winners: list[int | None], mano: int) -> int:
    first, second, third = winners
    if first is None:
        if second is not None:
            return second
        return mano if third is None else third
    if second is None:
        return first
    if second == first:
        return first
    if third is None:
        return first
    return third


class TrucoGame:
    """Partida 1 vs 1. Los asientos 0 y 1 son equipos opuestos."""

    def __init__(self, players: list[str], mano: int = 0) -> None:
        if len(players) != 2 or mano not in (0, 1):
            raise ValueError("Una partida requiere dos jugadores y una mano válida.")
        self.players = players
        self.mano = mano
        self.scores = [0, 0]
        self.hand_number = 0
        self._new_hand()

    def _new_hand(self) -> None:
        deck = [Card(value, suit) for suit in SUITS for value in VALUES]
        random.shuffle(deck)
        self.hands = [deck[:3], deck[3:6]]
        self.envido_hands = [list(self.hands[0]), list(self.hands[1])]
        self.burned = [False, False]
        self.tricks_target = 3
        self.played: list[list[dict[str, Any]]] = [[], []]
        self.trick_winners: list[int | None] = []
        self.trick_cards: list[tuple[int, Card]] = []
        self.turn = self.mano
        self.truco_level = 1
        self.truco_pending: dict[str, Any] | None = None
        self.envido_pending: dict[str, Any] | None = None
        self.envido_resolution: dict[str, Any] | None = None
        self.envido_points = 0
        self.envido_closed = False
        self.hand_over = False
        self.winner: int | None = None
        self.match_over = False
        self.event = f"Comienza la mano {self.hand_number + 1}. Mano: {self.players[self.mano]}."

    @property
    def envido_available(self) -> bool:
        return (not self.hand_over and not self.match_over and
                not self.envido_closed and not self.envido_pending and
                not self.envido_resolution and not self.trick_winners and
                not self.trick_cards)

    def _add_points(self, team: int, points: int) -> None:
        self.scores[team] += points
        if self.scores[team] >= 30:
            self.match_over = True

    def _finish_hand(self, team: int, points: int, message: str) -> None:
        if self.hand_over:
            return
        self._add_points(team, points)
        self.hand_over = True
        self.winner = team
        self.event = f"{message} {self.players[team]} suma {points} punto(s)."

    def _finish_if_tricks_decided(self) -> None:
        if len(self.trick_winners) != 3:
            return
        team = _winning_team(self.trick_winners, self.mano)
        self._finish_hand(team, self.truco_level, "Gana la mano.")

    def play_card(self, player: int, card_index: int) -> None:
        if self.hand_over or self.match_over or self.truco_pending or self.envido_pending:
            raise ValueError("No se puede jugar mientras la mano está pausada.")
        if player != self.turn:
            raise ValueError("No es tu turno.")
        if type(card_index) is not int or not 0 <= card_index < len(self.hands[player]):
            raise ValueError("Índice de carta inválido.")
        if self.envido_resolution:
            if len(self.envido_resolution["reports"]) != 2:
                raise ValueError("Ambos deben declarar su tanto antes de jugar.")
            self._resolve_tanto(challenge=False)
            if self.hand_over:
                return
        card = self.hands[player].pop(card_index)
        self.trick_cards.append((player, card))
        self.played[player].append({"card": card.to_dict(),
                                    "trick": len(self.trick_winners) + 1})
        self.event = f"{self.players[player]} jugó {card.name}."
        if len(self.trick_cards) == 1:
            self.turn = 1 - player
            return

        first, second = self.trick_cards
        rank_first = card_rank(first[1])
        rank_second = card_rank(second[1])
        trick_winner = None if rank_first == rank_second else (
            first[0] if rank_first > rank_second else second[0])
        self.trick_winners.append(trick_winner)
        if trick_winner is None:
            self.event += " La baza quedó parda."
            self.turn = self.mano
        else:
            self.event += f" Baza para {self.players[trick_winner]}."
            self.turn = trick_winner
        self.trick_cards = []

        if len(self.trick_winners) >= 2:
            decided = _winning_team(self.trick_winners + [None] *
                                    (3 - len(self.trick_winners)), self.mano)
            first_winner, second_winner = self.trick_winners[:2]
            if first_winner is None and second_winner is not None:
                self._finish_hand(second_winner, self.truco_level, "Gana la mano.")
            elif first_winner is not None and (
                    second_winner == first_winner or second_winner is None):
                self._finish_hand(first_winner, self.truco_level, "Gana la mano.")
            elif first_winner is not None and second_winner is not None:
                if len(self.trick_winners) >= self.tricks_target:
                    third_winner = self.trick_winners[2] if len(
                        self.trick_winners) == 3 else None
                    winner = (second_winner if self.tricks_target == 2 else
                              (first_winner if third_winner is None else third_winner))
                    self._finish_hand(winner, self.truco_level, "Gana la mano.")
                else:
                    self.turn = second_winner
            elif len(self.trick_winners) >= self.tricks_target:
                self._finish_hand(decided, self.truco_level, "Gana la mano.")

    def burn_card(self, player: int, card_index: int) -> None:
        if (self.hand_over or self.match_over or self.truco_pending or
                self.envido_pending or self.envido_resolution):
            raise ValueError("No se puede quemar una carta ahora.")
        if player != self.turn:
            raise ValueError("No es tu turno.")
        if self.trick_cards:
            raise ValueError("Solo se puede quemar antes de que empiece una baza.")
        if self.burned[player]:
            raise ValueError("Ya quemaste una carta en esta mano.")
        if len(self.hands[player]) < 2:
            raise ValueError("Debe quedarte al menos una carta para jugar.")
        if type(card_index) is not int or not 0 <= card_index < len(self.hands[player]):
            raise ValueError("Índice de carta inválido.")
        self.hands[player].pop(card_index)
        self.burned[player] = True
        self.tricks_target = min(
            self.tricks_target,
            len(self.trick_winners) + min(len(self.hands[0]), len(self.hands[1]))
        )
        self.turn = 1 - player
        self.event = f"{self.players[player]} quemó una carta boca abajo."

    def call_truco(self, player: int, call: str) -> None:
        levels = {"truco": 2, "retruco": 3, "vale_cuatro": 4}
        expected = {1: "truco", 2: "retruco", 3: "vale_cuatro"}
        if (self.hand_over or self.match_over or self.truco_pending or
                self.envido_pending or self.envido_resolution):
            raise ValueError("No se puede cantar ahora.")
        if player != self.turn:
            raise ValueError("Solo quien tiene el turno puede cantar.")
        if not isinstance(call, str) or expected.get(self.truco_level) != call:
            raise ValueError(f"El siguiente canto válido es {expected.get(self.truco_level)}.")
        if self.trick_winners and len(self.trick_winners) == 3:
            raise ValueError("La mano ya terminó.")
        self.truco_pending = {"caller": player, "level": levels[call]}
        self.event = f"{self.players[player]} cantó {call.replace('_', ' ')}."

    def respond_truco(self, player: int, accept: bool) -> None:
        if not isinstance(accept, bool):
            raise ValueError("La respuesta debe ser quiero o no quiero.")
        pending = self.truco_pending
        if not pending or player == pending["caller"]:
            raise ValueError("No tienes un canto pendiente para responder.")
        if accept:
            self.truco_level = pending["level"]
            self.truco_pending = None
            self.turn = player
            self.event = f"{self.players[player]} quiso. La mano vale {self.truco_level}."
        else:
            self._finish_hand(pending["caller"], self.truco_level,
                              f"{self.players[player]} no quiso.")
            self.truco_pending = None

    def call_envido(self, player: int, call: str) -> None:
        values = {"envido": 2, "real_envido": 3, "falta_envido": 30 - max(self.scores)}
        if (self.hand_over or self.match_over or self.envido_pending or
                self.envido_resolution or
                self.envido_closed or self.truco_pending):
            raise ValueError("No se puede cantar Envido ahora.")
        if self.trick_winners or self.trick_cards:
            raise ValueError("El Envido se canta antes de jugar la primera carta.")
        if player != self.turn:
            raise ValueError("Solo quien tiene el turno puede cantar.")
        if not isinstance(call, str) or call not in values:
            raise ValueError("Canto de Envido inválido.")
        self.envido_pending = {"caller": player,
                               "offer": self.envido_points + values[call],
                               "call": call}
        self.event = f"{self.players[player]} cantó {call.replace('_', ' ')}."

    def respond_envido(self, player: int, accept: bool) -> None:
        if not isinstance(accept, bool):
            raise ValueError("La respuesta debe ser quiero o no quiero.")
        pending = self.envido_pending
        if not pending or player == pending["caller"]:
            raise ValueError("No tienes un Envido pendiente para responder.")
        caller = pending["caller"]
        if not accept:
            points = self.envido_points or 1
            self._add_points(caller, points)
            self.envido_pending = None
            self.envido_closed = True
            if self.match_over:
                self.hand_over = True
                self.winner = caller
            self.event = f"{self.players[player]} no quiso el Envido. {self.players[caller]} suma {points}."
            return
        offer = pending["offer"]
        self.envido_points = offer
        self.envido_pending = None
        if pending["call"] == "falta_envido":
            offer = 30 - max(self.scores)
        self.envido_resolution = {"offer": offer, "reports": {}}
        self.event = ("Envido querido. Ambos declaran su tanto con /tanto N o "
                      "/tanto-oculto N; /reclamar verifica las cartas.")
        self.turn = player

    def report_tanto(self, player: int, value: int, show: bool = True) -> None:
        resolution = self.envido_resolution
        if not resolution or self.hand_over:
            raise ValueError("No hay un Envido pendiente de declaración.")
        if type(value) is not int or not 0 <= value <= 33:
            raise ValueError("El tanto debe ser un número entre 0 y 33.")
        reports = resolution["reports"]
        if player not in (0, 1):
            raise ValueError("Jugador inválido.")
        if player in reports:
            raise ValueError("Ya declaraste tu tanto.")
        reports[player] = {"value": value, "show": show}
        self.event = (f"{self.players[player]} declaró {value} tantos."
                      if show else f"{self.players[player]} declaró su tanto en secreto.")
        if len(reports) == 2:
            self.event += " Juega para aceptar o escribe /reclamar."

    def challenge_tanto(self) -> None:
        if not self.envido_resolution or len(self.envido_resolution["reports"]) != 2:
            raise ValueError("Ambos deben declarar su tanto antes del reclamo.")
        self._resolve_tanto(challenge=True)

    def _resolve_tanto(self, challenge: bool) -> None:
        resolution = self.envido_resolution
        if not resolution or len(resolution["reports"]) != 2:
            raise ValueError("Faltan declaraciones de tanto.")
        reports = resolution["reports"]
        actual = [envido_value(cards) for cards in self.envido_hands]
        if challenge:
            incorrect = [seat for seat in (0, 1)
                         if reports[seat]["value"] != actual[seat]]
            if len(incorrect) == 1:
                winner = 1 - incorrect[0]
                result = "Reclamo correcto: se comprueba un tanto falso."
            else:
                winner = (self.mano if actual[0] == actual[1] else
                          (0 if actual[0] > actual[1] else 1))
                result = "Reclamo comprobado. Tantos reales:"
            detail = f" {actual[0]} a {actual[1]}."
        else:
            declared = [reports[seat]["value"] for seat in (0, 1)]
            winner = (self.mano if declared[0] == declared[1] else
                      (0 if declared[0] > declared[1] else 1))
            result = "Declaraciones aceptadas sin reclamo."
            detail = ""
        points = resolution["offer"]
        self.envido_resolution = None
        self.envido_closed = True
        self._add_points(winner, points)
        if self.match_over:
            self.hand_over = True
            self.winner = winner
        self.event = f"{result}{detail} {self.players[winner]} suma {points}."

    def snapshot(self, player: int) -> dict[str, Any]:
        opponent = 1 - player
        return {
            "players": self.players,
            "you": player,
            "hands": [card.to_dict() for card in self.hands[player]],
            "played": self.played,
            "scores": self.scores,
            "turn": self.turn,
            "mano": self.mano,
            "trick": len(self.trick_winners) + 1,
            "truco_level": self.truco_level,
            "envido_available": self.envido_available,
            "truco_pending": self.truco_pending,
            "envido_pending": self.envido_pending,
            "envido_resolution": self._visible_envido_resolution(player),
            "event": self.event,
            "hand_over": self.hand_over,
            "winner": self.winner,
            "match_over": self.match_over,
            "opponent_card_count": len(self.hands[opponent]),
            "burned": self.burned,
        }

    def _visible_envido_resolution(self, player: int) -> dict[str, Any] | None:
        if not self.envido_resolution:
            return None
        reports = self.envido_resolution["reports"]
        return {
            "offer": self.envido_resolution["offer"],
            "submitted": [seat in reports for seat in (0, 1)],
            "reports": [
                (reports[seat]["value"] if reports[seat]["show"] or seat == player
                 else None) if seat in reports else None
                for seat in (0, 1)
            ],
            "hidden": [
                seat in reports and not reports[seat]["show"] for seat in (0, 1)
            ],
        }

    def next_hand(self) -> None:
        if not self.hand_over or self.match_over:
            raise ValueError("La siguiente mano no está disponible.")
        self.mano = 1 - self.mano
        self.hand_number += 1
        self._new_hand()


def choose_bot_card(cards: list[dict[str, Any]]) -> int:
    """Estrategia predefinida: conservar las cartas fuertes."""
    return min(range(len(cards)), key=lambda index: card_rank(
        Card(cards[index]["value"], cards[index]["suit"])))
