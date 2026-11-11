import os

from cryptography.fernet import Fernet, InvalidToken


NOME_VARIAVEL_CHAVE = "EMISSOR_NFSE_CHAVE"


def obter_fernet() -> Fernet:
    chave = os.environ.get(NOME_VARIAVEL_CHAVE)

    if not chave:
        raise RuntimeError(
            f"A variável de ambiente {NOME_VARIAVEL_CHAVE} não foi definida."
        )

    try:
        return Fernet(chave.encode("utf-8"))
    except Exception as erro:
        raise RuntimeError(
            "A chave EMISSOR_NFSE_CHAVE não é uma chave Fernet válida."
        ) from erro


def criptografar(texto: str) -> str:
    if texto is None:
        texto = ""

    return obter_fernet().encrypt(
        texto.encode("utf-8")
    ).decode("utf-8")


def descriptografar(token: str) -> str:
    if not token:
        return ""

    try:
        return obter_fernet().decrypt(
            token.encode("utf-8")
        ).decode("utf-8")
    except InvalidToken as erro:
        raise RuntimeError(
            "Não foi possível descriptografar a senha do certificado. "
            "Verifique se a chave EMISSOR_NFSE_CHAVE é a mesma usada no cadastro."
        ) from erro


def gerar_chave():
    """
    Gera uma nova chave Fernet.
    Execute diretamente este arquivo para gerar uma chave.
    """
    print(Fernet.generate_key().decode("utf-8"))


if __name__ == "__main__":
    gerar_chave()