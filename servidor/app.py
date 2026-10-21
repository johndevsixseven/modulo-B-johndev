"""app.py — ponto de entrada do servidor VaxGuard Connect.

Rodar:  python app.py   (ouve em 0.0.0.0:5000)
"""
import logging
import os
import secrets

from flask import Flask
from werkzeug.security import generate_password_hash

import banco
from api import api
from painel import painel

PASTA = os.path.dirname(os.path.abspath(__file__))


def caminho_banco():
    return os.environ.get("VAXGUARD_BANCO") or os.path.join(PASTA, "vaxguard.db")


def configurar_log():
    """Log em logs/servidor.log e no console."""
    log = logging.getLogger("vaxguard")
    if log.handlers:
        return
    os.makedirs(os.path.join(PASTA, "logs"), exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.FileHandler(os.path.join(PASTA, "logs", "servidor.log"), encoding="utf-8"),
                    logging.StreamHandler()):
        handler.setFormatter(formato)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def criar_usuarios_iniciais(con):
    """Na primeira execução cria 'admin' e 'operador'. Senha da variável de ambiente ou gerada e impressa."""
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        return
    for nome, perfil, variavel in (("admin", "ADMINISTRADOR", "VAXGUARD_SENHA_ADMIN"),
                                   ("operador", "OPERADOR", "VAXGUARD_SENHA_OPERADOR")):
        senha = os.environ.get(variavel)
        if not senha:
            senha = secrets.token_urlsafe(9)
            print(f"*** Usuário '{nome}' ({perfil}) criado com a senha: {senha}  -> anote, não aparece de novo!")
        con.execute("INSERT INTO usuarios (nome, senha_hash, perfil) VALUES (?, ?, ?)",
                    (nome, generate_password_hash(senha), perfil))
    con.commit()


def criar_app(caminho=None):
    app = Flask(__name__)
    # Sem a variável, gera uma chave nova a cada início (todos precisam logar de novo).
    app.config["SECRET_KEY"] = os.environ.get("VAXGUARD_SECRET_KEY") or secrets.token_hex(32)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # outro site não consegue enviar formulário com a sessão
    app.config["BANCO"] = caminho or caminho_banco()
    configurar_log()

    con = banco.conectar(app.config["BANCO"])
    banco.criar_tabelas(con)
    criar_usuarios_iniciais(con)
    con.close()

    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(painel)
    app.teardown_appcontext(banco.fechar)
    return app


if __name__ == "__main__":
    criar_app().run(host="0.0.0.0", port=5000)
