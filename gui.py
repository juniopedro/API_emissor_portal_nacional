# gui.py
import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

import flet as ft

from database import inicializar_banco

DB_NAME = "emissor_nfse.db"
from nfe_service import transmitir_lote_nfs_e
from seguranca import criptografar


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

@contextmanager
def conectar():
    """Abre a conexão, faz commit ou rollback e sempre fecha."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def empresa_existe(emp_id: int) -> bool:
    with conectar() as conn:
        return conn.execute(
            "SELECT 1 FROM empresas WHERE id = ?", (emp_id,)
        ).fetchone() is not None


def tomador_pertence_a_empresa(tomador_id: int, emp_id: int) -> bool:
    with conectar() as conn:
        return conn.execute(
            "SELECT 1 FROM tomadores WHERE id = ? AND empresa_id = ?",
            (tomador_id, emp_id),
        ).fetchone() is not None


# ---------------------------------------------------------------------------
# Validações e utilitários
# ---------------------------------------------------------------------------

def somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_cnpj(cnpj: str) -> bool:
    if len(cnpj) != 14 or not cnpj.isdigit() or cnpj == cnpj[0] * 14:
        return False

    def calcular_dv(base: str, pesos: list[int]) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    dv1 = calcular_dv(cnpj[:12], pesos1)
    dv2 = calcular_dv(cnpj[:12] + dv1, pesos2)
    return cnpj[-2:] == dv1 + dv2


def parse_valor(texto: str) -> Decimal:
    """Aceita '1500.00', '1500,00' e '1.500,00'. Lança ValueError se inválido."""
    limpo = (texto or "").strip().replace("R$", "").replace(" ", "")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except InvalidOperation:
        raise ValueError("valor não numérico")
    if not valor.is_finite() or valor <= 0:
        raise ValueError("valor deve ser maior que zero")
    return valor.quantize(Decimal("0.01"))


def montar_rps(valor: Decimal, descricao: str) -> str:
    # Provisório: será substituído pelo XML oficial da DPS.
    return (
        "<RPS>"
        f"<ValorServicos>{valor:.2f}</ValorServicos>"
        f"<Discriminacao>{escape(descricao)}</Discriminacao>"
        "</RPS>"
    )


def campo(label: str, **kwargs) -> ft.TextField:
    """Campo padronizado: sem preenchimento cinza e com borda visível."""
    return ft.TextField(
        label=label,
        width=480,
        filled=False,
        border=ft.OutlineInputBorder(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def main(page: ft.Page):
    inicializar_banco()

    page.title = "Emissor NFS-e - Painel Administrativo"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.WHITE
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_width = 560
    page.window_height = 900
    page.window_resizable = True
    page.padding = 10
    page.scroll = ft.ScrollMode.AUTO

    # --- Cadastro de empresa ---
    txt_cnpj = campo("CNPJ da Empresa", hint_text="Somente números")
    txt_razao = campo("Razão Social")
    txt_cnae = campo("CNAE Principal", hint_text="Ex: 6201-5/01")
    txt_cert = campo(
        "Caminho do Certificado (.pfx)",
        hint_text="O:/Api_Nfes/CERTIFICADOS/certificado_pedro.pfx",
    )
    txt_senha = campo("Senha do Certificado", password=True, can_reveal_password=True)

    # --- Cadastro de tomador ---
    txt_tom_empresa = campo("ID da Empresa Prestadora", hint_text="Ex: 1")
    txt_tom_doc = campo("CPF/CNPJ do Tomador", hint_text="Somente números")
    txt_tom_nome = campo("Nome / Razão Social do Tomador")
    txt_tom_email = campo("E-mail do Tomador")
    txt_tom_end = campo("Endereço do Tomador", multiline=True, min_lines=2)

    # --- Emissão de nota ---
    txt_id_empresa = campo("ID da Empresa (Cadastrada)", hint_text="Ex: 1")
    txt_id_tomador = campo("ID do Tomador", hint_text="Ex: 1")
    txt_valor = campo("Valor do Serviço (R$)", hint_text="Ex: 1500,00")
    txt_descricao = campo("Discriminação do Serviço", multiline=True, min_lines=2)

    txt_status = ft.Text(value="", weight=ft.FontWeight.BOLD)

    def mostrar_status(mensagem: str, cor: str):
        txt_status.value = mensagem
        txt_status.color = cor
        page.update()

    # --- Ações: empresa ---

    def salvar_empresa(e):
        cnpj = somente_digitos(txt_cnpj.value)
        razao = (txt_razao.value or "").strip()

        if not cnpj or not razao:
            mostrar_status("Preencha pelo menos o CNPJ e a Razão Social.", ft.Colors.RED)
            return

        if not validar_cnpj(cnpj):
            mostrar_status("CNPJ inválido. Verifique os dígitos.", ft.Colors.RED)
            return

        try:
            senha_criptografada = criptografar(txt_senha.value or "")
        except RuntimeError as ex:
            mostrar_status(str(ex), ft.Colors.RED)
            return

        try:
            with conectar() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO empresas
                        (cnpj, razao_social, cnae_principal, caminho_certificado, senha_certificado)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        cnpj,
                        razao,
                        (txt_cnae.value or "").strip(),
                        (txt_cert.value or "").strip(),
                        senha_criptografada,
                    ),
                )
                novo_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            mostrar_status("Já existe uma empresa com este CNPJ cadastrada.", ft.Colors.RED)
            return
        except Exception as ex:
            mostrar_status(f"Erro inesperado ao salvar: {ex}", ft.Colors.RED)
            return

        for c in (txt_cnpj, txt_razao, txt_cnae, txt_cert, txt_senha):
            c.value = ""
        mostrar_status(f"Empresa '{razao}' cadastrada com ID {novo_id}.", ft.Colors.GREEN)

    # --- Ações: tomador ---

    def salvar_tomador(e):
        texto_emp = (txt_tom_empresa.value or "").strip()
        if not texto_emp.isdigit():
            mostrar_status("O ID da empresa prestadora deve ser um número.", ft.Colors.RED)
            return
        emp_id = int(texto_emp)
        if not empresa_existe(emp_id):
            mostrar_status(f"Nenhuma empresa cadastrada com ID {emp_id}.", ft.Colors.RED)
            return

        doc = somente_digitos(txt_tom_doc.value)
        if len(doc) not in (11, 14):
            mostrar_status("CPF deve ter 11 dígitos e CNPJ 14.", ft.Colors.RED)
            return

        nome = (txt_tom_nome.value or "").strip()
        if not nome:
            mostrar_status("Informe o nome ou razão social do tomador.", ft.Colors.RED)
            return

        with conectar() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tomadores
                    (empresa_id, cnpj_cpf, nome_razao_social, email, endereco)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    emp_id,
                    doc,
                    nome,
                    (txt_tom_email.value or "").strip(),
                    (txt_tom_end.value or "").strip(),
                ),
            )
            novo_id = cursor.lastrowid

        for c in (txt_tom_doc, txt_tom_nome, txt_tom_email, txt_tom_end):
            c.value = ""
        mostrar_status(f"Tomador '{nome}' cadastrado com ID {novo_id}.", ft.Colors.GREEN)

    # --- Ações: emissão ---

    def acao_emitir_nota(e):
        texto_id = (txt_id_empresa.value or "").strip()
        if not texto_id.isdigit():
            mostrar_status("O ID da empresa deve ser um número inteiro.", ft.Colors.RED)
            return
        emp_id = int(texto_id)

        texto_tom = (txt_id_tomador.value or "").strip()
        if not texto_tom.isdigit():
            mostrar_status("Informe o ID do tomador.", ft.Colors.RED)
            return
        tomador_id = int(texto_tom)

        try:
            valor = parse_valor(txt_valor.value)
        except ValueError as ex:
            mostrar_status(f"Valor inválido: {ex}. Use o formato 1500,00.", ft.Colors.RED)
            return

        descricao = (txt_descricao.value or "").strip()
        if not descricao:
            mostrar_status("Informe a discriminação do serviço.", ft.Colors.RED)
            return

        if not empresa_existe(emp_id):
            mostrar_status(f"Nenhuma empresa cadastrada com ID {emp_id}.", ft.Colors.RED)
            return

        if not tomador_pertence_a_empresa(tomador_id, emp_id):
            mostrar_status("Este tomador não está cadastrado para essa empresa.", ft.Colors.RED)
            return

        mostrar_status("Transmitindo...", ft.Colors.BLUE)
        try:
            resultado = transmitir_lote_nfs_e(emp_id, montar_rps(valor, descricao))
        except Exception as ex:
            mostrar_status(f"Erro na transmissão: {ex}", ft.Colors.RED)
            return

        if resultado.get("sucesso"):
            mostrar_status("Nota transmitida com sucesso para o Portal Nacional.", ft.Colors.GREEN)
        else:
            erro = resultado.get("erro", "Erro desconhecido")
            mostrar_status(f"Falha na emissão: {erro}", ft.Colors.RED)

    # --- Botões ---

    btn_salvar = ft.Button(
        content=ft.Text("Cadastrar Empresa"),
        icon=ft.Icons.SAVE,
        on_click=salvar_empresa,
        width=480,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
    )

    btn_tomador = ft.Button(
        content=ft.Text("Cadastrar Tomador"),
        icon=ft.Icons.PERSON_ADD,
        on_click=salvar_tomador,
        width=480,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
    )

    btn_emitir = ft.Button(
        content=ft.Text("Transmitir NFS-e (Portal Nacional)"),
        icon=ft.Icons.SEND,
        on_click=acao_emitir_nota,
        width=480,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE),
    )

    # --- Layout ---

    conteudo_principal = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.BUSINESS, size=24, color=ft.Colors.BLUE),
                    ft.Text("Painel Emissor NFS-e v2.0", size=18, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Divider(height=10),
            ft.Text("1. Cadastro de Empresa", weight=ft.FontWeight.BOLD, size=14),
            txt_cnpj,
            txt_razao,
            txt_cnae,
            txt_cert,
            txt_senha,
            btn_salvar,
            ft.Divider(height=15),
            ft.Text("2. Cadastro de Tomador", weight=ft.FontWeight.BOLD, size=14),
            txt_tom_empresa,
            txt_tom_doc,
            txt_tom_nome,
            txt_tom_email,
            txt_tom_end,
            btn_tomador,
            ft.Divider(height=15),
            ft.Text("3. Emissão de Nota Fiscal", weight=ft.FontWeight.BOLD, size=14),
            txt_id_empresa,
            txt_id_tomador,
            txt_valor,
            txt_descricao,
            btn_emitir,
            ft.Divider(height=10),
            txt_status,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8,
    )

    page.add(conteudo_principal)


if __name__ == "__main__":
    ft.run(main)
    