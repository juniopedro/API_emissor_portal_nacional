import re
from pathlib import Path

from database import conectar
from seguranca import criptografar


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def validar_cnpj(cnpj: str) -> bool:
    cnpj = somente_digitos(cnpj)

    if len(cnpj) != 14:
        return False

    if cnpj == cnpj[0] * 14:
        return False

    pesos_primeiro_digito = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_segundo_digito = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def calcular_digito(base: str, pesos: list[int]) -> str:
        total = sum(
            int(digito) * peso
            for digito, peso in zip(base, pesos)
        )

        resto = total % 11
        return "0" if resto < 2 else str(11 - resto)

    primeiro = calcular_digito(cnpj[:12], pesos_primeiro_digito)
    segundo = calcular_digito(cnpj[:12] + primeiro, pesos_segundo_digito)

    return cnpj[-2:] == primeiro + segundo


def cadastrar_empresa(
    cnpj: str,
    razao_social: str,
    cnae: str,
    caminho_certificado: str,
    senha_certificado: str,
) -> int:
    cnpj = somente_digitos(cnpj)
    razao_social = (razao_social or "").strip()
    cnae = (cnae or "").strip()
    caminho_certificado = (caminho_certificado or "").strip()

    if not validar_cnpj(cnpj):
        raise ValueError("CNPJ inválido.")

    if not razao_social:
        raise ValueError("A razão social é obrigatória.")

    if caminho_certificado:
        caminho = Path(caminho_certificado)

        if not caminho.exists():
            raise FileNotFoundError(
                f"Certificado não encontrado: {caminho}"
            )

        if caminho.suffix.lower() != ".pfx":
            raise ValueError(
                "O certificado deve possuir extensão .pfx."
            )

    senha_criptografada = criptografar(senha_certificado or "")

    with conectar() as conn:
        cursor = conn.execute(
            """
            INSERT INTO empresas (
                cnpj,
                razao_social,
                cnae_principal,
                caminho_certificado,
                senha_certificado
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                cnpj,
                razao_social,
                cnae,
                caminho_certificado,
                senha_criptografada,
            ),
        )

        return int(cursor.lastrowid)


def buscar_empresa_por_id(empresa_id: int):
    with conectar() as conn:
        return conn.execute(
            """
            SELECT *
            FROM empresas
            WHERE id = ?
            """,
            (empresa_id,),
        ).fetchone()


def buscar_empresa_por_cnpj(cnpj: str):
    cnpj = somente_digitos(cnpj)

    with conectar() as conn:
        return conn.execute(
            """
            SELECT *
            FROM empresas
            WHERE cnpj = ?
            """,
            (cnpj,),
        ).fetchone()


def listar_empresas():
    with conectar() as conn:
        return conn.execute(
            """
            SELECT
                id,
                cnpj,
                razao_social,
                cnae_principal,
                caminho_certificado,
                criado_em
            FROM empresas
            ORDER BY id
            """
        ).fetchall()


def cadastrar_tomador(
    empresa_id: int,
    cnpj_cpf: str,
    nome_razao_social: str,
    email: str = "",
    endereco: str = "",
) -> int:
    nome_razao_social = (nome_razao_social or "").strip()

    if not nome_razao_social:
        raise ValueError("O nome ou razão social do tomador é obrigatório.")

    empresa = buscar_empresa_por_id(empresa_id)

    if not empresa:
        raise ValueError("Empresa não encontrada.")

    with conectar() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tomadores (
                empresa_id,
                cnpj_cpf,
                nome_razao_social,
                email,
                endereco
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                somente_digitos(cnpj_cpf),
                nome_razao_social,
                (email or "").strip(),
                (endereco or "").strip(),
            ),
        )

        return int(cursor.lastrowid)


def buscar_tomador_por_id(tomador_id: int):
    with conectar() as conn:
        return conn.execute(
            """
            SELECT *
            FROM tomadores
            WHERE id = ?
            """,
            (tomador_id,),
        ).fetchone()


def listar_tomadores(empresa_id: int):
    with conectar() as conn:
        return conn.execute(
            """
            SELECT *
            FROM tomadores
            WHERE empresa_id = ?
            ORDER BY nome_razao_social
            """,
            (empresa_id,),
        ).fetchall()


def salvar_nota(
    empresa_id: int,
    tomador_id: int | None,
    valor_servico: str,
    descricao: str,
    status: str,
    retorno: str = "",
    numero_nota: str = "",
    protocolo: str = "",
) -> int:
    with conectar() as conn:
        cursor = conn.execute(
            """
            INSERT INTO notas_fiscais (
                empresa_id,
                tomador_id,
                numero_nota,
                protocolo,
                status,
                valor_servico,
                descricao,
                retorno
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                tomador_id,
                numero_nota,
                protocolo,
                status,
                str(valor_servico),
                descricao,
                retorno,
            ),
        )

        return int(cursor.lastrowid)