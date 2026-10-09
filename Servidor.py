"""Servidor TCP de Truco Argentino: autenticación, partidas y chat JSON."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from psycopg2 import OperationalError

from persistencia import Persistence
from truco import Card, TrucoGame, card_rank, choose_bot_card, envido_value

HOST = os.environ.get("TRUCO_HOST", "0.0.0.0")
PORT = int(os.environ.get("TRUCO_PORT", "12345"))
MAX_MESSAGE_LENGTH = 8192
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


@dataclass(eq=False)
class Client:
    sock: socket.socket
    address: tuple[str, int]
    send_lock: threading.Lock = field(default_factory=threading.Lock)
    user: dict[str, Any] | None = None
    match_id: str | None = None

    def send(self, message: dict[str, Any]) -> None:
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self.send_lock:
            self.sock.sendall(payload)


@dataclass
class Match:
    id: str
    players: list[Client]
    game: TrucoGame
    against_bot: bool = False
    saved: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)


class GameServer:
    def __init__(self, database: Persistence) -> None:
        self.database = database
        self.clients: set[Client] = set()
        self.waiting: list[Client] = []
        self.matches: dict[str, Match] = {}
        self.lock = threading.RLock()
        self.running = True

    def _error(self, client: Client, message: str) -> None:
        client.send({"type": "error", "message": message})

    @staticmethod
    def _match_users(match: Match) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        for player in match.players:
            if player.user is None:
                raise ValueError("Todos los jugadores deben iniciar sesión.")
            users.append(player.user)
        return users

    def _send_state(self, match: Match, event_type: str = "game_state") -> None:
        for seat, client in enumerate(match.players):
            if client.user is None or client.user.get("id") is None:
                continue
            try:
                client.send({"type": event_type,
                             "state": match.game.snapshot(seat)})
            except OSError:
                logging.info("No se pudo notificar estado a %s", client.address)

    def _create_match(self, players: list[Client],
                      against_bot: bool = False) -> Match:
        match_id = str(uuid.uuid4())
        if against_bot:
            bot = Client(sock=players[0].sock, address=players[0].address)
            bot.user = {"id": None, "username": "Bot Truquero",
                        "wins": 0, "losses": 0}
            match_players = [players[0], bot]
        else:
            match_players = players
        game = TrucoGame([player.user["username"] for player in match_players])
        match = Match(match_id, match_players, game, against_bot)
        self.database.create_match(match_id, self._match_users(match), against_bot)
        self.matches[match_id] = match
        for player in match_players:
            player.match_id = match_id
        self._send_state(match, "match_found")
        logging.info("Partida %s iniciada (%s)", match_id,
                     "contra bot" if against_bot else "entre usuarios")
        return match

    def _get_match(self, client: Client) -> Match:
        if not client.match_id or client.match_id not in self.matches:
            raise ValueError("No estás en una partida.")
        return self.matches[client.match_id]

    def _persist_result(self, match: Match) -> None:
        if not match.game.match_over or match.saved:
            return
        match.saved = True
        try:
            self.database.save_match(
                match.id, self._match_users(match),
                match.game.winner if match.game.winner is not None else 0,
                match.game.scores, match.against_bot
            )
        except Exception:
            match.saved = False
            logging.exception("No se pudo guardar la partida %s", match.id)
            for player in match.players:
                if player.user and player.user.get("id") is not None:
                    self._error(player, "La partida terminó, pero no se pudo guardar el historial.")

    @staticmethod
    def _bot_card_rank(cards: list[Card]) -> int:
        return max((card_rank(card) for card in cards), default=0)

    def _run_bot(self, match: Match) -> None:
        if not match.against_bot or match.game.hand_over:
            return
        game = match.game
        bot_seat = 1
        if game.truco_pending and game.truco_pending["caller"] != bot_seat:
            best = self._bot_card_rank(game.hands[bot_seat])
            game.respond_truco(bot_seat, best >= 7)
        if game.envido_pending and game.envido_pending["caller"] != bot_seat:
            game.respond_envido(
                bot_seat, envido_value(game.envido_hands[bot_seat]) >= 23
            )
        if game.envido_resolution and bot_seat not in game.envido_resolution["reports"]:
            game.report_tanto(bot_seat, envido_value(game.envido_hands[bot_seat]))
        if (game.envido_resolution and len(game.envido_resolution["reports"]) == 2 and
                game.turn == bot_seat):
            user_report = game.envido_resolution["reports"][0]
            user_tanto = envido_value(game.envido_hands[0])
            if not user_report["show"] or user_report["value"] != user_tanto:
                game.challenge_tanto()
        if (not game.hand_over and not game.truco_pending and
                not game.match_over and not game.envido_pending and
                (not game.envido_resolution or
                 len(game.envido_resolution["reports"]) == 2) and
                game.turn == bot_seat):
            cards = [card.to_dict() for card in game.hands[bot_seat]]
            if cards:
                game.play_card(bot_seat, choose_bot_card(cards))

    def _new_hand(self, match: Match) -> None:
        match.game.next_hand()
        self._send_state(match)

    def _handle_match_action(self, client: Client, message: dict[str, Any]) -> None:
        with self.lock:
            match = self._get_match(client)
        with match.lock:
            game = match.game
            try:
                action = message.get("action")
                player = match.players.index(client)
                if action == "play_card":
                    game.play_card(player, message.get("card_index"))
                elif action == "burn_card":
                    game.burn_card(player, message.get("card_index"))
                elif action == "call_truco":
                    game.call_truco(player, message.get("call"))
                elif action == "respond_truco":
                    accept = message.get("accept")
                    if not isinstance(accept, bool):
                        raise ValueError("La respuesta debe ser quiero o no quiero.")
                    game.respond_truco(player, accept)
                elif action == "call_envido":
                    game.call_envido(player, message.get("call"))
                elif action == "respond_envido":
                    accept = message.get("accept")
                    if not isinstance(accept, bool):
                        raise ValueError("La respuesta debe ser quiero o no quiero.")
                    game.respond_envido(player, accept)
                elif action == "next_hand":
                    self._new_hand(match)
                    return
                elif action == "resign":
                    game._finish_hand(1 - player, game.truco_level,
                                      f"{client.user['username']} se fue al mazo.")
                    game.match_over = True
                else:
                    raise ValueError("Acción de partida desconocida.")
                self._run_bot(match)
                self._send_state(match)
                self._persist_result(match)
            except ValueError as exc:
                self._error(client, str(exc))

    def _handle_chat(self, client: Client, message: dict[str, Any]) -> None:
        text = message.get("message")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError("El mensaje debe tener entre 1 y 500 caracteres.")
        match = self._get_match(client)
        with match.lock:
            player = match.players.index(client)
            parts = text.strip().split()
            command = parts[0].lower()
            if command in ("/tanto", "/tanto-oculto"):
                if len(parts) != 2 or not parts[1].isdecimal():
                    raise ValueError("Usa /tanto 33 o /tanto-oculto 33 (de 0 a 33).")
                game = match.game
                game.report_tanto(player, int(parts[1]), command == "/tanto")
                self._run_bot(match)
                self._send_state(match)
                self._persist_result(match)
                return
            if command == "/reclamar":
                if len(parts) != 1:
                    raise ValueError("El comando /reclamar no lleva argumentos.")
                match.game.challenge_tanto()
                self._run_bot(match)
                self._send_state(match)
                self._persist_result(match)
                return
            self.database.save_chat(match.id, client.user["id"], text.strip())
            for player in match.players:
                if player.user and player.user.get("id") is not None:
                    try:
                        player.send({"type": "chat", "username": client.user["username"],
                                     "message": text.strip()})
                    except OSError:
                        logging.info("No se pudo entregar chat a %s", player.address)

    def _handle_authenticated(self, client: Client,
                              message: dict[str, Any]) -> None:
        action = message.get("action")
        if action in ("register", "login"):
            if client.user:
                raise ValueError("Ya iniciaste sesión.")
            user = self.database.authenticate(action, message.get("username", ""),
                                              message.get("password", ""))
            client.user = user
            client.send({"type": "authenticated", "user": user})
            logging.info("Usuario %s autenticado desde %s",
                         user["username"], client.address)
        elif not client.user:
            raise ValueError("Primero debes iniciar sesión.")
        elif action == "queue":
            with self.lock:
                if client.match_id:
                    raise ValueError("Ya estás en una partida.")
                if client not in self.waiting:
                    self.waiting.append(client)
                    client.send({"type": "queued"})
                if len(self.waiting) >= 2:
                    first, second = self.waiting.pop(0), self.waiting.pop(0)
                    if first.user and second.user:
                        try:
                            self._create_match([first, second])
                        except Exception:
                            self._error(first, "No se pudo crear la partida. Intenta nuevamente.")
                            self._error(second, "No se pudo crear la partida. Intenta nuevamente.")
                            raise
        elif action == "play_bot":
            with self.lock:
                if client.match_id:
                    raise ValueError("Ya estás en una partida.")
                self._create_match([client], against_bot=True)
        elif action == "chat":
            self._handle_chat(client, message)
        else:
            self._handle_match_action(client, message)

    def handle_client(self, client: Client) -> None:
        try:
            stream = client.sock.makefile("r", encoding="utf-8", newline="\n")
            for line in stream:
                if len(line) > MAX_MESSAGE_LENGTH:
                    self._error(client, "Mensaje demasiado largo.")
                    break
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("El mensaje debe ser un objeto JSON.")
                    self._handle_authenticated(client, message)
                except (ValueError, json.JSONDecodeError) as exc:
                    self._error(client, str(exc))
                except (OSError, RuntimeError):
                    logging.exception("Error al procesar solicitud de %s", client.address)
                    self._error(client, "Error interno del servidor.")
                except Exception:
                    logging.exception("No se pudo completar la solicitud de %s",
                                      client.address)
                    self._error(client, "No se pudo completar la solicitud.")
        except (ConnectionResetError, BrokenPipeError, OSError):
            logging.info("Conexión cerrada por %s", client.address)
        finally:
            self._disconnect(client)

    def _disconnect(self, client: Client) -> None:
        with self.lock:
            if client in self.waiting:
                self.waiting.remove(client)
            self.clients.discard(client)
            match = self.matches.get(client.match_id or "")
            if match and not match.game.match_over:
                with match.lock:
                    try:
                        seat = match.players.index(client)
                        match.game._finish_hand(
                            1 - seat, match.game.truco_level,
                            f"{client.user['username'] if client.user else 'El rival'} se desconectó."
                        )
                        match.game.match_over = True
                        self._send_state(match)
                        self._persist_result(match)
                    except ValueError:
                        logging.exception("El cliente no figuraba en su partida %s",
                                          match.id)
            client.match_id = None
            try:
                client.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.sock.close()

    def serve_forever(self) -> None:
        self.database.initialize()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(32)
            logging.info("Servidor escuchando en %s:%s", HOST, PORT)
            while self.running:
                sock, address = server.accept()
                client = Client(sock=sock, address=address)
                with self.lock:
                    self.clients.add(client)
                threading.Thread(target=self.handle_client, args=(client,),
                                 daemon=True).start()


def main() -> None:
    database = Persistence()
    try:
        GameServer(database).serve_forever()
    except OperationalError as exc:
        logging.critical(
            "No se pudo conectar a PostgreSQL. Comprueba que el servicio esté "
            "iniciado y configura PGHOST, PGPORT, PGDATABASE, PGUSER y "
            "PGPASSWORD en esta misma terminal. Detalle: %s",
            exc,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
