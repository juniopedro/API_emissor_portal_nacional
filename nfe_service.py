# nfe_service.py
import os
import sqlite3
import tempfile

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

DB_NAME = "emissor_nfse.db"
from seguranca import descriptografar

# Endereço do serviço da NFS-e, definido na variável de ambiente NFSE_ENDPOINT.
# Ainda não temos o endereço oficial de homologação.
NFSE_ENDPOINT = os.environ.get("NFSE_ENDPOINT", "").strip()


def carregar_certificado_pfx(caminho_pfx: str, senha_pfx: str):
    """Extrai certificado e chave privada do .pfx para arquivos PEM temporários."""
    with open(caminho_pfx, "rb") as f:
        pfx_data = f.read()

    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        pfx_data, senha_pfx.encode("utf-8"), default_backend()
    )

    if private_key is None or certificate is None:
        raise ValueError("O arquivo .pfx não contém certificado e chave privada.")

    cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
    key_fd, key_path = tempfile.mkstemp(suffix=".pem")

    with os.fdopen(cert_fd, "wb") as cert_file:
        cert_file.write(certificate.public_bytes(serialization.Encoding.PEM))
        for cert in additional_certificates or []:
            cert_file.write(cert.public_bytes(serialization.Encoding.PEM))

    with os.fdopen(key_fd, "wb") as key_file:
        key_file.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    return cert_path, key_path


def montar_envelope(cnpj: str, rps_xml: str) -> str:
    # Provisório: o envelope oficial da NFS-e ainda será definido.
    return (
        '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">'
        "<env:Body>"
        f"<!-- Prestador: {cnpj} -->"
        f"{rps_xml}"
        "</env:Body>"
        "</env:Envelope>"
    )


def transmitir_lote_nfs_e(empresa_id: int, rps_xml: str) -> dict:
    """Transmite a NFS-e da empresa informada. Retorna dict com 'sucesso' e 'erro' ou 'retorno'."""
    conn = sqlite3.connect(DB_NAME)
    try:
        linha = conn.execute(
            "SELECT cnpj, caminho_certificado, senha_certificado FROM empresas WHERE id = ?",
            (empresa_id,),
        ).fetchone()
    finally:
        conn.close()

    if not linha:
        return {"sucesso": False, "erro": "Empresa não encontrada na base de dados."}

    cnpj, caminho_pfx, senha_criptografada = linha

    if not caminho_pfx or not os.path.exists(caminho_pfx):
        return {"sucesso": False, "erro": f"Certificado não encontrado: {caminho_pfx}"}

    cert_pem = key_pem = None
    try:
        senha = descriptografar(senha_criptografada)
        cert_pem, key_pem = carregar_certificado_pfx(caminho_pfx, senha)

        if not NFSE_ENDPOINT:
            return {
                "sucesso": False,
                "erro": (
                    "Certificado carregado com sucesso, mas NFSE_ENDPOINT não está "
                    "configurado. Nada foi transmitido."
                ),
            }

        envelope = montar_envelope(cnpj, rps_xml)
        headers = {"Content-Type": "text/xml; charset=utf-8"}

        resposta = requests.post(
            NFSE_ENDPOINT,
            data=envelope.encode("utf-8"),
            headers=headers,
            cert=(cert_pem, key_pem),
            timeout=30,
        )

        if resposta.status_code == 200:
            return {"sucesso": True, "retorno": resposta.text}
        return {
            "sucesso": False,
            "erro": f"Status HTTP {resposta.status_code}: {resposta.text}",
        }

    except Exception as e:
        return {"sucesso": False, "erro": str(e)}

    finally:
        for caminho in (cert_pem, key_pem):
            if caminho and os.path.exists(caminho):
                os.remove(caminho)
                