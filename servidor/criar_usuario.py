"""criar_usuario.py — cria um usuário ou troca a senha de um existente.

Uso:  python criar_usuario.py NOME OPERADOR|ADMINISTRADOR   (a senha é pedida no terminal)
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

import banco
from app import caminho_banco

if len(sys.argv) != 3 or sys.argv[2].upper() not in ("OPERADOR", "ADMINISTRADOR"):
    sys.exit(__doc__)
nome, perfil = sys.argv[1], sys.argv[2].upper()
senha = getpass.getpass("Senha: ")
if len(senha) < 6 or senha != getpass.getpass("Repita a senha: "):
    sys.exit("Senhas diferentes ou com menos de 6 caracteres.")

con = banco.conectar(caminho_banco())
banco.criar_tabelas(con)
con.execute("INSERT INTO usuarios (nome, senha_hash, perfil) VALUES (?, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET senha_hash = excluded.senha_hash, perfil = excluded.perfil",
            (nome, generate_password_hash(senha), perfil))
con.commit()
print(f"Usuário '{nome}' ({perfil}) salvo.")
