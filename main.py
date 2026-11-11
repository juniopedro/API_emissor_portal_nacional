from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from crud import (
    buscar_empresa_por_cnpj,
    cadastrar_empresa,
    cadastrar_tomador,
    listar_empresas,
    listar_tomadores,
    salvar_nota,
)
from database import inicializar_banco
from nfe_service import transmitir_lote_nfs_e


inicializar_banco()

app = FastAPI(
    title="Emissor NFS-e Local",
    description="API local para gerenciamento de empresas, tomadores e transmissão.",
    version="1.0.0",
)


class EmpresaSchema(BaseModel):
    cnpj: str
    razao_social: str
    cnae_principal: str = ""
    caminho_certificado: str
    senha_certificado: str


class TomadorSchema(BaseModel):
    empresa_id: int
    cnpj_cpf: str = ""
    nome_razao_social: str
    email: str = ""
    endereco: str = ""


class NotaFiscalSchema(BaseModel):
    empresa_cnpj: str
    valor_servico: Decimal = Field(gt=0)
    descricao: str = Field(min_length=1)


@app.get("/")
def inicio():
    return {
        "status": "online",
        "mensagem": "API do emissor NFS-e em execução.",
    }


@app.post("/empresas/")
def api_cadastrar_empresa(empresa: EmpresaSchema):
    try:
        empresa_id = cadastrar_empresa(
            cnpj=empresa.cnpj,
            razao_social=empresa.razao_social,
            cnae=empresa.cnae_principal,
            caminho_certificado=empresa.caminho_certificado,
            senha_certificado=empresa.senha_certificado,
        )

        return {
            "status": "sucesso",
            "empresa_id": empresa_id,
            "mensagem": "Empresa cadastrada com sucesso.",
        }

    except FileNotFoundError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro

    except Exception as erro:
        if "UNIQUE constraint failed" in str(erro):
            raise HTTPException(
                status_code=400,
                detail="Já existe uma empresa com este CNPJ.",
            ) from erro

        raise HTTPException(
            status_code=500,
            detail="Erro interno ao cadastrar empresa.",
        ) from erro


@app.get("/empresas/")
def api_listar_empresas():
    empresas = listar_empresas()

    return [
        {
            "id": empresa["id"],
            "cnpj": empresa["cnpj"],
            "razao_social": empresa["razao_social"],
            "cnae_principal": empresa["cnae_principal"],
            "caminho_certificado": empresa["caminho_certificado"],
            "criado_em": empresa["criado_em"],
        }
        for empresa in empresas
    ]


@app.post("/tomadores/")
def api_cadastrar_tomador(tomador: TomadorSchema):
    try:
        tomador_id = cadastrar_tomador(
            empresa_id=tomador.empresa_id,
            cnpj_cpf=tomador.cnpj_cpf,
            nome_razao_social=tomador.nome_razao_social,
            email=tomador.email,
            endereco=tomador.endereco,
        )

        return {
            "status": "sucesso",
            "tomador_id": tomador_id,
            "mensagem": "Tomador cadastrado com sucesso.",
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro

    except Exception as erro:
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao cadastrar tomador.",
        ) from erro


@app.get("/empresas/{empresa_id}/tomadores/")
def api_listar_tomadores(empresa_id: int):
    tomadores = listar_tomadores(empresa_id)

    return [
        {
            "id": tomador["id"],
            "empresa_id": tomador["empresa_id"],
            "cnpj_cpf": tomador["cnpj_cpf"],
            "nome_razao_social": tomador["nome_razao_social"],
            "email": tomador["email"],
            "endereco": tomador["endereco"],
        }
        for tomador in tomadores
    ]


@app.post("/emitir-nfse/")
def api_emitir_nfse(nota: NotaFiscalSchema):
    empresa = buscar_empresa_por_cnpj(nota.empresa_cnpj)

    if not empresa:
        raise HTTPException(
            status_code=404,
            detail="Empresa não encontrada.",
        )

    valor = nota.valor_servico.quantize(Decimal("0.01"))

    resultado = transmitir_lote_nfs_e(
        empresa_id=empresa["id"],
        valor_servico=f"{valor:.2f}",
        discriminacao=nota.descricao,
    )

    retorno = resultado.get("retorno", "")
    sucesso = resultado.get("sucesso", False)

    status = "ENVIADA" if sucesso else "ERRO"

    nota_id = salvar_nota(
        empresa_id=empresa["id"],
        tomador_id=None,
        valor_servico=f"{valor:.2f}",
        descricao=nota.descricao,
        status=status,
        retorno=retorno or resultado.get("erro", ""),
    )

    if not sucesso:
        raise HTTPException(
            status_code=502,
            detail={
                "nota_id": nota_id,
                "erro": resultado.get("erro", "Falha na transmissão."),
            },
        )

    return {
        "status": "sucesso",
        "nota_id": nota_id,
        "retorno": retorno,
    }
    
    # uvicorn main:app --reload
    # http://127.0.0.1:8000/docs
    
    
    