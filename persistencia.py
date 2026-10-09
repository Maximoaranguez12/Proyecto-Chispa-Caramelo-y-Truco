"""Acceso a PostgreSQL para usuarios, chat e historial de partidas."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from contextlib import contextmanager
from typing import Any, Generator

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as exc:
    raise RuntimeError(
        "Falta psycopg2-binary. Instala las dependencias con "
        "'python -m pip install -r requirements.txt'."
    ) from exc


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,24}$")
PASSWORD_LENGTH = (8, 128)
SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(24) UNIQUE NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    fecha_registro TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_salt TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS wins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS losses INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS partidas (
    id UUID PRIMARY KEY,
    player_one_id BIGINT NOT NULL REFERENCES usuarios(id),
    player_two_id BIGINT REFERENCES usuarios(id),
    player_one_name VARCHAR(24) NOT NULL,
    player_two_name VARCHAR(24) NOT NULL,
    winner_seat SMALLINT CHECK (winner_seat IN (0, 1)),
    score_one INTEGER NOT NULL,
    score_two INTEGER NOT NULL,
    contra_bot BOOLEAN NOT NULL DEFAULT FALSE,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mensajes (
    id BIGSERIAL PRIMARY KEY,
    partida_id UUID REFERENCES partidas(id) ON DELETE CASCADE,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    contenido VARCHAR(500) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS partida_id UUID
    REFERENCES partidas(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_partidas_player_one ON partidas(player_one_id);
CREATE INDEX IF NOT EXISTS idx_partidas_player_two ON partidas(player_two_id);
CREATE INDEX IF NOT EXISTS idx_mensajes_partida_fecha ON mensajes(partida_id, fecha);
"""


class Persistence:
    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL")
        self.connection_options = {
            "host": os.environ.get("PGHOST", "localhost"),
            "port": os.environ.get("PGPORT", "5432"),
            "dbname": os.environ.get("PGDATABASE", "truco"),
            "user": os.environ.get("PGUSER", "postgres"),
            "password": os.environ.get("PGPASSWORD", ""),
            "connect_timeout": 5,
        }

    @contextmanager
    def _connection(self) -> Generator[Any, None, None]:
        if self.database_url:
            connection = psycopg2.connect(self.database_url)
        else:
            connection = psycopg2.connect(**self.connection_options)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        cursor.execute(statement)

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
        actual_salt = salt or secrets.token_bytes(16)
        password_hash = hashlib.scrypt(
            password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1
        )
        return actual_salt.hex(), password_hash.hex()

    def authenticate(self, action: str, username: str, password: str) -> dict[str, Any]:
        if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
            raise ValueError("El usuario debe tener 3-24 caracteres: letras, números o _.")
        if not isinstance(password, str):
            raise ValueError("La contraseña debe ser texto.")
        if not PASSWORD_LENGTH[0] <= len(password) <= PASSWORD_LENGTH[1]:
            raise ValueError("La contraseña debe tener entre 8 y 128 caracteres.")

        with self._connection() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT id, username, password_salt, password_hash, wins, losses "
                    "FROM usuarios WHERE username = %s",
                    (username,),
                )
                row = cursor.fetchone()
                if action == "register":
                    if row:
                        raise ValueError("Ese nombre de usuario ya está registrado.")
                    salt, password_hash = self._hash_password(password)
                    cursor.execute(
                        "INSERT INTO usuarios (username, password_salt, password_hash) "
                        "VALUES (%s, %s, %s) RETURNING id, username, wins, losses",
                        (username, salt, password_hash),
                    )
                    row = cursor.fetchone()
                elif action == "login":
                    if not row:
                        raise ValueError("Usuario o contraseña incorrectos.")
                    if not row["password_salt"]:
                        raise ValueError(
                            "Esta cuenta es anterior al sistema de contraseñas actual; "
                            "debe registrarse de nuevo con otro usuario."
                        )
                    _, password_hash = self._hash_password(
                        password, bytes.fromhex(row["password_salt"])
                    )
                    if not hmac.compare_digest(password_hash, row["password_hash"]):
                        raise ValueError("Usuario o contraseña incorrectos.")
                else:
                    raise ValueError("Acción de autenticación inválida.")
                return {"id": row["id"], "username": row["username"],
                        "wins": row["wins"], "losses": row["losses"]}

    def save_chat(self, match_id: str, user_id: int, message: str) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO mensajes (partida_id, usuario_id, contenido) "
                    "VALUES (%s, %s, %s)",
                    (match_id, user_id, message),
                )

    def create_match(self, match_id: str, players: list[dict[str, Any]],
                     against_bot: bool) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO partidas "
                    "(id, player_one_id, player_two_id, player_one_name, player_two_name, "
                    "winner_seat, score_one, score_two, contra_bot) "
                    "VALUES (%s, %s, %s, %s, %s, NULL, 0, 0, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (match_id, players[0]["id"],
                     None if against_bot else players[1]["id"],
                     players[0]["username"], players[1]["username"],
                     against_bot),
                )

    def save_match(self, match_id: str, players: list[dict[str, Any]],
                   winner: int, scores: list[int], against_bot: bool) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE partidas SET winner_seat = %s, score_one = %s, score_two = %s "
                    "WHERE id = %s AND winner_seat IS NULL",
                    (winner, scores[0], scores[1], match_id),
                )
                if cursor.rowcount == 0:
                    return
                cursor.execute(
                    "UPDATE usuarios SET wins = wins + 1 WHERE id = %s"
                    if winner == 0 else
                    "UPDATE usuarios SET losses = losses + 1 WHERE id = %s",
                    (players[0]["id"],),
                )
                if not against_bot:
                    cursor.execute(
                        "UPDATE usuarios SET wins = wins + 1 WHERE id = %s"
                        if winner == 1 else
                        "UPDATE usuarios SET losses = losses + 1 WHERE id = %s",
                        (players[1]["id"],),
                    )
