-- Crear primero la base desde psql:
-- CREATE DATABASE truco;
-- Luego ejecutar: psql -U postgres -d truco -f BD.Sql

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(24) UNIQUE NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    fecha_registro TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS partidas (
    id UUID PRIMARY KEY,
    player_one_id BIGINT NOT NULL REFERENCES usuarios(id),
    player_two_id BIGINT REFERENCES usuarios(id),
    player_one_name VARCHAR(24) NOT NULL,
    player_two_name VARCHAR(24) NOT NULL,
    winner_seat SMALLINT CHECK (winner_seat IN (0, 1)),
    score_one INTEGER NOT NULL DEFAULT 0,
    score_two INTEGER NOT NULL DEFAULT 0,
    contra_bot BOOLEAN NOT NULL DEFAULT FALSE,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mensajes (
    id BIGSERIAL PRIMARY KEY,
    partida_id UUID NOT NULL REFERENCES partidas(id) ON DELETE CASCADE,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    contenido VARCHAR(500) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_partidas_player_one ON partidas(player_one_id);
CREATE INDEX IF NOT EXISTS idx_partidas_player_two ON partidas(player_two_id);
CREATE INDEX IF NOT EXISTS idx_mensajes_partida_fecha ON mensajes(partida_id, fecha);
