"""Cliente gráfico Pygame para el servidor de Truco Argentino."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from typing import Any

import pygame

WIDTH, HEIGHT = 1100, 760
BG = (23, 92, 65)
PANEL = (18, 65, 49)
CREAM = (250, 239, 204)
GOLD = (234, 188, 83)
RED = (165, 49, 43)
WHITE = (255, 255, 255)


class NetworkClient:
    """Mantiene la conexión TCP y transfiere mensajes JSON en segundo plano."""

    def __init__(self, host: str, port: int) -> None:
        """Conecta al servidor y arranca el hilo que recibe sus mensajes."""
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(None)
        self.incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self.send_lock = threading.Lock()
        threading.Thread(target=self._receive, daemon=True).start()

    def send(self, payload: dict[str, Any]) -> None:
        """Serializa un mensaje JSON y lo envía como una línea completa."""
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        with self.send_lock:
            self.sock.sendall(data)

    def _receive(self) -> None:
        """Lee respuestas sin bloquear el bucle gráfico y las pone en la cola."""
        try:
            stream = self.sock.makefile("r", encoding="utf-8", newline="\n")
            for line in stream:
                self.incoming.put(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            self.incoming.put({"type": "error", "message": f"Conexión cerrada: {exc}"})

    def close(self) -> None:
        """Cierra ordenadamente el socket al salir del cliente."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class TrucoClient:
    """Administra las pantallas, los controles y el estado visual del juego."""

    def __init__(self, host: str, port: int) -> None:
        """Inicializa Pygame y prepara el estado local de la interfaz."""
        pygame.init()
        pygame.display.set_caption("Chispa, Caramelo y Truco")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 22)
        self.small_font = pygame.font.SysFont("segoeui", 17)
        self.title_font = pygame.font.SysFont("segoeui", 38, bold=True)
        self.host, self.port = host, port
        self.network: NetworkClient | None = None
        self.scene = "auth"
        self.auth_action = "login"
        self.username = ""
        self.password = ""
        self.active_field = "username"
        self.user: dict[str, Any] | None = None
        self.state: dict[str, Any] | None = None
        self.chat_lines: list[str] = []
        self.chat_input = ""
        self.notice = ""
        self.running = True
        self.burn_mode = False
        self.card_rects: list[pygame.Rect] = []

    def _text(self, text: str, x: int, y: int, color: tuple[int, int, int] = WHITE,
              font: pygame.font.Font | None = None) -> None:
        """Dibuja texto en la ventana usando la fuente indicada o la normal."""
        rendered = (font or self.font).render(text, True, color)
        self.screen.blit(rendered, (x, y))

    def _button(self, label: str, rect: pygame.Rect,
                color: tuple[int, int, int] = GOLD) -> bool:
        """Dibuja un botón y devuelve si el cursor está encima."""
        pygame.draw.rect(self.screen, color, rect, border_radius=9)
        pygame.draw.rect(self.screen, CREAM, rect, width=2, border_radius=9)
        rendered = self.font.render(label, True, (35, 35, 30))
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))
        return rect.collidepoint(pygame.mouse.get_pos())

    def _connect(self) -> bool:
        """Abre la conexión una sola vez; informa el error en la interfaz."""
        if self.network:
            return True
        try:
            self.network = NetworkClient(self.host, self.port)
            return True
        except OSError as exc:
            self.notice = f"No se pudo conectar a {self.host}:{self.port}: {exc}"
            return False

    def _send(self, payload: dict[str, Any]) -> None:
        """Envía una acción al servidor y convierte errores en avisos visibles."""
        try:
            if self.network is None:
                raise OSError("No hay conexión con el servidor.")
            self.network.send(payload)
        except OSError as exc:
            self.notice = str(exc)

    def _handle_messages(self) -> None:
        """Consume las respuestas de red y actualiza usuario, partida o avisos."""
        if not self.network:
            return
        while True:
            try:
                message = self.network.incoming.get_nowait()
            except queue.Empty:
                return
            kind = message.get("type")
            if kind == "authenticated":
                self.user = message["user"]
                self.scene = "lobby"
                self.notice = f"¡Bienvenido, {self.user['username']}!"
            elif kind in ("match_found", "game_state"):
                self.state = message["state"]
                self.scene = "game"
                self.notice = self.state.get("event", "")
            elif kind == "queued":
                self.notice = "Buscando rival…"
            elif kind == "chat":
                self.chat_lines.append(f"{message['username']}: {message['message']}")
                self.chat_lines = self.chat_lines[-5:]
            elif kind == "error":
                self.notice = message.get("message", "Error del servidor.")

    def _draw_auth(self) -> None:
        """Dibuja la pantalla para ingresar o crear una cuenta."""
        self._text("Chispa, Caramelo y Truco", 325, 100, GOLD, self.title_font)
        self._text("Truco Argentino  ·  partidas 1 vs 1", 387, 155, CREAM)
        self._text("Nombre de usuario", 345, 250, CREAM)
        self._text("Contraseña", 345, 340, CREAM)
        for field, rect, value in (
                ("username", pygame.Rect(345, 282, 410, 46), self.username),
                ("password", pygame.Rect(345, 372, 410, 46), "*" * len(self.password))):
            pygame.draw.rect(self.screen, CREAM, rect, border_radius=7)
            pygame.draw.rect(self.screen, GOLD if self.active_field == field else PANEL,
                             rect, width=3, border_radius=7)
            self._text(value, rect.x + 12, rect.y + 9, (35, 35, 30))
        label = "Ingresar" if self.auth_action == "login" else "Crear cuenta"
        self._button(label, pygame.Rect(345, 450, 195, 52))
        self._button("Cambiar a registro" if self.auth_action == "login" else
                     "Volver a ingresar", pygame.Rect(560, 450, 240, 52), CREAM)
        self._text("La contraseña requiere al menos 8 caracteres.", 345, 525,
                   CREAM, self.small_font)
        if self.notice:
            self._text(self.notice[:85], 250, 620, GOLD, self.small_font)

    def _draw_lobby(self) -> None:
        """Dibuja el perfil del usuario y las opciones para buscar partida."""
        self._text("¡A la mesa!", 395, 140, GOLD, self.title_font)
        if self.user:
            self._text(f"Jugador: {self.user['username']}", 430, 210, CREAM)
            self._text(f"Victorias: {self.user['wins']}   Derrotas: {self.user['losses']}",
                       380, 250, CREAM)
        self._button("Jugar contra bot", pygame.Rect(350, 340, 400, 64))
        self._button("Buscar rival en línea", pygame.Rect(350, 425, 400, 64), CREAM)
        self._text("Para jugar en red, inicia el servidor y conecta ambos clientes.",
                   290, 535, CREAM, self.small_font)
        if self.notice:
            self._text(self.notice[:85], 275, 600, GOLD, self.small_font)

    def _draw_card(self, card: dict[str, Any], rect: pygame.Rect) -> None:
        """Dibuja una carta con su valor numérico y el nombre de su palo."""
        pygame.draw.rect(self.screen, CREAM, rect, border_radius=10)
        pygame.draw.rect(self.screen, GOLD, rect, width=3, border_radius=10)
        suit = card["suit"]
        color = RED if suit in ("oros", "copas") else (35, 50, 53)
        self._text(str(card["value"]), rect.x + 13, rect.y + 17, color)
        self._text("de " + suit, rect.x + 13, rect.y + 49,
                   color, self.small_font)

    def _draw_game(self) -> None:
        """Dibuja el tablero, cartas, mensajes y controles válidos del turno."""
        state = self.state
        if not state:
            return
        pygame.draw.rect(self.screen, PANEL, (0, 0, WIDTH, 94))
        players, scores = state["players"], state["scores"]
        self._text(f"{players[0]}  {scores[0]}", 40, 29, CREAM)
        self._text("VS", 520, 29, GOLD, self.title_font)
        self._text(f"{players[1]}  {scores[1]}", 810, 29, CREAM)
        if self.notice:
            self._text(self.notice[:95], 20, 98, GOLD, self.small_font)
        self._text(f"Mano: {players[state['mano']]}  ·  Baza {state['trick']}",
                   410, 118, CREAM, self.small_font)
        self._text(state.get("event", "")[:90], 140, 165, GOLD)
        burned = [players[seat] for seat, value in enumerate(state["burned"]) if value]
        if burned:
            self._text("Carta quemada: " + ", ".join(burned), 20, 205,
                       CREAM, self.small_font)
        if self.burn_mode:
            self._text("Elige la carta que vas a quemar.", 385, 505, GOLD,
                       self.small_font)
        pending = state.get("truco_pending") or state.get("envido_pending")
        resolution = state.get("envido_resolution")
        if pending:
            label = "Truco" if state.get("truco_pending") else "Envido"
            status = ("Esperando tu respuesta." if pending["caller"] != state["you"]
                      else "Esperando respuesta del rival.")
            self._text(f"{label} pendiente. {status}", 370, 212, CREAM)
        if resolution:
            own_report = resolution["reports"][state["you"]]
            status = ("Tu tanto está oculto." if resolution["hidden"][state["you"]]
                      else f"Tu declaración: {own_report} tantos."
                      if own_report is not None else "Declara tu tanto en el chat.")
            self._text(status, 20, 212, CREAM, self.small_font)
            self._text("Chat: /tanto N  ·  /tanto-oculto N  ·  /reclamar",
                       20, 235, GOLD, self.small_font)

        pygame.draw.rect(self.screen, (32, 117, 77), (115, 250, 870, 250),
                         border_radius=30)
        pygame.draw.rect(self.screen, GOLD, (115, 250, 870, 250), 2,
                         border_radius=30)
        for seat, plays in enumerate(state["played"]):
            for index, play in enumerate(plays[-3:]):
                rect = pygame.Rect(300 + index * 120, 290 + seat * 104, 102, 88)
                self._draw_card(play["card"], rect)
        self._text(f"Cartas del rival: {state['opponent_card_count']}",
                   420, 225, CREAM, self.small_font)
        for index, line in enumerate(self.chat_lines[-3:]):
            self._text(line[:55], 20, 120 + index * 22, CREAM, self.small_font)

        self.card_rects.clear()
        cards = state["hands"]
        start_x = (WIDTH - len(cards) * 150) // 2
        for index, card in enumerate(cards):
            rect = pygame.Rect(start_x + index * 150, 530, 132, 135)
            self.card_rects.append(rect)
            self._draw_card(card, rect)

        pygame.draw.rect(self.screen, PANEL, (0, 680, WIDTH, 80))
        pending = state.get("truco_pending") or state.get("envido_pending")
        is_responder = pending and pending["caller"] != state["you"]
        if state.get("hand_over") and not state.get("match_over"):
            self._button("Siguiente mano", pygame.Rect(20, 690, 205, 50))
        elif state.get("match_over"):
            self._text(f"Partida finalizada. Ganó {players[state['winner']]}",
                       25, 699, GOLD)
        elif state.get("envido_resolution"):
            reports = state["envido_resolution"]["submitted"]
            if all(reports):
                self._button("Reclamar", pygame.Rect(500, 690, 150, 50), CREAM)
                self._text("Juega una carta para aceptar.", 30, 700,
                           CREAM, self.small_font)
            else:
                self._text("Esperando las declaraciones de ambos tantos…",
                           30, 700, CREAM, self.small_font)
        elif is_responder and state.get("envido_pending"):
            self._button("Quiero", pygame.Rect(220, 690, 130, 50))
            self._button("No quiero", pygame.Rect(360, 690, 145, 50), CREAM)
        elif is_responder:
            self._button("Quiero", pygame.Rect(235, 690, 135, 50))
            self._button("No quiero", pygame.Rect(380, 690, 155, 50), CREAM)
        elif pending:
            self._text("Esperando respuesta del rival…", 225, 700, CREAM)
        elif state["turn"] == state["you"] and not state.get("hand_over"):
            self._button("Truco", pygame.Rect(20, 690, 100, 50))
            if state["envido_available"]:
                self._button("Envido", pygame.Rect(130, 690, 115, 50), CREAM)
                self._button("Real", pygame.Rect(255, 690, 105, 50))
                self._button("Falta", pygame.Rect(370, 690, 105, 50), CREAM)
            else:
                self._text("Envido cerrado", 135, 705, CREAM, self.small_font)
            if not state["burned"][state["you"]] and len(state["hands"]) > 1:
                self._button("Quemar", pygame.Rect(485, 690, 120, 50))
        else:
            self._text("Esperando al rival…", 30, 700, CREAM, self.small_font)
        self._text("Chat (Enter):", 700, 695, GOLD, self.small_font)
        self._text(self.chat_input[-34:], 825, 695, CREAM, self.small_font)

    def _auth_submit(self) -> None:
        """Valida que haya conexión y envía la operación de acceso elegida."""
        if not self._connect():
            return
        self._send({"action": self.auth_action, "username": self.username,
                    "password": self.password})
        self.password = ""
        self.notice = "Conectando…"

    def _click(self, position: tuple[int, int]) -> None:
        """Traduce un clic en la pantalla activa a una acción para el servidor."""
        if self.scene == "auth":
            if pygame.Rect(345, 282, 410, 46).collidepoint(position):
                self.active_field = "username"
            elif pygame.Rect(345, 372, 410, 46).collidepoint(position):
                self.active_field = "password"
            elif pygame.Rect(345, 450, 195, 52).collidepoint(position):
                self._auth_submit()
            elif pygame.Rect(560, 450, 240, 52).collidepoint(position):
                self.auth_action = "register" if self.auth_action == "login" else "login"
            return
        if self.scene == "lobby":
            if pygame.Rect(350, 340, 400, 64).collidepoint(position):
                self._send({"action": "play_bot"})
            elif pygame.Rect(350, 425, 400, 64).collidepoint(position):
                self._send({"action": "queue"})
            return
        state = self.state
        if not state:
            return
        if state.get("hand_over") and not state.get("match_over"):
            if pygame.Rect(20, 690, 205, 50).collidepoint(position):
                self._send({"action": "next_hand"})
        elif state.get("truco_pending") or state.get("envido_pending"):
            pending = state.get("truco_pending") or state.get("envido_pending")
            if pending["caller"] != state["you"]:
                action = ("respond_truco" if state.get("truco_pending")
                          else "respond_envido")
                if pygame.Rect(220, 690, 150, 50).collidepoint(position):
                    self._send({"action": action, "accept": True})
                elif pygame.Rect(360, 690, 155, 50).collidepoint(position):
                    self._send({"action": action, "accept": False})
        elif state.get("envido_resolution"):
            if (all(state["envido_resolution"]["submitted"]) and
                    pygame.Rect(500, 690, 150, 50).collidepoint(position)):
                self._send({"action": "chat", "message": "/reclamar"})
            elif (all(state["envido_resolution"]["submitted"]) and
                  state["turn"] == state["you"] and not state.get("hand_over")):
                for index, rect in enumerate(self.card_rects):
                    if rect.collidepoint(position):
                        self._send({"action": "play_card", "card_index": index})
                        break
        else:
            if state["turn"] != state["you"] or state.get("hand_over"):
                return
            if pygame.Rect(485, 690, 120, 50).collidepoint(position):
                self.burn_mode = not self.burn_mode
                self.notice = "Selecciona una carta para quemarla." if self.burn_mode else ""
            elif pygame.Rect(20, 690, 100, 50).collidepoint(position):
                level = state["truco_level"]
                call = {1: "truco", 2: "retruco", 3: "vale_cuatro"}.get(level)
                if call:
                    self._send({"action": "call_truco", "call": call})
            elif (state["envido_available"] and
                  pygame.Rect(130, 690, 115, 50).collidepoint(position)):
                self._send({"action": "call_envido", "call": "envido"})
            elif (state["envido_available"] and
                  pygame.Rect(255, 690, 105, 50).collidepoint(position)):
                self._send({"action": "call_envido", "call": "real_envido"})
            elif (state["envido_available"] and
                  pygame.Rect(370, 690, 105, 50).collidepoint(position)):
                self._send({"action": "call_envido", "call": "falta_envido"})
            else:
                for index, rect in enumerate(self.card_rects):
                    if (state["turn"] == state["you"] and not state.get("hand_over")
                            and rect.collidepoint(position)):
                        self._send({"action": "burn_card" if self.burn_mode else "play_card",
                                    "card_index": index})
                        self.burn_mode = False
                        break

    def _key(self, event: pygame.event.Event) -> None:
        """Procesa teclas para los campos de acceso y el chat de la partida."""
        if self.scene == "auth":
            if event.key == pygame.K_TAB:
                self.active_field = ("password" if self.active_field == "username"
                                     else "username")
            elif event.key == pygame.K_RETURN:
                self._auth_submit()
            elif event.key == pygame.K_BACKSPACE:
                if self.active_field == "username":
                    self.username = self.username[:-1]
                else:
                    self.password = self.password[:-1]
            elif event.unicode.isprintable():
                if self.active_field == "username" and len(self.username) < 24:
                    self.username += event.unicode
                elif self.active_field == "password" and len(self.password) < 128:
                    self.password += event.unicode
        elif self.scene == "game" and event.key == pygame.K_RETURN:
            if self.chat_input.strip():
                self._send({"action": "chat", "message": self.chat_input.strip()})
                self.chat_input = ""
        elif self.scene == "game" and event.key == pygame.K_BACKSPACE:
            self.chat_input = self.chat_input[:-1]
        elif self.scene == "game" and event.unicode.isprintable():
            if len(self.chat_input) < 500:
                self.chat_input += event.unicode

    def run(self) -> None:
        """Ejecuta el bucle gráfico hasta que se cierre la ventana."""
        while self.running:
            self._handle_messages()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self._key(event)
            self.screen.fill(BG)
            if self.scene == "auth":
                self._draw_auth()
            elif self.scene == "lobby":
                self._draw_lobby()
            else:
                self._draw_game()
            pygame.display.flip()
            self.clock.tick(60)
        if self.network:
            self.network.close()
        pygame.quit()


def main() -> None:
    """Lee los parámetros de conexión y arranca la interfaz del cliente."""
    parser = argparse.ArgumentParser(description="Cliente de Chispa, Caramelo y Truco")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Dirección del servidor (por defecto: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=12345)
    arguments = parser.parse_args()
    TrucoClient(arguments.host, arguments.port).run()


if __name__ == "__main__":
    main()
