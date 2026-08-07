-- Creacion de base de datos (ejecutar esto desde fuera de , ej. conectado a "postgres")
CREATE DATABASE chat_db;

-- A partir de acá, conectarse a chat_db y ejecutar lo siguiente:

-- 1. Usuarios
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Mensajes
CREATE TABLE mensajes (
    id SERIAL PRIMARY KEY,
    usuario_id INT REFERENCES usuarios(id),
    contenido TEXT NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Conexiones
CREATE TABLE conexiones (
    id SERIAL PRIMARY KEY,
    usuario_id INT REFERENCES usuarios(id),
    tipo VARCHAR(15) NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. API calls
CREATE TABLE api_calls (
    id SERIAL PRIMARY KEY,
    usuario_id INT REFERENCES usuarios(id),
    comando VARCHAR(50) NOT NULL,
    url_resultado TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);