from contextlib import contextmanager
from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "emissor_nfse.db"


@contextmanager
def conectar():
    """
    Abre uma conexão SQLite e garante o fechamento.
    O commit ocorre automaticamente quando o bloco termina sem erro.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        with conn:
            yield conn
    finally:
        conn.close()


def inicializar_banco():
    """
    Cria as tabelas necessárias caso ainda não existam.
    """
    with conectar() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT NOT NULL,
                cnae_principal TEXT,
                caminho_certificado TEXT,
                senha_certificado TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tomadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                cnpj_cpf TEXT NOT NULL,
                nome_razao_social TEXT NOT NULL,
                email TEXT,
                endereco TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS notas_fiscais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                tomador_id INTEGER,
                numero_nota TEXT,
                protocolo TEXT,
                status TEXT NOT NULL,
                valor_servico TEXT NOT NULL,
                descricao TEXT NOT NULL,
                retorno TEXT,
                data_emissao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (empresa_id)
                    REFERENCES empresas(id),

                FOREIGN KEY (tomador_id)
                    REFERENCES tomadores(id)
            );
            """
        )


if __name__ == "__main__":
    inicializar_banco()
    print(f"Banco inicializado em: {DB_PATH}")
    