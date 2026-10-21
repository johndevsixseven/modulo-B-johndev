"""banco.py — conexão com o SQLite e criação das tabelas."""
import sqlite3
import time

from flask import current_app, g

ESQUEMA = """
CREATE TABLE IF NOT EXISTS dispositivos (
    id             TEXT PRIMARY KEY,            -- ex.: VG-CAM01
    nome           TEXT NOT NULL,
    placa          TEXT NOT NULL,               -- UNO_R4_WIFI, ESP32 ou SIMULADOR
    temp_min       REAL NOT NULL DEFAULT 2.0,   -- faixa ideal (°C)
    temp_max       REAL NOT NULL DEFAULT 8.0,
    intervalo_s    INTEGER NOT NULL DEFAULT 5,  -- intervalo entre leituras
    ultimo_contato INTEGER,                     -- epoch da última mensagem recebida
    risco_ativo    INTEGER NOT NULL DEFAULT 0,  -- 1 = já existe alerta de risco aberto
    criado_em      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS leituras (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id TEXT NOT NULL REFERENCES dispositivos(id),
    seq            INTEGER NOT NULL,
    ts             INTEGER NOT NULL,  -- hora da leitura (do dispositivo ou, se ele não tinha hora, do recebimento)
    ts_dispositivo INTEGER NOT NULL,  -- ts original enviado (0 = sem hora NTP)
    recebido_em    INTEGER NOT NULL,
    temp REAL, umid REAL, temp_ntc REAL, luz_pct REAL,
    porta INTEGER NOT NULL, ventilacao INTEGER NOT NULL, estado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leituras ON leituras(dispositivo_id, ts);

CREATE TABLE IF NOT EXISTS eventos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id TEXT NOT NULL REFERENCES dispositivos(id),
    ts             INTEGER NOT NULL,
    recebido_em    INTEGER NOT NULL,
    de TEXT NOT NULL, para TEXT NOT NULL, motivo TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comandos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id TEXT NOT NULL REFERENCES dispositivos(id),
    tipo           TEXT NOT NULL,
    parametros     TEXT NOT NULL DEFAULT '{}',        -- JSON, ex.: {"min": 2, "max": 8}
    status         TEXT NOT NULL DEFAULT 'PENDENTE',  -- PENDENTE, EXECUTADO ou REJEITADO
    criado_por     TEXT,
    criado_em      INTEGER NOT NULL,
    confirmado_em  INTEGER
);

CREATE TABLE IF NOT EXISTS usuarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil     TEXT NOT NULL CHECK (perfil IN ('OPERADOR', 'ADMINISTRADOR'))
);

CREATE TABLE IF NOT EXISTS alertas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id  TEXT NOT NULL REFERENCES dispositivos(id),
    ts              INTEGER NOT NULL,
    tipo            TEXT NOT NULL,   -- ANOMALIA ou RISCO DE EXCURSÃO
    mensagem        TEXT NOT NULL,
    reconhecido_por TEXT,
    reconhecido_em  INTEGER
);
"""


def agora():
    return int(time.time())


def conectar(caminho):
    con = sqlite3.connect(caminho, timeout=10)
    con.row_factory = sqlite3.Row  # linhas acessíveis por nome: linha["temp"]
    con.execute("PRAGMA foreign_keys = ON")
    return con


def db():
    """Conexão da requisição atual (uma por requisição)."""
    if "db" not in g:
        g.db = conectar(current_app.config["BANCO"])
    return g.db


def fechar(_erro=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def criar_tabelas(con):
    con.executescript(ESQUEMA)


def cadastrar_dispositivo(con, device_id, placa, nome=None, temp_min=2.0, temp_max=8.0):
    """Cadastra se ainda não existe. Devolve True se cadastrou agora."""
    cur = con.execute(
        "INSERT OR IGNORE INTO dispositivos (id, nome, placa, temp_min, temp_max, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
        (device_id, nome or device_id, placa, temp_min, temp_max, agora()),
    )
    return cur.rowcount == 1
