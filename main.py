from datetime import datetime, timedelta
import os
import uuid
import time
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sisgersa")

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from database.connection import db
from config import settings
from database.connectivity import init_connectivity_checker, is_online, force_check
from database.cache import download_to_cache, get_cache_status, start_background_cache, stop_background_cache, cache_query_one, cache_query_all
from database.backup import dump_database, start_background_backup, stop_background_backup, get_last_backup, get_backup_count, cleanup_old_backups
from database.estado import (
    rate_limit_excedido,
    registrar_tentativa,
    incrementar_contador,
    criar_pending_login,
    consumir_pending_login,
)
from utils.auth import (
    usuario_por_email,
    usuarios_por_email,
    usuarios_por_cpf,
    usuario_por_cpf,
    _is_cpf,
    _normalizar_cpf,
    verificar_senha,
    hash_senha,
    criar_token,
    verificar_token,
    criar_sessao,
    sessao_ativa,
    revogar_sessao,
    revogar_sessoes_usuario,
    obter_estabelecimentos_usuario,
    criar_usuario,
    vincular_paciente,
)
from utils.permissoes import (
    MODULOS, DEFAULT_PERMISSIONS,
    pode_acessar, obter_permissoes_usuario, obter_permissoes_para_nav,
    salvar_permissoes, limpar_permissoes, exigir_permissao,
)
from utils.planos import verificar_limite, LimiteAtingidoError, obter_plano_estabelecimento, contar_uso, bloquear_se_limite, _mes_atual_filter
from utils.email import enviar_email, montar_confirmacao_agendamento
from utils.scheduler import iniciar_scheduler, parar_scheduler
from utils.farmaco import checar_medicamento_paciente, sugestoes_para_sintoma, principios_curados, resolver_principios_medicamento, alertas_paciente, listar_sintomas, sugestoes_seguras

@asynccontextmanager
async def lifespan(app):
    logger.info(f"Startup: ENVIRONMENT={settings.ENVIRONMENT}, DB_ENGINE={settings.DB_ENGINE}")
    try:
        db.get_connection()
        logger.info("Startup: conexao DB OK")
    except Exception as e:
        logger.error(f"Startup: falha na conexao DB: {e}")

    if settings.DB_ENGINE == "postgresql":
        try:
            from init_db import criar_banco, criar_admin_padrao, seed_planos, seed_cupons, criar_tabela_sessoes
            criar_banco()
            criar_admin_padrao()
            seed_planos()
            seed_cupons()
            logger.info("Startup: banco inicializado com sucesso")
        except Exception as e:
            logger.error(f"Startup: erro ao inicializar banco: {e}", exc_info=True)
    else:
        try:
            from init_db import seed_planos, seed_cupons, criar_tabela_sessoes
            seed_planos()
            seed_cupons()
        except Exception as e:
            logger.error(f"Startup: erro ao semear dados: {e}")

    try:
        criar_tabela_sessoes()
    except Exception as e:
        logger.error(f"Startup: erro ao garantir tabela de sessoes: {e}")

    try:
        from init_db import criar_tabelas_estado
        criar_tabelas_estado()
    except Exception as e:
        logger.error(f"Startup: erro ao garantir tabelas de estado: {e}")

    if settings.DB_ENGINE == "postgresql":
        try:
            from urllib.parse import urlparse
            parsed = urlparse(settings.DATABASE_URL)
            host = parsed.hostname or settings.DB_HOST
            port = parsed.port or 5432
            init_connectivity_checker(host, port)
            logger.info(f"Startup: Connectivity checker ON, Render={host}:{port}")
        except Exception as e:
            logger.error(f"Startup: erro connectivity: {e}")

        try:
            from database.cache import init_cache, download_to_cache
            init_cache()
            initial = force_check()
            if initial:
                logger.info("Startup: online, baixando cache...")
                download_to_cache()
            else:
                logger.warning("Startup: offline, usando cache SQLite existente")
        except Exception as e:
            logger.error(f"Startup: erro cache inicial: {e}")

        start_background_cache(interval=3600)

    try:
        dump_file = dump_database()
        if dump_file:
            cleanup_old_backups()
            logger.info(f"Startup: backup local criado")
        else:
            logger.warning("Startup: backup nao criado")
    except Exception as e:
        logger.error(f"Startup: erro backup: {e}")

    start_background_backup(interval=21600)
    iniciar_scheduler()

    yield

    parar_scheduler()
    stop_background_cache()
    stop_background_backup()
    db.close()


app = FastAPI(title="SISGERSA", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _proximo_numero_prontuario(estabelecimento_id: int) -> str:
    linhas = db.fetch_all(
        "SELECT numero_prontuario FROM prontuarios WHERE estabelecimento_id = %s",
        (estabelecimento_id,),
    )
    maior = 0
    for r in linhas or []:
        valor = str(r.get("numero_prontuario") or "")
        for token in valor.split("-"):
            if token.isdigit():
                maior = max(maior, int(token))
    return f"PRONT-{maior + 1:05d}"


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["MODULOS_INFO"] = MODULOS
templates.env.globals["pode_acessar"] = pode_acessar

def format_cpf(value):
    if not value:
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return str(value)
templates.env.filters["format_cpf"] = format_cpf

def format_phone(value):
    if not value:
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return str(value)
templates.env.filters["format_phone"] = format_phone


def from_json(value):
    import json
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) if isinstance(value, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
templates.env.filters["from_json"] = from_json


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 302 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data:"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)


RATE_LIMIT_WINDOW = 300
RATE_LIMIT_MAX = 10

def is_rate_limited(ip: str) -> bool:
    return rate_limit_excedido(f"login:{ip}", RATE_LIMIT_WINDOW, RATE_LIMIT_MAX)

def record_login_attempt(ip: str):
    registrar_tentativa(f"login:{ip}", RATE_LIMIT_WINDOW)

WRITE_RATE_WINDOW = 60
WRITE_RATE_LIMIT_CREATE = 50
WRITE_RATE_LIMIT_DELETE = 15

def is_write_limited(request: Request, usuario: dict, action: str = "create") -> bool:
    key = f"write:{usuario['id']}:{action}"
    limit = WRITE_RATE_LIMIT_DELETE if action == "delete" else WRITE_RATE_LIMIT_CREATE
    return incrementar_contador(key, WRITE_RATE_WINDOW) > limit


def obter_usuario_atual(request: Request):
    token = request.cookies.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
        return None
    if not sessao_ativa(payload.get("sub"), payload.get("jti")):
        return None
    usuario = db.fetch_one("SELECT * FROM usuarios WHERE id = %s AND ativo = TRUE", (payload["sub"],))
    return usuario


def exigir_login(request: Request):
    usuario = obter_usuario_atual(request)
    if not usuario:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return usuario


def resolver_estabelecimento(request: Request, usuario: dict, estab_id_form: str = None) -> str:
    estab_id = request.cookies.get("estabelecimento_id")
    if not estab_id and estab_id_form:
        estab_id = estab_id_form
    if estab_id:
        ativo = db.fetch_one("SELECT id FROM estabelecimentos WHERE id = %s AND ativo = TRUE", (estab_id,))
        if not ativo:
            estab_id = None
    if not estab_id and usuario["tipo"] == "admin" and not usuario.get("is_super"):
        todos = db.fetch_all("SELECT id FROM estabelecimentos WHERE ativo = TRUE")
        if len(todos) == 1:
            estab_id = str(todos[0]["id"])
    return estab_id


def verificar_acesso_registro(request: Request, usuario: dict, registro: dict):
    if usuario.get("is_super"):
        return
    estab_id_check = request.cookies.get("estabelecimento_id")
    if usuario["tipo"] == "admin":
        if estab_id_check and str(registro.get("estabelecimento_id")) != str(estab_id_check):
            raise HTTPException(status_code=403)
    elif usuario["tipo"] == "profissional":
        if estab_id_check and str(registro.get("estabelecimento_id")) != str(estab_id_check):
            raise HTTPException(status_code=403)
        paciente_id = registro.get("paciente_usuario_id")
        if paciente_id:
            consulta = db.fetch_one(
                """SELECT 1 FROM consultas
                   WHERE profissional_usuario_id = %s AND paciente_usuario_id = %s
                   LIMIT 1""",
                (usuario["id"], paciente_id),
            )
            if not consulta:
                raise HTTPException(status_code=403)
    elif usuario["tipo"] == "paciente":
        if registro.get("paciente_usuario_id") and registro["paciente_usuario_id"] != usuario["id"]:
            raise HTTPException(status_code=403)


def obter_pacientes_para_filtro(usuario, estab_id=None):
    if usuario["tipo"] == "paciente":
        return [{"id": usuario["id"], "nome": usuario["nome"]}]
    if usuario.get("is_super"):
        if estab_id:
            return db.fetch_all(
                """SELECT u.id, u.nome FROM usuarios u
                   JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
                   WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
                (estab_id,),
            )
        return db.fetch_all(
            "SELECT id, nome FROM usuarios WHERE tipo = 'paciente' AND ativo = TRUE ORDER BY nome"
        )
    if usuario["tipo"] == "profissional":
        if estab_id:
            return db.fetch_all(
                """SELECT DISTINCT u.id, u.nome FROM usuarios u
                   JOIN consultas c ON c.paciente_usuario_id = u.id
                   WHERE c.profissional_usuario_id = %s AND c.estabelecimento_id = %s AND u.ativo = TRUE
                   ORDER BY u.nome""",
                (usuario["id"], estab_id),
            )
        return []
    if estab_id:
        return db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario["tipo"] == "admin":
        return db.fetch_all(
            "SELECT id, nome FROM usuarios WHERE tipo = 'paciente' AND ativo = TRUE ORDER BY nome"
        )
    return []


@app.get("/health")
def health_check():
    try:
        row = db.fetch_one("SELECT 1 AS ok")
        db_ok = row is not None
    except Exception:
        db_ok = False
    return JSONResponse({
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    usuario = obter_usuario_atual(request)
    if usuario:
        return RedirectResponse("/dashboard", status_code=302)
    planos = db.fetch_all("SELECT * FROM planos WHERE ativo = TRUE AND slug != 'cortesia' ORDER BY valor_mensal ASC")
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "planos": planos},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, motivo: str = None):
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "erro": None, "motivo": motivo},
    )


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), senha: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"

    if is_rate_limited(client_ip):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Muitas tentativas. Aguarde 5 minutos."},
        )

    if _is_cpf(email):
        todos_usuarios = usuarios_por_cpf(_normalizar_cpf(email))
    else:
        todos_usuarios = usuarios_por_email(email)
    if not todos_usuarios:
        record_login_attempt(client_ip)
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Email ou senha invalidos"},
        )

    usuarios_validos = [u for u in todos_usuarios if verificar_senha(senha, u["senha_hash"])]

    if not usuarios_validos:
        record_login_attempt(client_ip)
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Email ou senha invalidos"},
        )

    if len(usuarios_validos) == 1:
        return _login_usuario(request, usuarios_validos[0])

    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    import hashlib
    session_key = hashlib.sha256(f"{email}:{time.time()}:{client_ip}".encode()).hexdigest()[:32]

    criar_pending_login(session_key, [u["id"] for u in usuarios_validos])

    usuarios_info = []
    for u in usuarios_validos:
        estabs = []
        if u["tipo"] in ("profissional", "recepcionista"):
            estabs = obter_estabelecimentos_usuario(u["id"])
        usuarios_info.append({
            "id": u["id"],
            "nome": u["nome"],
            "tipo": u["tipo"],
            "estabelecimentos": estabs,
        })

    return templates.TemplateResponse(
        "auth/selecionar_conta.html",
        {"request": request, "usuarios": usuarios_info, "session_key": session_key},
    )


@app.get("/minha-conta/alterar-senha")
def alterar_senha_page(request: Request, usuario: dict = Depends(exigir_login)):
    return templates.TemplateResponse(
        "auth/alterar_senha.html",
        {"request": request, "usuario": usuario, "erro": None, "sucesso": None},
    )


@app.post("/minha-conta/alterar-senha")
def alterar_senha_submit(
    request: Request,
    usuario: dict = Depends(exigir_login),
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    nova_senha2: str = Form(...),
):
    if not verificar_senha(senha_atual, usuario["senha_hash"]):
        return templates.TemplateResponse(
            "auth/alterar_senha.html",
            {"request": request, "usuario": usuario, "erro": "Senha atual incorreta.", "sucesso": None},
        )
    if len(nova_senha) < 6:
        return templates.TemplateResponse(
            "auth/alterar_senha.html",
            {"request": request, "usuario": usuario, "erro": "A nova senha deve ter pelo menos 6 caracteres.", "sucesso": None},
        )
    if nova_senha != nova_senha2:
        return templates.TemplateResponse(
            "auth/alterar_senha.html",
            {"request": request, "usuario": usuario, "erro": "A confirmação da nova senha não confere.", "sucesso": None},
        )
    db.execute(
        "UPDATE usuarios SET senha_hash = %s WHERE id = %s",
        (hash_senha(nova_senha), usuario["id"]),
    )
    revogar_sessoes_usuario(usuario["id"])
    response = RedirectResponse("/login?motivo=senha-alterada", status_code=302)
    response.delete_cookie("token")
    response.delete_cookie("estabelecimento_id")
    response.delete_cookie("impersonate_token")
    response.delete_cookie("impersonate_estab")
    return response


def _login_usuario(request: Request, usuario: dict):
    jti = uuid.uuid4().hex
    token = criar_token(usuario["id"], usuario["tipo"], bool(usuario.get("is_super", False)), jti)
    criar_sessao(usuario["id"], jti)

    estabelecimentos = []
    if usuario["tipo"] in ("admin", "profissional", "recepcionista"):
        estabelecimentos = obter_estabelecimentos_usuario(usuario["id"])

    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard?welcome=1", status_code=302)
    response.set_cookie("token", token, **cookie_kwargs)

    if len(estabelecimentos) == 1:
        response.set_cookie("estabelecimento_id", str(estabelecimentos[0]["id"]), **cookie_kwargs)

    return response


@app.post("/login/selecionar")
def login_selecionar(request: Request, session_key: str = Form(...), usuario_id: int = Form(...)):
    client_ip = request.client.host if request.client else "unknown"

    if is_rate_limited(client_ip):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Muitas tentativas. Aguarde 5 minutos."},
        )

    allowed_ids = consumir_pending_login(session_key)
    if not allowed_ids or usuario_id not in allowed_ids:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Sessao expirada. Faca login novamente."},
        )

    usuario = db.fetch_one("SELECT * FROM usuarios WHERE id = %s AND ativo = TRUE", (usuario_id,))
    if not usuario:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Usuario nao encontrado."},
        )

    return _login_usuario(request, usuario)


@app.get("/registrar", response_class=HTMLResponse)
def registrar_page(request: Request, plano: str = Query("gratis")):
    usuario = obter_usuario_atual(request)
    if usuario:
        return RedirectResponse("/dashboard", status_code=302)
    from database.connection import db
    planos_validos = {"gratis", "basico", "profissional", "enterprise"}
    if plano not in planos_validos:
        plano = "gratis"
    plano_info = db.fetch_one("SELECT id, nome, slug, valor_mensal FROM planos WHERE slug = %s AND ativo = TRUE", (plano,))
    if not plano_info:
        plano_info = db.fetch_one("SELECT id, nome, slug, valor_mensal FROM planos WHERE slug = 'gratis' AND ativo = TRUE")
    return templates.TemplateResponse("auth/registrar.html", {"request": request, "plano_info": plano_info})


@app.get("/api/cupom/validar")
def api_validar_cupom(codigo: str):
    try:
        cupom = db.fetch_one(
            "SELECT * FROM cupons WHERE codigo = %s AND ativo = TRUE",
            (codigo.upper(),),
        )
    except Exception:
        return {"valido": False, "mensagem": "Sistema de cupons indisponível"}

    if not cupom:
        return {"valido": False, "mensagem": "Cupom não encontrado ou inativo"}

    if cupom["max_usos"] is not None and cupom["max_usos"] > 0 and cupom["usos_atual"] >= cupom["max_usos"]:
        return {"valido": False, "mensagem": "Cupom atingiu o limite de uso"}

    desconto = cupom["desconto_percentual"]
    plano = cupom["plano_destino"]
    if desconto == 100:
        msg = f"Cupom válido! Acesso gratuito ao plano {plano} por {cupom['validade_dias']} dias"
    else:
        msg = f"Cupom válido! {desconto}% de desconto no plano {plano}"
    return {"valido": True, "mensagem": msg, "desconto": desconto, "plano": plano}


@app.post("/registrar")
def registrar_submit(
    request: Request,
    nome_estabelecimento: str = Form(...),
    tipo: str = Form("clinica"),
    cnpj: str = Form(None),
    telefone: str = Form(None),
    email_estab: str = Form(None),
    endereco: str = Form(None),
    nome_admin: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    senha2: str = Form(...),
    cupom: str = Form(None),
    plano_slug: str = Form("gratis"),
):
    from database.connection import db
    cupom_id = None
    planos_validos = {"gratis", "basico", "profissional", "enterprise"}
    if plano_slug not in planos_validos:
        plano_slug = "gratis"
    data_expiracao_trial = None
    validade_dias = 30

    def _plano_info():
        return db.fetch_one("SELECT id, nome, slug, valor_mensal FROM planos WHERE slug = %s", (plano_slug,))

    if senha != senha2:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "As senhas não coincidem",
            "plano_info": _plano_info(),
        })

    if len(senha) < 6:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "A senha deve ter no mínimo 6 caracteres",
            "plano_info": _plano_info(),
        })

    existente = db.fetch_one("SELECT id FROM usuarios WHERE email = %s", (email,))
    if existente:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "Já existe uma conta com este email",
            "plano_info": _plano_info(),
        })
    if cupom and cupom.strip():
        cupom_row = db.fetch_one(
            "SELECT * FROM cupons WHERE codigo = %s AND ativo = TRUE",
            (cupom.strip().upper(),),
        )
        if cupom_row:
            if cupom_row["max_usos"] is not None and cupom_row["max_usos"] > 0 and cupom_row["usos_atual"] >= cupom_row["max_usos"]:
                return templates.TemplateResponse("auth/registrar.html", {
                    "request": request, "erro": "Cupom atingiu o limite de uso",
                    "plano_info": _plano_info(),
                })
            cupom_id = cupom_row["id"]
            plano_slug = cupom_row["plano_destino"]
            if cupom_row["desconto_percentual"] >= 100:
                validade_dias = cupom_row.get("validade_dias") or 30
                from datetime import timedelta
                data_expiracao_trial = (datetime.now() + timedelta(days=validade_dias)).strftime("%Y-%m-%d")
        else:
            return templates.TemplateResponse("auth/registrar.html", {
                "request": request, "erro": "Cupom inválido",
                "plano_info": db.fetch_one("SELECT id, nome, slug, valor_mensal FROM planos WHERE slug = %s", (plano_slug,)),
            })

    plano_row = db.fetch_one("SELECT id FROM planos WHERE slug = %s", (plano_slug,))
    plano_id = plano_row["id"] if plano_row else None

    try:
        if settings.DB_ENGINE == "postgresql":
            cursor = db.execute(
                """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, plano_id, cupom_id, plano_expira_em)
                   VALUES (%s, %s, NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), %s, %s, %s)
                   RETURNING id""",
                (nome_estabelecimento, tipo, cnpj or "", telefone or "", email_estab or "", endereco or "", plano_id, cupom_id, data_expiracao_trial),
            )
            row = cursor.fetchone()
            estab_id = row["id"] if row else None
        else:
            cursor = db.execute(
                """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, plano_id, cupom_id, plano_expira_em)
                   VALUES (%s, %s, NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), %s, %s, %s)""",
                (nome_estabelecimento, tipo, cnpj or "", telefone or "", email_estab or "", endereco or "", plano_id, cupom_id, data_expiracao_trial),
            )
            estab_id = cursor.lastrowid

        if cupom_id:
            db.execute("UPDATE cupons SET usos_atual = usos_atual + 1 WHERE id = %s", (cupom_id,))
    except Exception as e:
        logger.error(f"registrar: erro ao criar estabelecimento: {e}")
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": f"Erro ao criar estabelecimento: {e}",
            "plano_info": _plano_info(),
        })

    try:
        from utils.auth import criar_usuario, vincular_profissional
        admin_id = criar_usuario(
            nome=nome_admin,
            email=email,
            senha=senha,
            tipo="admin",
            telefone=telefone or None,
            is_super=False,
        )
        vincular_profissional(admin_id, estab_id, cargo="Administrador")
    except Exception as e:
        logger.error(f"registrar: erro ao criar admin: {e}")
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": f"Erro ao criar usuário: {e}",
            "plano_info": _plano_info(),
        })

    jti = uuid.uuid4().hex
    token = criar_token(admin_id, "admin", False, jti)
    criar_sessao(admin_id, jti)

    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard?welcome=1", status_code=302)
    response.set_cookie("token", token, **cookie_kwargs)
    response.set_cookie("estabelecimento_id", str(estab_id), **cookie_kwargs)

    logger.info(f"registrar: nova clínica '{nome_estabelecimento}' (ID={estab_id}), admin={email}")
    return response


@app.get("/logout")
def logout(request: Request, motivo: str = None):
    token = request.cookies.get("token")
    payload = verificar_token(token) if token else None
    if payload:
        revogar_sessao(payload.get("jti"))
    destino = "/login"
    if motivo:
        destino += f"?motivo={motivo}"
    response = RedirectResponse(destino, status_code=302)
    response.delete_cookie("token")
    response.delete_cookie("estabelecimento_id")
    response.delete_cookie("impersonate_token")
    response.delete_cookie("impersonate_estab")
    return response


@app.get("/api/heartbeat")
def api_heartbeat(request: Request):
    if not obter_usuario_atual(request):
        return JSONResponse(status_code=401, content={"ok": False})
    return {"ok": True, "ts": time.time()}


@app.get("/admin/impersonate/{user_id}")
def impersonate_user(
    request: Request,
    user_id: int,
    usuario=Depends(exigir_login),
):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    target = db.fetch_one("SELECT * FROM usuarios WHERE id = %s AND ativo = TRUE", (user_id,))
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    estab_id_form = request.query_params.get("estab_id")
    estab_id_cookie = request.cookies.get("estabelecimento_id")
    estab_id = estab_id_form or estab_id_cookie

    if not estab_id:
        if target["tipo"] == "paciente":
            pe = db.fetch_one(
                "SELECT estabelecimento_id FROM paciente_estabelecimento WHERE usuario_id = %s LIMIT 1",
                (user_id,),
            )
        else:
            pe = db.fetch_one(
                "SELECT estabelecimento_id FROM profissional_estabelecimento WHERE usuario_id = %s LIMIT 1",
                (user_id,),
            )
        if pe:
            estab_id = str(pe["estabelecimento_id"])

    jti = uuid.uuid4().hex
    token = criar_token(target["id"], target["tipo"], target.get("is_super", False), jti)
    criar_sessao(target["id"], jti)

    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard?impersonate=1", status_code=302)
    original_token = request.cookies.get("token")
    response.set_cookie("impersonate_token", original_token, **cookie_kwargs)
    if estab_id_cookie:
        response.set_cookie("impersonate_estab", estab_id_cookie, **cookie_kwargs)
    response.set_cookie("token", token, **cookie_kwargs)
    if estab_id:
        response.set_cookie("estabelecimento_id", estab_id, **cookie_kwargs)

    logger.info(f"impersonate: super admin {usuario['id']} impersonating user {user_id} ({target['tipo']})")
    return response


@app.get("/admin/stop-impersonate")
def stop_impersonate(request: Request):
    original_token = request.cookies.get("impersonate_token")
    original_estab = request.cookies.get("impersonate_estab")

    if not original_token:
        return RedirectResponse("/login", status_code=302)

    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("token", original_token, **cookie_kwargs)
    response.delete_cookie("impersonate_token")
    response.delete_cookie("impersonate_estab")
    if original_estab:
        response.set_cookie("estabelecimento_id", original_estab, **cookie_kwargs)
    else:
        response.delete_cookie("estabelecimento_id")
    return response


@app.get("/admin/testar-email")
def testar_email(request: Request, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    if not usuario.get("email"):
        return JSONResponse({"erro": "Admin sem email cadastrado"}, status_code=400)

    corpo = montar_confirmacao_agendamento(
        paciente_nome=usuario["nome"],
        profissional_nome="Dr. Teste",
        data_formatada="01/01/2099",
        hora_formatada="10:00",
        duracao=30,
        procedimento="Consulta de Teste",
        estabelecimento_nome="SISGERSA - Teste",
        estabelecimento_endereco="Rua de Teste, 123",
    )

    enviado = enviar_email(
        destinatario=usuario["email"],
        assunto="[SISGERSA] Teste de envio de email",
        corpo_html=corpo,
    )

    if enviado:
        return JSONResponse({"ok": True, "mensagem": f"Email de teste enviado para {usuario['email']}"})
    else:
        return JSONResponse({"ok": False, "mensagem": "Falha ao enviar. Verifique as configuracoes SMTP."}, status_code=500)


@app.get("/api/email-status")
def api_email_status(request: Request, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    try:
        row = db.fetch_one("SELECT valor FROM config_sistema WHERE chave = 'email_habilitado'")
        ativo = row["valor"] == "true" if row else True
    except Exception:
        ativo = True
    return JSONResponse({"habilitado": ativo})


@app.post("/admin/toggle-email")
def toggle_email(request: Request, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    try:
        row = db.fetch_one("SELECT valor FROM config_sistema WHERE chave = 'email_habilitado'")
        atual = row["valor"] if row else "true"
        novo = "false" if atual == "true" else "true"
        if row:
            db.execute("UPDATE config_sistema SET valor = %s WHERE chave = 'email_habilitado'", (novo,))
        else:
            db.execute("INSERT INTO config_sistema (chave, valor) VALUES ('email_habilitado', %s)", (novo,))
        return JSONResponse({"ok": True, "habilitado": novo == "true"})
    except Exception as e:
        logger.error(f"Erro ao toggle email: {e}")
        return JSONResponse({"ok": False, "mensagem": str(e)}, status_code=500)


@app.post("/estabelecimento/selecionar")
def selecionar_estabelecimento(
    request: Request,
    estabelecimento_id: str = Form(""),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    redirect = request.headers.get("referer", "/dashboard")
    cookie_kwargs = dict(httponly=True, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse(redirect, status_code=302)
    if estabelecimento_id:
        response.set_cookie("estabelecimento_id", estabelecimento_id, **cookie_kwargs)
    else:
        response.delete_cookie("estabelecimento_id")
    return response


@app.get("/admin/cupons", response_class=HTMLResponse)
def listar_cupons(request: Request, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    try:
        cupons = db.fetch_all("SELECT * FROM cupons ORDER BY criado_em DESC")
    except Exception:
        cupons = []
    return templates.TemplateResponse(
        "admin/cupons.html",
        {"request": request, "usuario": usuario, "cupons": cupons},
    )


@app.post("/admin/cupons/criar")
def criar_cupom(
    request: Request,
    codigo: str = Form(...),
    descricao: str = Form(None),
    desconto_percentual: int = Form(0),
    plano_destino: str = Form("basico"),
    validade_dias: int = Form(30),
    max_usos: int = Form(0),
    usuario=Depends(exigir_login),
):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    try:
        db.execute(
            """INSERT INTO cupons (codigo, descricao, desconto_percentual, plano_destino, validade_dias, max_usos)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (codigo.upper().strip(), descricao, desconto_percentual, plano_destino, validade_dias, max_usos),
        )
    except Exception:
        return RedirectResponse("/admin/cupons?erro=codigo_duplicado", status_code=302)

    return RedirectResponse("/admin/cupons", status_code=302)


@app.post("/admin/cupons/{cupom_id}/toggle")
def toggle_cupom(cupom_id: int, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    cupom = db.fetch_one("SELECT id, ativo FROM cupons WHERE id = %s", (cupom_id,))
    if not cupom:
        raise HTTPException(status_code=404)
    novo = not cupom["ativo"]
    db.execute("UPDATE cupons SET ativo = %s WHERE id = %s", (novo, cupom_id))
    return RedirectResponse("/admin/cupons", status_code=302)


@app.get("/admin/permissoes", response_class=HTMLResponse)
def paginar_permissoes(
    request: Request,
    estabelecimento_id: str = Query(None),
    usuario_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = estabelecimento_id or request.cookies.get("estabelecimento_id")
    estabelecimentos = []
    if usuario.get("is_super"):
        estabelecimentos = db.fetch_all("SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome")
    elif estab_id:
        estabelecimentos = db.fetch_all(
            "SELECT id, nome FROM estabelecimentos WHERE id = %s AND ativo = TRUE", (estab_id,)
        )
        estab_id = str(estab_id)

    usuarioSelecionado = None
    overrides = {}
    defaults = {}
    if estab_id and usuario_id:
        usuarioSelecionado = db.fetch_one(
            "SELECT id, nome, tipo FROM usuarios WHERE id = %s", (usuario_id,)
        )
        if usuarioSelecionado:
            overrides = obter_permissoes_usuario(int(usuario_id), int(estab_id))
            defaults = DEFAULT_PERMISSIONS.get(usuarioSelecionado["tipo"], {})

    return templates.TemplateResponse("admin/permissoes.html", {
        "request": request,
        "usuario": usuario,
        "estabelecimentos": estabelecimentos,
        "estabSelecionado": estab_id or "",
        "usuarioSelecionado": usuarioSelecionado,
        "overrides": overrides,
        "defaults": defaults,
        "modulos": MODULOS,
    })


@app.post("/admin/permissoes/salvar")
def salvar_permissoes_rota(
    request: Request,
    usuario_id: int = Form(...),
    estabelecimento_id: int = Form(...),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    if not usuario.get("is_super"):
        cookie_estab = request.cookies.get("estabelecimento_id")
        if cookie_estab and str(estabelecimento_id) != str(cookie_estab):
            raise HTTPException(status_code=403)

    permissoes = {}
    for mod_key in MODULOS:
        permissoes[mod_key] = {
            "ver": f"{mod_key}_ver" in request._form,
            "criar": f"{mod_key}_criar" in request._form,
            "editar": f"{mod_key}_editar" in request._form,
            "excluir": f"{mod_key}_excluir" in request._form,
        }

    salvar_permissoes(usuario_id, estabelecimento_id, permissoes)
    return RedirectResponse(f"/admin/permissoes?estabelecimento_id={estabelecimento_id}&usuario_id={usuario_id}", status_code=302)


@app.get("/admin/configuracoes-recepcionista", response_class=HTMLResponse)
def configuracoes_recepcionista_page(request: Request, usuario=Depends(exigir_login), usuario_id: str = ""):
    estab_id = resolver_estabelecimento(request, usuario)
    if (not estab_id or usuario["tipo"] != "admin") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    recepcionistas = db.fetch_all(
        """SELECT u.id, u.nome, u.email FROM usuarios u
           JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
           WHERE u.tipo = 'recepcionista' AND u.ativo = TRUE AND pe.estabelecimento_id = %s""",
        (estab_id,),
    )

    permissoes_atuais = []
    if usuario_id:
        rows = db.fetch_all(
            "SELECT modulo FROM permissoes_usuario WHERE usuario_id = %s AND estabelecimento_id = %s AND pode_ver = TRUE",
            (int(usuario_id), estab_id),
        )
        permissoes_atuais = [r["modulo"] for r in rows]

    return templates.TemplateResponse(
        "admin/config_recepcionista.html",
        {
            "request": request, "usuario": usuario,
            "recepcionistas": recepcionistas,
            "usuario_id_sel": usuario_id,
            "modulos": MODULOS,
            "permissoes_atuais": permissoes_atuais,
            "mensagem": None, "tipo_mensagem": "success",
        },
    )


@app.post("/admin/configuracoes-recepcionista/salvar")
def salvar_config_recepcionista(
    request: Request,
    usuario_id: int = Form(...),
    usuario=Depends(exigir_login),
):
    estab_id = resolver_estabelecimento(request, usuario)
    if (not estab_id or usuario["tipo"] != "admin") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    permissoes = {}
    for chave, info in MODULOS.items():
        if chave in ("estabelecimentos", "configuracoes"):
            continue
        ativo = f"modulo_{chave}" in request._form
        permissoes[chave] = {"ver": ativo, "criar": ativo, "editar": ativo, "excluir": False}

    salvar_permissoes(usuario_id, estab_id, permissoes)
    return RedirectResponse(f"/admin/configuracoes-recepcionista?usuario_id={usuario_id}&salvo=1", status_code=302)


@app.get("/api/usuarios-por-estab")
def api_usuarios_por_estab(
    request: Request,
    estabelecimento_id: int = Query(...),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    if not usuario.get("is_super"):
        cookie_estab = request.cookies.get("estabelecimento_id")
        if cookie_estab and str(estabelecimento_id) != str(cookie_estab):
            raise HTTPException(status_code=403)

    usuarios = db.fetch_all(
        """SELECT u.id, u.nome, u.tipo
           FROM usuarios u
           WHERE u.ativo = TRUE
             AND (
               u.tipo = 'paciente' AND u.id IN (SELECT usuario_id FROM paciente_estabelecimento WHERE estabelecimento_id = %s)
               OR u.tipo IN ('profissional', 'recepcionista') AND u.id IN (SELECT usuario_id FROM profissional_estabelecimento WHERE estabelecimento_id = %s)
               OR u.tipo = 'admin' AND u.is_super = TRUE
             )
           ORDER BY u.nome""",
        (estabelecimento_id, estabelecimento_id),
    )
    return JSONResponse(content={"usuarios": [{"id": u["id"], "nome": u["nome"], "tipo": u["tipo"]} for u in usuarios]})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, usuario=Depends(exigir_login)):
    plano_info = None
    uso_info = None
    estab_id = resolver_estabelecimento(request, usuario)
    estab_info = None
    if estab_id:
        plano_info = obter_plano_estabelecimento(estab_id)
        uso_info = contar_uso(estab_id)
        estab_info = db.fetch_one("SELECT * FROM estabelecimentos WHERE id = %s", (estab_id,))

    if usuario["tipo"] == "admin" and not usuario.get("is_super") and not estab_id:
        estabs = db.fetch_all("SELECT id, nome, tipo, email FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome")
        if len(estabs) == 1:
            response = RedirectResponse("/dashboard", status_code=302)
            cookie_kwargs = dict(httponly=True, samesite="lax")
            if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
                cookie_kwargs["secure"] = True
            response.set_cookie("estabelecimento_id", str(estabs[0]["id"]), **cookie_kwargs)
            return response
        return templates.TemplateResponse("auth/selecionar_estab.html", {
            "request": request, "usuario": usuario, "estabelecimentos": estabs,
        })

    template_name = f"dashboard/{usuario['tipo']}.html"
    if usuario["tipo"] == "admin" and not usuario.get("is_super"):
        template_name = "dashboard/admin_estab.html"

    cortesia_ate = None
    plano_status = None
    if estab_info and estab_info.get("plano_expira_em"):
        exp = estab_info["plano_expira_em"]
        cortesia_ate = exp.strftime("%d/%m/%Y")
        if exp < datetime.now().date():
            plano_status = "expirado"
        elif (exp - datetime.now().date()).days <= 5:
            plano_status = "proximo_expirar"
    elif plano_info and plano_info.get("valor_mensal", 0) > 0:
        dt_base = estab_info.get("criado_em") or datetime.now()
        cortesia_ate = (dt_base + timedelta(days=30)).strftime("%d/%m/%Y")

    ctx = {
        "request": request, "usuario": usuario, "now": datetime.now(),
        "plano_info": plano_info, "uso_info": uso_info,
        "estab_id": estab_id, "estab_info": estab_info,
        "cortesia_ate": cortesia_ate, "plano_status": plano_status,
    }

    if usuario["tipo"] == "profissional" and estab_id:
        ctx["consultas_hoje"] = db.fetch_all(
            """SELECT c.*, u.nome AS paciente_nome FROM consultas c
               JOIN usuarios u ON u.id = c.paciente_usuario_id
               WHERE c.profissional_usuario_id = %s AND c.estabelecimento_id = %s
               AND DATE(c.data_hora) = CURRENT_DATE ORDER BY c.data_hora""",
            (usuario["id"], estab_id),
        )
        ctx["consultas_proximas"] = db.fetch_all(
            """SELECT c.*, u.nome AS paciente_nome FROM consultas c
               JOIN usuarios u ON u.id = c.paciente_usuario_id
               WHERE c.profissional_usuario_id = %s AND c.estabelecimento_id = %s
               AND c.data_hora > NOW() AND c.status IN ('agendada','confirmada')
               ORDER BY c.data_hora LIMIT 10""",
            (usuario["id"], estab_id),
        )
        ctx["meus_pacientes"] = db.fetch_all(
            """SELECT DISTINCT u.id, u.nome, u.email, u.telefone FROM usuarios u
               JOIN consultas c ON c.paciente_usuario_id = u.id
               WHERE c.profissional_usuario_id = %s AND c.estabelecimento_id = %s AND u.ativo = TRUE
               ORDER BY u.nome""",
            (usuario["id"], estab_id),
        )
        ctx["total_prontuarios"] = db.fetch_one(
            "SELECT COUNT(*) AS total FROM prontuarios WHERE estabelecimento_id = %s",
            (estab_id,),
        )

    if usuario["tipo"] == "recepcionista" and estab_id:
        ctx["consultas_hoje"] = db.fetch_all(
            """SELECT c.*, u.nome AS paciente_nome, up.nome AS profissional_nome FROM consultas c
               JOIN usuarios u ON u.id = c.paciente_usuario_id
               JOIN usuarios up ON up.id = c.profissional_usuario_id
               WHERE c.estabelecimento_id = %s AND DATE(c.data_hora) = CURRENT_DATE
               ORDER BY c.data_hora""",
            (estab_id,),
        )
        ctx["pacientes_cadastrados"] = db.fetch_one(
            "SELECT COUNT(*) AS total FROM paciente_estabelecimento WHERE estabelecimento_id = %s",
            (estab_id,),
        )
        ctx["consultas_pendentes"] = db.fetch_one(
            "SELECT COUNT(*) AS total FROM consultas WHERE estabelecimento_id = %s AND status IN ('agendada','confirmada') AND DATE(data_hora) >= CURRENT_DATE",
            (estab_id,),
        )
        perm_modulos = db.fetch_all(
            "SELECT modulo, pode_ver FROM permissoes_usuario WHERE usuario_id = %s AND estabelecimento_id = %s AND pode_ver = TRUE",
            (usuario["id"], estab_id),
        )
        ctx["modulos_liberados"] = [m["modulo"] for m in perm_modulos]

    if usuario["tipo"] == "paciente":
        ctx["minhas_consultas"] = db.fetch_all(
            """SELECT c.*, up.nome AS profissional_nome, e.nome AS estab_nome FROM consultas c
               JOIN usuarios up ON up.id = c.profissional_usuario_id
               JOIN estabelecimentos e ON e.id = c.estabelecimento_id
               WHERE c.paciente_usuario_id = %s ORDER BY c.data_hora DESC LIMIT 10""",
            (usuario["id"],),
        )
        ctx["meus_prontuarios"] = db.fetch_all(
            """SELECT p.*, e.nome AS estab_nome FROM prontuarios p
               JOIN estabelecimentos e ON e.id = p.estabelecimento_id
               WHERE p.paciente_usuario_id = %s ORDER BY p.criado_em DESC""",
            (usuario["id"],),
        )
        ctx["meus_orcamentos"] = db.fetch_all(
            """SELECT o.*, up.nome AS profissional_nome, e.nome AS estab_nome FROM orcamentos o
               JOIN usuarios up ON up.id = o.profissional_usuario_id
               JOIN estabelecimentos e ON e.id = o.estabelecimento_id
               WHERE o.paciente_usuario_id = %s ORDER BY o.criado_em DESC LIMIT 5""",
            (usuario["id"],),
        )
        ctx["meus_medicamentos"] = db.fetch_all(
            """SELECT pm.*, m.nome AS nome_med
               FROM paciente_medicamentos pm
               LEFT JOIN medicamentos m ON m.id = pm.medicamento_id
               WHERE pm.paciente_id = %s AND pm.ativo = TRUE
               ORDER BY pm.criado_em DESC""",
            (usuario["id"],),
        )
        ctx["meus_sinais_vitais"] = db.fetch_all(
            """SELECT * FROM sinais_vitais
               WHERE paciente_id = %s
               ORDER BY aferido_em DESC LIMIT 10""",
            (usuario["id"],),
        )

    if usuario["tipo"] == "admin" and usuario.get("is_super"):
        ctx["total_estabelecimentos"] = db.fetch_one("SELECT COUNT(*) AS total FROM estabelecimentos WHERE ativo = TRUE")
        ctx["total_usuarios"] = db.fetch_one("SELECT COUNT(*) AS total FROM usuarios WHERE ativo = TRUE")
        ctx["total_pacientes"] = db.fetch_one("SELECT COUNT(*) AS total FROM prontuarios")
        ctx["total_profissionais"] = db.fetch_one("SELECT COUNT(*) AS total FROM usuarios WHERE tipo = 'profissional' AND ativo = TRUE")
        filtro_consultas, params_cf = _mes_atual_filter()
        ctx["total_consultas_mes"] = db.fetch_one(
            f"SELECT COUNT(*) AS total FROM consultas WHERE {filtro_consultas}", params_cf
        )
        filtro_receita, params_rf = _mes_atual_filter('')
        ctx["receita_mes"] = db.fetch_one(
            f"SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE status = 'pago' AND {filtro_receita}", params_rf
        )
        ctx["planos_distribuicao"] = db.fetch_all(
            """SELECT p.nome, COUNT(e.id) AS total FROM planos p
               LEFT JOIN estabelecimentos e ON e.plano_id = p.id AND e.ativo = TRUE
               WHERE p.ativo = TRUE GROUP BY p.id, p.nome ORDER BY p.valor_mensal"""
        )
        ctx["estabelecimentos"] = db.fetch_all(
            """SELECT e.id, e.nome, e.tipo, e.email, e.ativo, p.slug AS plano_slug,
                      (SELECT pe2.usuario_id FROM profissional_estabelecimento pe2
                       JOIN usuarios u2 ON u2.id = pe2.usuario_id
                       WHERE pe2.estabelecimento_id = e.id AND u2.tipo = 'admin' AND u2.is_super = FALSE AND u2.ativo = TRUE
                       LIMIT 1) AS admin_id
               FROM estabelecimentos e
               LEFT JOIN planos p ON p.id = e.plano_id
               WHERE e.ativo = TRUE ORDER BY e.nome"""
        )

    return templates.TemplateResponse(template_name, ctx)


@app.post("/paciente/medicao")
async def paciente_nova_medicao(request: Request, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "paciente":
        raise HTTPException(status_code=403)
    form = dict(await request.form())
    db.execute(
        """INSERT INTO sinais_vitais (paciente_id, pressao_sistolica, pressao_diastolica,
           frequencia_cardiaca, saturacao_oxigenio, temperatura, glicemia, peso, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (usuario["id"],
         int(form["pressao_sistolica"]) if form.get("pressao_sistolica") else None,
         int(form["pressao_diastolica"]) if form.get("pressao_diastolica") else None,
         int(form["frequencia_cardiaca"]) if form.get("frequencia_cardiaca") else None,
         float(form["saturacao_oxigenio"]) if form.get("saturacao_oxigenio") else None,
         float(form["temperatura"]) if form.get("temperatura") else None,
         float(form["glicemia"]) if form.get("glicemia") else None,
         float(form["peso"]) if form.get("peso") else None,
         form.get("observacoes")),
    )
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/api/dashboard-stats")
def dashboard_stats(
    request: Request,
    periodo: str = Query("mes"),
    data_inicio: str = Query(None),
    data_fim: str = Query(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    hoje = datetime.now()
    hoje_str = hoje.strftime("%Y-%m-%d")
    estab_id = resolver_estabelecimento(request, usuario)

    if periodo == "hoje":
        ini = hoje_str
        fim = hoje_str + " 23:59:59"
    elif periodo == "semana":
        seg = hoje - timedelta(days=hoje.weekday())
        ini = seg.strftime("%Y-%m-%d")
        fim = (seg + timedelta(days=6)).strftime("%Y-%m-%d") + " 23:59:59"
    elif periodo == "mes":
        ini = hoje.strftime("%Y-%m-01")
        fim = hoje.strftime("%Y-%m-31") + " 23:59:59"
    elif periodo == "personalizado" and data_inicio and data_fim:
        ini = data_inicio
        fim = data_fim + " 23:59:59"
    else:
        ini = hoje.strftime("%Y-%m-01")
        fim = hoje.strftime("%Y-%m-31") + " 23:59:59"

    estab_filter = ""
    estab_params = []
    if estab_id:
        estab_filter = " AND estabelecimento_id = %s"
        estab_params = [estab_id]

    estabelecimentos = db.fetch_one("SELECT COUNT(*) AS total FROM estabelecimentos WHERE ativo = TRUE")
    if estab_id:
        pacientes = db.fetch_one(
            "SELECT COUNT(*) AS total FROM prontuarios WHERE estabelecimento_id = %s",
            (estab_id,),
        )
        profissionais = db.fetch_one(
            "SELECT COUNT(*) AS total FROM profissional_estabelecimento pe JOIN usuarios u ON u.id = pe.usuario_id WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE",
            (estab_id,),
        )
    else:
        pacientes = db.fetch_one(
            "SELECT COUNT(*) AS total FROM prontuarios"
        )
        profissionais = db.fetch_one(
            "SELECT COUNT(*) AS total FROM profissional_estabelecimento pe JOIN usuarios u ON u.id = pe.usuario_id WHERE u.ativo = TRUE"
        )
    convenios = db.fetch_one("SELECT COUNT(*) AS total FROM convenios WHERE ativo = TRUE")
    procedimentos = db.fetch_one("SELECT COUNT(*) AS total FROM procedimentos WHERE ativo = TRUE")
    prontuarios_count = db.fetch_one(
        "SELECT COUNT(*) AS total FROM prontuarios WHERE estabelecimento_id = %s",
        (estab_id,),
    ) if estab_id else db.fetch_one("SELECT COUNT(*) AS total FROM prontuarios")
    consultas_hoje = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM consultas WHERE DATE(data_hora) = CURRENT_DATE{estab_filter}",
        tuple(estab_params),
    )

    consultas_periodo = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM consultas WHERE data_hora BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )

    consultas_status = db.fetch_all(
        f"SELECT status, COUNT(*) AS total FROM consultas WHERE data_hora BETWEEN %s AND %s{estab_filter} GROUP BY status",
        (ini, fim) + tuple(estab_params),
    )

    orc_rascunho = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'rascunho' AND criado_em BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )
    orc_enviados = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'enviado' AND criado_em BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )
    orc_aprovados = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'aprovado' AND criado_em BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )
    orc_rejeitados = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'rejeitado' AND criado_em BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )

    faturamento = db.fetch_one(
        f"""SELECT COALESCE(SUM(valor_total), 0) AS total
           FROM orcamentos WHERE status = 'aprovado'
           AND atualizado_em BETWEEN %s AND %s{estab_filter}""",
        (ini, fim) + tuple(estab_params),
    )

    faturamento_por_prof = db.fetch_all(
        f"""SELECT u.nome AS profissional_nome, COUNT(o.id) AS qtd, COALESCE(SUM(o.valor_total), 0) AS valor
           FROM orcamentos o
           JOIN usuarios u ON u.id = o.profissional_usuario_id
           WHERE o.status = 'aprovado' AND o.atualizado_em BETWEEN %s AND %s{estab_filter}
           GROUP BY o.profissional_usuario_id, u.nome ORDER BY valor DESC""",
        (ini, fim) + tuple(estab_params),
    )

    return JSONResponse(content={
        "estabelecimentos": estabelecimentos["total"],
        "pacientes": pacientes["total"],
        "profissionais": profissionais["total"],
        "convenios": convenios["total"],
        "procedimentos": procedimentos["total"],
        "prontuarios": prontuarios_count["total"] if prontuarios_count else 0,
        "consultas_total": consultas_periodo["total"],
        "consultas_hoje": consultas_hoje["total"] if consultas_hoje else 0,
        "consultas_status": [{"status": r["status"], "total": r["total"]} for r in consultas_status],
        "orc_rascunho": orc_rascunho["total"],
        "orc_enviados": orc_enviados["total"],
        "orc_aprovados": orc_aprovados["total"],
        "orc_rejeitados": orc_rejeitados["total"],
        "faturamento": float(faturamento["total"]),
        "faturamento_por_prof": [{"profissional_nome": r["profissional_nome"], "qtd": r["qtd"], "valor": float(r["valor"])} for r in faturamento_por_prof],
        "periodo": periodo,
        "data_inicio": ini,
        "data_fim": fim.split(" ")[0],
    })


@app.get("/api/estabelecimentos")
def api_estabelecimentos(usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    estabs = db.fetch_all(
        "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
    )
    return JSONResponse(content={"estabelecimentos": estabs})


@app.get("/api/estabelecimento/{estab_id}/usuarios")
def api_estabelecimento_usuarios(estab_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin" or not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    usuarios = db.fetch_all(
        """SELECT DISTINCT u.id, u.nome, u.email, u.tipo, u.ativo
           FROM usuarios u
           LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
           LEFT JOIN paciente_estabelecimento pae ON pae.usuario_id = u.id
           WHERE u.ativo = TRUE
             AND (u.estabelecimento_id = %s OR pe.estabelecimento_id = %s OR pae.estabelecimento_id = %s)
           ORDER BY u.tipo, u.nome""",
        (estab_id, estab_id, estab_id),
    )
    return JSONResponse(content={"usuarios": usuarios})


_server_start_time = time.time()

@app.get("/api/status")
def sistema_status():
    db_ok = False
    db_latency_ms = -1
    try:
        t0 = time.time()
        db_ok = db.ping()
        db_latency_ms = round((time.time() - t0) * 1000, 1)
    except Exception:
        db_ok = False

    online = is_online() if settings.DB_ENGINE == "postgresql" else True

    return JSONResponse(content={
        "banco": db_ok,
        "db_latency_ms": db_latency_ms,
        "uptime_seg": round(time.time() - _server_start_time),
        "hora_servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "online": online,
    })


@app.get("/api/cache-status")
def cache_status_endpoint():
    status = get_cache_status()
    return JSONResponse(content=status)


@app.post("/api/cache-refresh")
def cache_refresh_endpoint(usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(403, "Apenas super admin pode forcar refresh do cache")
    try:
        from database.cache import download_to_cache
        result = download_to_cache()
        return JSONResponse(content={"ok": result})
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)})


@app.get("/api/backup-status")
def backup_status_endpoint():
    last = get_last_backup()
    count = get_backup_count()
    return JSONResponse(content={"last_backup": last, "count": count})


@app.post("/api/backup-now")
def backup_now_endpoint(usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(403, "Apenas super admin pode forcar backup")
    try:
        dump_file = dump_database()
        if dump_file:
            cleanup_old_backups()
            return JSONResponse(content={"ok": True, "file": os.path.basename(dump_file)})
        return JSONResponse(content={"ok": False, "error": "Dump falhou"})
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)})


UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/api/upload")
async def upload_arquivo(
    arquivo: UploadFile = File(...),
    usuario=Depends(exigir_login),
):
    extensoes_permitidas = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in extensoes_permitidas:
        raise HTTPException(status_code=400, detail="Formato nao permitido. Use JPG, PNG, GIF ou WEBP")

    nome_arquivo = f"{uuid.uuid4().hex}{ext}"
    caminho = os.path.join(UPLOAD_DIR, nome_arquivo)
    conteudo = await arquivo.read()
    if len(conteudo) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo maximo 5MB")

    with open(caminho, "wb") as f:
        f.write(conteudo)

    url = f"/static/uploads/{nome_arquivo}"
    return JSONResponse(content={"url": url})


@app.get("/pacientes")
def listar_pacientes_redirect():
    return RedirectResponse(url="/prontuarios", status_code=302)


@app.get("/estabelecimentos", response_class=HTMLResponse)
def listar_estabelecimentos(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "estabelecimentos", "ver")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estabelecimentos = db.fetch_all(
        "SELECT * FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
    )
    return templates.TemplateResponse(
        "estabelecimentos/lista.html",
        {"request": request, "usuario": usuario, "estabelecimentos": estabelecimentos},
    )


@app.post("/estabelecimentos/criar")
def criar_estabelecimento(
    request: Request,
    nome: str = Form(...),
    tipo: str = Form("clinica"),
    cnpj: str = Form(None),
    telefone: str = Form(None),
    email: str = Form(None),
    endereco: str = Form(None),
    logo_url: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "estabelecimentos", "criar")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute(
        """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, logo_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (nome, tipo, cnpj, telefone, email, endereco, logo_url),
    )
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.post("/estabelecimentos/{estab_id}/desativar")
def desativar_estabelecimento(estab_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute("UPDATE estabelecimentos SET ativo = FALSE WHERE id = %s", (estab_id,))
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.get("/estabelecimentos/{estab_id}/editar", response_class=HTMLResponse)
def editar_estabelecimento(estab_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "estabelecimentos", "editar")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab = db.fetch_one("SELECT * FROM estabelecimentos WHERE id = %s", (estab_id,))
    if not estab:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "estabelecimentos/editar.html",
        {"request": request, "usuario": usuario, "estab": estab,
         "profissionais": db.fetch_all("SELECT id, nome FROM usuarios WHERE tipo IN ('admin','profissional') AND ativo = TRUE ORDER BY nome")},
    )


@app.post("/estabelecimentos/{estab_id}/editar")
def salvar_estabelecimento(
    estab_id: int,
    request: Request,
    nome: str = Form(...),
    tipo: str = Form("clinica"),
    cnpj: str = Form(None),
    telefone: str = Form(None),
    email: str = Form(None),
    endereco: str = Form(None),
    logo_url: str = Form(None),
    responsavel_usuario_id: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    resp_id = int(responsavel_usuario_id) if responsavel_usuario_id and responsavel_usuario_id.strip() else None
    db.execute(
        """UPDATE estabelecimentos
           SET nome = %s, tipo = %s, cnpj = %s, telefone = %s, email = %s, endereco = %s, logo_url = %s,
               responsavel_usuario_id = %s
           WHERE id = %s""",
        (nome, tipo, cnpj, telefone, email, endereco, logo_url, resp_id, estab_id),
    )
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.get("/profissionais", response_class=HTMLResponse)
def listar_profissionais(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "profissionais", "ver")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario)

    if usuario.get("is_super") and not estab_id:
        profissionais = db.fetch_all(
            """SELECT u.*, pe.especialidade, pe.cargo, pe.estabelecimento_id,
                      e.nome AS estabelecimento_nome
               FROM usuarios u
               LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               LEFT JOIN estabelecimentos e ON e.id = pe.estabelecimento_id
               WHERE u.tipo IN ('admin', 'profissional')
               ORDER BY u.ativo DESC, u.nome"""
        )
    elif estab_id:
        profissionais = db.fetch_all(
            """SELECT u.*, pe.especialidade, pe.cargo, pe.estabelecimento_id,
                      e.nome AS estabelecimento_nome
               FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               LEFT JOIN estabelecimentos e ON e.id = pe.estabelecimento_id
               WHERE pe.estabelecimento_id = %s AND u.tipo IN ('admin', 'profissional')
               ORDER BY u.ativo DESC, u.nome""",
            (estab_id,),
        )
    else:
        profissionais = []

    estabelecimentos = db.fetch_all(
        "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
    )

    return templates.TemplateResponse(
        "profissionais/lista.html",
        {"request": request, "usuario": usuario, "profissionais": profissionais, "estabelecimentos": estabelecimentos},
    )


@app.post("/profissionais/criar")
def criar_profissional(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(None),
    senha: str = Form(...),
    foto_url: str = Form(None),
    especialidade: str = Form(None),
    cargo: str = Form(None),
    registro_profissional: str = Form(None),
    estabelecimento_id: str = Form(None),
    cor: str = Form("#0d6efd"),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "profissionais", "criar")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if estab_id:
        try:
            bloquear_se_limite(estab_id, "profissionais")
        except LimiteAtingidoError as e:
            return RedirectResponse(f"/profissionais?erro_quota={e}", status_code=302)

    try:
        user_id = criar_usuario(nome, email, senha, "profissional", telefone)
    except Exception:
        return RedirectResponse("/profissionais?erro=email_existente", status_code=302)

    if foto_url:
        db.execute("UPDATE usuarios SET foto_url = %s WHERE id = %s", (foto_url, user_id))

    if estabelecimento_id and estabelecimento_id.strip():
        db.execute(
            "INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id, especialidade, cargo, registro_profissional, cor) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, int(estabelecimento_id), especialidade, cargo, registro_profissional, cor or "#0d6efd"),
        )

    return RedirectResponse("/profissionais", status_code=302)


@app.get("/profissionais/{prof_id}/editar", response_class=HTMLResponse)
def editar_profissional(prof_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "profissionais", "editar")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    prof = db.fetch_one(
        """SELECT u.*, pe.especialidade, pe.cargo, pe.estabelecimento_id, pe.registro_profissional
           FROM usuarios u
           LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
           WHERE u.id = %s AND u.tipo = 'profissional'""",
        (prof_id,),
    )
    if not prof:
        raise HTTPException(status_code=404)

    estabelecimentos = db.fetch_all(
        "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
    )

    return templates.TemplateResponse(
        "profissionais/editar.html",
        {"request": request, "usuario": usuario, "prof": prof, "estabelecimentos": estabelecimentos},
    )


@app.post("/profissionais/{prof_id}/editar")
def salvar_profissional(
    prof_id: int,
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(None),
    foto_url: str = Form(None),
    especialidade: str = Form(None),
    cargo: str = Form(None),
    registro_profissional: str = Form(None),
    estabelecimento_id: str = Form(None),
    cor: str = Form("#6c757d"),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute(
        "UPDATE usuarios SET nome = %s, email = %s, telefone = %s, foto_url = %s WHERE id = %s",
        (nome, email, telefone, foto_url, prof_id),
    )

    existing = db.fetch_one(
        "SELECT id FROM profissional_estabelecimento WHERE usuario_id = %s", (prof_id,)
    )

    if estabelecimento_id and estabelecimento_id.strip():
        if existing:
            db.execute(
                """UPDATE profissional_estabelecimento
                   SET estabelecimento_id = %s, especialidade = %s, cargo = %s, registro_profissional = %s, cor = %s
                   WHERE usuario_id = %s""",
                (int(estabelecimento_id), especialidade, cargo, registro_profissional, cor or "#6c757d", prof_id),
            )
        else:
            vincular_profissional(prof_id, int(estabelecimento_id), especialidade, cargo, registro_profissional)
            if cor and cor.strip():
                db.execute(
                    "UPDATE profissional_estabelecimento SET cor = %s WHERE usuario_id = %s",
                    (cor, prof_id),
                )

    return RedirectResponse("/profissionais", status_code=302)


@app.post("/profissionais/{prof_id}/desativar")
def desativar_profissional(prof_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute("UPDATE usuarios SET ativo = FALSE WHERE id = %s", (prof_id,))
    return RedirectResponse("/profissionais", status_code=302)


@app.post("/profissionais/{prof_id}/reativar")
def reativar_profissional(prof_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute("UPDATE usuarios SET ativo = TRUE WHERE id = %s", (prof_id,))
    return RedirectResponse("/profissionais", status_code=302)


@app.post("/pacientes/criar")
def criar_paciente(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(None),
    cpf: str = Form(None),
    data_nascimento: str = Form(None),
    endereco: str = Form(None),
    logradouro: str = Form(None),
    numero: str = Form(None),
    complemento: str = Form(None),
    bairro: str = Form(None),
    cidade: str = Form(None),
    estado: str = Form(None),
    cep: str = Form(None),
    senha: str = Form(...),
    foto_url: str = Form(None),
    estabelecimento_id: str = Form(None),
    tipo_pagamento: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "pacientes", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if estab_id:
        try:
            bloquear_se_limite(estab_id, "pacientes")
        except LimiteAtingidoError as e:
            return RedirectResponse(f"/prontuarios?erro_quota={e}", status_code=302)

    try:
        user_id = criar_usuario(nome, email, senha, "paciente", telefone)
    except Exception:
        return RedirectResponse("/prontuarios?erro=email_duplicado", status_code=302)
    partes_endereco = [p for p in (logradouro, numero, complemento, bairro, cidade, cep) if p and p.strip()]
    endereco_completo = ", ".join(partes_endereco) if partes_endereco else (endereco or None)
    db.execute(
        "UPDATE usuarios SET cpf = %s, data_nascimento = %s, endereco = %s WHERE id = %s",
        (cpf or None, data_nascimento or None, endereco_completo, user_id),
    )
    if foto_url:
        db.execute("UPDATE usuarios SET foto_url = %s WHERE id = %s", (foto_url, user_id))

    if estab_id:
        vincular_paciente(user_id, int(estab_id))
        numero = _proximo_numero_prontuario(int(estab_id))
        db.execute(
            "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
            (user_id, int(estab_id), numero),
        )
    elif usuario.get("is_super"):
        estabs = db.fetch_all("SELECT id FROM estabelecimentos WHERE ativo = TRUE")
        for e in estabs:
            vincular_paciente(user_id, int(e["id"]))
            numero = _proximo_numero_prontuario(int(e["id"]))
            db.execute(
                "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
                (user_id, int(e["id"]), numero),
            )

    return RedirectResponse("/prontuarios", status_code=302)


@app.get("/pacientes/{pac_id}", response_class=HTMLResponse)
def ver_paciente(pac_id: int, request: Request, usuario=Depends(exigir_login), tab: str = Query(None)):
    exigir_permissao(usuario, "prontuarios", "ver")
    pac = db.fetch_one(
        """SELECT u.*,
                  (SELECT COUNT(*) FROM prontuarios pr WHERE pr.paciente_usuario_id = u.id AND pr.estabelecimento_id = %s) AS total_prontuarios
           FROM usuarios u WHERE u.id = %s AND u.tipo = 'paciente'""",
        (resolver_estabelecimento(request, usuario), pac_id),
    )
    if not pac:
        raise HTTPException(status_code=404)

    estab_id = resolver_estabelecimento(request, usuario)
    prontuario = None
    if estab_id:
        prontuario = db.fetch_one(
            "SELECT * FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
            (pac_id, estab_id),
        )
    if not prontuario:
        prontuario = db.fetch_one(
            "SELECT * FROM prontuarios WHERE paciente_usuario_id = %s LIMIT 1",
            (pac_id,),
        )
        if prontuario:
            estab_id = str(prontuario["estabelecimento_id"])

    consultas_recentes = []
    if estab_id:
        consultas_recentes = db.fetch_all(
            """SELECT c.*, u.nome AS profissional_nome FROM consultas c
               JOIN usuarios u ON u.id = c.profissional_usuario_id
               WHERE c.paciente_usuario_id = %s AND c.estabelecimento_id = %s
               ORDER BY c.data_hora DESC LIMIT 5""",
            (pac_id, estab_id),
        )

    cpf_fmt = None
    if pac and pac["cpf"]:
        cpf_raw = "".join(c for c in str(pac["cpf"]) if c.isdigit())
        if len(cpf_raw) == 11:
            cpf_fmt = f"{cpf_raw[:3]}.{cpf_raw[3:6]}.{cpf_raw[6:9]}-{cpf_raw[9:]}"
        else:
            cpf_fmt = pac["cpf"]

    return templates.TemplateResponse("pacientes/ver.html", {
        "request": request, "usuario": usuario, "pac": pac,
        "prontuario": prontuario, "consultas_recentes": consultas_recentes,
        "cpf_fmt": cpf_fmt, "tab": tab or "prontuario",
    })


# ─── Anamnese ────────────────────────────────────────────────────────────────

@app.get("/pacientes/{pac_id}/anamnese", response_class=HTMLResponse)
def pagina_anamnese(pac_id: int, request: Request, usuario=Depends(exigir_login), embedded: str = Query(None)):
    exigir_permissao(usuario, "prontuarios", "ver")
    pac = db.fetch_one("SELECT id, nome, data_nascimento FROM usuarios WHERE id = %s AND tipo = 'paciente'", (pac_id,))
    if not pac:
        raise HTTPException(status_code=404)

    estab_id = resolver_estabelecimento(request, usuario)
    anamnese = db.fetch_one(
        "SELECT * FROM anamnese WHERE paciente_id = %s ORDER BY criado_em DESC LIMIT 1",
        (pac_id,),
    )
    if not anamnese and estab_id:
        prontuario = db.fetch_one(
            "SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s LIMIT 1",
            (pac_id, int(estab_id)),
        )
    else:
        prontuario = None

    medicamentos_paciente = db.fetch_all(
        """SELECT pm.*, m.nome AS nome_medicamento_catalogo
           FROM paciente_medicamentos pm
           LEFT JOIN medicamentos m ON m.id = pm.medicamento_id
           WHERE pm.paciente_id = %s AND pm.ativo = TRUE
           ORDER BY pm.criado_em DESC""",
        (pac_id,),
    )

    alertas_farmaco = alertas_paciente(pac_id) if medicamentos_paciente else []
    sintomas = listar_sintomas()

    sinais_vitais = db.fetch_all(
        """SELECT sv.*, u.nome AS profissional_nome
           FROM sinais_vitais sv
           LEFT JOIN usuarios u ON u.id = sv.profissional_usuario_id
           WHERE sv.paciente_id = %s
           ORDER BY sv.aferido_em DESC
           LIMIT 20""",
        (pac_id,),
    )

    return templates.TemplateResponse(
        "pacientes/anamnese.html",
        {
            "request": request, "usuario": usuario, "pac": pac,
            "anamnese": anamnese, "prontuario": prontuario,
            "medicamentos": medicamentos_paciente,
            "alertas_farmaco": alertas_farmaco,
            "sintomas": sintomas,
            "sinais_vitais": sinais_vitais,
            "embedded": embedded in ("1", "True", "true"),
        },
    )


@app.post("/pacientes/{pac_id}/anamnese/salvar")
async def salvar_anamnese(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    estab_id = resolver_estabelecimento(request, usuario)

    prontuario = None
    if estab_id:
        prontuario = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s LIMIT 1", (pac_id, int(estab_id)))
    if not prontuario:
        prontuario = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s LIMIT 1", (pac_id,))

    existing = db.fetch_one("SELECT id FROM anamnese WHERE paciente_id = %s ORDER BY criado_em DESC LIMIT 1", (pac_id,))

    fields = {
        "queixa_principal": form.get("queixa_principal"),
        "historico_doenca_atual": form.get("historico_doenca_atual"),
        "impressao": form.get("impressao"),
        "historico_medico": form.get("historico_medico"),
        "historico_familiar": form.get("historico_familiar"),
        "alergias": form.get("alergias"),
        "habits": form.get("habits"),
        "atividade_fisica": form.get("atividade_fisica"),
        "tabagismo": form.get("tabagismo"),
        "etilismo": form.get("etilismo"),
        "refeicoes_dia": int(form["refeicoes_dia"]) if form.get("refeicoes_dia") else None,
        "horas_sono": float(form["horas_sono"]) if form.get("horas_sono") else None,
        "gestante": form.get("gestante") == "1" if form.get("gestante") else None,
        "numero_gestacoes": int(form["numero_gestacoes"]) if form.get("numero_gestacoes") else None,
        "observacoes": form.get("observacoes"),
        "revisao_sistemas": form.get("revisao_sistemas", "{}"),
    }

    if existing:
        fields["id"] = existing["id"]
        db.execute(
            """UPDATE anamnese SET queixa_principal=%(queixa_principal)s, historico_doenca_atual=%(historico_doenca_atual)s,
               impressao=%(impressao)s, historico_medico=%(historico_medico)s, historico_familiar=%(historico_familiar)s,
               alergias=%(alergias)s, habits=%(habits)s, atividade_fisica=%(atividade_fisica)s,
               tabagismo=%(tabagismo)s, etilismo=%(etilismo)s, refeicoes_dia=%(refeicoes_dia)s,
               horas_sono=%(horas_sono)s, gestante=%(gestante)s, numero_gestacoes=%(numero_gestacoes)s,
               observacoes=%(observacoes)s, revisao_sistemas=%(revisao_sistemas)s,
               profissional_usuario_id=%(profissional)s, atualizado_em=NOW()
               WHERE id=%(id)s""",
            {**fields, "profissional": usuario["id"], "id": existing["id"]},
        )
    else:
        db.execute(
            """INSERT INTO anamnese (paciente_id, estabelecimento_id, prontuario_id, profissional_usuario_id,
               queixa_principal, historico_doenca_atual, impressao, historico_medico, historico_familiar,
               alergias, habits, atividade_fisica, tabagismo, etilismo, refeicoes_dia, horas_sono,
               gestante, numero_gestacoes, observacoes, revisao_sistemas)
               VALUES (%(paciente)s,%(estabelecimento)s,%(prontuario)s,%(profissional)s,
               %(queixa_principal)s,%(historico_doenca_atual)s,%(impressao)s,
               %(historico_medico)s,%(historico_familiar)s,%(alergias)s,%(habits)s,%(atividade_fisica)s,
               %(tabagismo)s,%(etilismo)s,%(refeicoes_dia)s,%(horas_sono)s,%(gestante)s,%(numero_gestacoes)s,
               %(observacoes)s,%(revisao_sistemas)s)""",
            {**fields,
             "paciente": pac_id,
             "estabelecimento": int(estab_id) if estab_id else None,
             "prontuario": prontuario["id"] if prontuario else None,
             "profissional": usuario["id"]},
        )

    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1", status_code=302)


@app.get("/admin/medicamentos/cadastrar", response_class=HTMLResponse)
def pagina_cadastrar_medicamento(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    return templates.TemplateResponse(
        "admin/cadastrar_medicamento.html",
        {
            "request": request,
            "usuario": usuario,
            "erro": request.query_params.get("erro"),
            "salvo": request.query_params.get("salvo"),
        },
    )


@app.post("/admin/medicamentos/cadastrar")
async def cadastrar_medicamento(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    nome = form.get("nome", "").strip()
    if not nome or len(nome) < 2:
        return RedirectResponse("/admin/medicamentos/cadastrar?erro=nome_curto", status_code=302)
    try:
        existente = db.fetch_one("SELECT id FROM medicamentos WHERE nome = %s", (nome,))
        if existente:
            return RedirectResponse("/admin/medicamentos/cadastrar?erro=duplicado", status_code=302)
        db.execute(
            "INSERT INTO medicamentos (nome, principio_ativo) VALUES (%s, %s)",
            (nome, form.get("principio_ativo", "").strip() or None),
        )
    except Exception:
        return RedirectResponse("/admin/medicamentos/cadastrar?erro=erro", status_code=302)
    return RedirectResponse("/admin/medicamentos/cadastrar?salvo=1", status_code=302)


@app.get("/medicamentos/buscar")
def buscar_medicamentos(q: str = "", usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    if len(q) < 2:
        return JSONResponse([])
    rows = db.fetch_all(
        "SELECT id, nome, principio_ativo FROM medicamentos WHERE nome LIKE %s OR principio_ativo LIKE %s LIMIT 20",
        (f"%{q}%", f"%{q}%"),
    )
    return JSONResponse([{"id": r["id"], "nome": r["nome"], "principio_ativo": r["principio_ativo"]} for r in rows])


@app.post("/medicamentos/criar")
async def criar_medicamento(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    nome = form.get("nome", "").strip()
    if not nome or len(nome) < 2:
        return JSONResponse({"ok": False, "erro": "Nome muito curto"})
    try:
        existente = db.fetch_one("SELECT id FROM medicamentos WHERE nome = %s", (nome,))
        if existente:
            return JSONResponse({"ok": True, "id": existente["id"], "nome": nome})
        if settings.DB_ENGINE == "postgresql":
            cursor = db.execute(
                "INSERT INTO medicamentos (nome, principio_ativo) VALUES (%s, %s) RETURNING id",
                (nome, form.get("principio_ativo", "").strip() or None),
            )
            row = cursor.fetchone()
            novo_id = row["id"] if row else None
            return JSONResponse({"ok": True, "id": novo_id, "nome": nome})
        cursor = db.execute(
            "INSERT INTO medicamentos (nome, principio_ativo) VALUES (%s, %s)",
            (nome, form.get("principio_ativo", "").strip() or None),
        )
        return JSONResponse({"ok": True, "id": cursor.lastrowid, "nome": nome})
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)})


@app.get("/pacientes/{pac_id}/medicamentos/json")
def listar_medicamentos_json(pac_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    rows = db.fetch_all(
        """SELECT pm.id, COALESCE(m.nome, pm.nome_medicamento) AS nome,
                  pm.dose, pm.frequencia, pm.via, pm.observacoes, pm.ativo
           FROM paciente_medicamentos pm
           LEFT JOIN medicamentos m ON m.id = pm.medicamento_id
           WHERE pm.paciente_id = %s AND pm.ativo = TRUE
           ORDER BY pm.criado_em DESC""",
        (pac_id,),
    )
    return JSONResponse([dict(r) for r in rows])


@app.post("/pacientes/{pac_id}/medicamentos/verificar")
async def verificar_medicamento(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    medicamento_id = int(form["medicamento_id"]) if form.get("medicamento_id") else None
    nome_medicamento = (form.get("nome_medicamento") or "").strip() or None
    alertas = checar_medicamento_paciente(pac_id, medicamento_id, nome_medicamento)
    return JSONResponse({"alertas": alertas, "quantidade": len(alertas)})


@app.post("/pacientes/{pac_id}/sugestoes")
async def sugestoes_sintomas(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    form = await request.form()
    sintoma_ids = []
    for v in form.getlist("sintoma_ids"):
        try:
            sintoma_ids.append(int(v))
        except (TypeError, ValueError):
            continue
    sugestoes = sugestoes_seguras(pac_id, sintoma_ids)
    return JSONResponse({"sugestoes": sugestoes, "quantidade": len(sugestoes)})


@app.post("/pacientes/{pac_id}/medicamentos")
async def adicionar_medicamento(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    medicamento_id = int(form["medicamento_id"]) if form.get("medicamento_id") else None
    nome_medicamento = (form.get("nome_medicamento") or "").strip() or None
    if medicamento_id is not None:
        existe = db.fetch_one("SELECT id FROM medicamentos WHERE id = %s", (medicamento_id,))
        if not existe:
            medicamento_id = None
    if not medicamento_id and not nome_medicamento:
        return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=medicamentos&erro=med_vazio", status_code=302)

    alertas = checar_medicamento_paciente(pac_id, medicamento_id, nome_medicamento)
    graves = [a for a in alertas if a.get("severidade") == "grave"]
    if graves and form.get("confirmar_grave") != "1":
        from urllib.parse import quote
        resumo = "; ".join(a["mensagem"] for a in graves[:3])
        if len(graves) > 3:
            resumo += f" (+{len(graves) - 3} outras)"
        msg = f"Medicamento não adicionado — alerta(s) grave(s): {resumo}"
        return RedirectResponse(
            url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=medicamentos&erro={quote(msg)}",
            status_code=302,
        )

    db.execute(
        """INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, nome_medicamento, dose, frequencia, via, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (pac_id, medicamento_id, nome_medicamento,
         form.get("dose"), form.get("frequencia"), form.get("via"),
         form.get("observacoes")),
    )
    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=medicamentos", status_code=302)


@app.post("/pacientes/{pac_id}/medicamentos/{med_id}/remover")
def remover_medicamento(pac_id: int, med_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    db.execute("UPDATE paciente_medicamentos SET ativo = FALSE WHERE id = %s AND paciente_id = %s", (med_id, pac_id))
    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=medicamentos", status_code=302)


@app.post("/pacientes/{pac_id}/sinais-vitais")
async def adicionar_sinais_vitais(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = dict(await request.form())
    estab_id = resolver_estabelecimento(request, usuario)
    prontuario = None
    if estab_id:
        prontuario = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s LIMIT 1", (pac_id, int(estab_id)))
    db.execute(
        """INSERT INTO sinais_vitais (paciente_id, prontuario_id, profissional_usuario_id,
           pressao_sistolica, pressao_diastolica, frequencia_cardiaca, frequencia_respiratoria,
           saturacao_oxigenio, temperatura, glicemia, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pac_id, prontuario["id"] if prontuario else None, usuario["id"],
         int(form["pressao_sistolica"]) if form.get("pressao_sistolica") else None,
         int(form["pressao_diastolica"]) if form.get("pressao_diastolica") else None,
         int(form["frequencia_cardiaca"]) if form.get("frequencia_cardiaca") else None,
         int(form["frequencia_respiratoria"]) if form.get("frequencia_respiratoria") else None,
         float(form["saturacao_oxigenio"]) if form.get("saturacao_oxigenio") else None,
         float(form["temperatura"]) if form.get("temperatura") else None,
         float(form["glicemia"]) if form.get("glicemia") else None,
         form.get("observacoes")),
    )
    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=sinais", status_code=302)


@app.get("/pacientes/{pac_id}/sinais-vitais/json")
def listar_sinais_vitais_json(pac_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    rows = db.fetch_all(
        """SELECT sv.*, u.nome AS profissional_nome
           FROM sinais_vitais sv
           LEFT JOIN usuarios u ON u.id = sv.profissional_usuario_id
           WHERE sv.paciente_id = %s
           ORDER BY sv.aferido_em DESC
           LIMIT 50""",
        (pac_id,),
    )
    resultado = []
    for r in rows:
        d = dict(r)
        if d.get("aferido_em"):
            d["aferido_em"] = d["aferido_em"].strftime("%Y-%m-%dT%H:%M:%S")
        if d.get("criado_em"):
            d["criado_em"] = d["criado_em"].strftime("%Y-%m-%dT%H:%M:%S")
        resultado.append(d)
    return JSONResponse(resultado)


# ─── Exames Laboratoriais ────────────────────────────────────────────────────

@app.post("/pacientes/{pac_id}/exames/upload")
async def upload_exame(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    form = await request.form()
    nome_exame = form.get("nome_exame", "").strip()
    if not nome_exame:
        return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=exames&erro=Nome+do+exame+obrigatorio", status_code=302)

    estab_id = resolver_estabelecimento(request, usuario)
    prontuario = None
    if estab_id:
        prontuario = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s LIMIT 1", (pac_id, int(estab_id)))

    arquivo_pdf = None
    arquivo_nome = None
    pdf_file = form.get("arquivo_pdf")
    if pdf_file and pdf_file.filename:
        ext = os.path.splitext(pdf_file.filename)[1].lower()
        if ext != ".pdf":
            return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=exames&erro=Apenas+PDF+sao+aceitos", status_code=302)
        import base64
        content = await pdf_file.read()
        if len(content) > 10 * 1024 * 1024:
            return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=exames&erro=Arquivo+muito+grande+(max+10MB)", status_code=302)
        arquivo_pdf = base64.b64encode(content).decode("utf-8")
        arquivo_nome = pdf_file.filename

    db.execute(
        """INSERT INTO exames_laboratoriais (paciente_id, prontuario_id, profissional_usuario_id,
           nome_exame, data_solicitacao, data_resultado, resultado, valor_referencia,
           laboratorio, observacoes, arquivo_pdf, arquivo_nome)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pac_id, prontuario["id"] if prontuario else None, usuario["id"],
         nome_exame,
         form.get("data_solicitacao") or None,
         form.get("data_resultado") or None,
         form.get("resultado"),
         form.get("valor_referencia"),
         form.get("laboratorio"),
         form.get("observacoes"),
         arquivo_pdf, arquivo_nome),
    )
    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=exames", status_code=302)


@app.get("/pacientes/{pac_id}/exames/json")
def listar_exames_json(pac_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    rows = db.fetch_all(
        """SELECT id, nome_exame, data_solicitacao, data_resultado, resultado, valor_referencia,
                  laboratorio, observacoes, arquivo_nome, criado_em
           FROM exames_laboratoriais
           WHERE paciente_id = %s
           ORDER BY COALESCE(data_resultado, data_solicitacao, criado_em) DESC""",
        (pac_id,),
    )
    exames = []
    for r in rows:
        d = dict(r)
        d["tem_pdf"] = bool(r["arquivo_nome"])
        for chave in ("data_solicitacao", "data_resultado", "criado_em"):
            valor = d.get(chave)
            if valor is not None and hasattr(valor, "strftime"):
                d[chave] = valor.strftime("%Y-%m-%d")
        exames.append(d)
    return JSONResponse(exames)


@app.get("/pacientes/{pac_id}/exames/{exame_id}/pdf")
def visualizar_pdf(pac_id: int, exame_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    from fastapi.responses import Response
    row = db.fetch_one(
        "SELECT arquivo_pdf, arquivo_nome FROM exames_laboratoriais WHERE id = %s AND paciente_id = %s",
        (exame_id, pac_id),
    )
    if not row or not row["arquivo_pdf"]:
        raise HTTPException(status_code=404)
    import base64
    content = base64.b64decode(row["arquivo_pdf"])
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{row["arquivo_nome"] or "exame.pdf"}"',
    })


@app.post("/pacientes/{pac_id}/exames/{exame_id}/remover")
def remover_exame(pac_id: int, exame_id: int, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "editar")
    db.execute("DELETE FROM exames_laboratoriais WHERE id = %s AND paciente_id = %s", (exame_id, pac_id))
    return RedirectResponse(url=f"/pacientes/{pac_id}/anamnese?embedded=1&tab=exames", status_code=302)


@app.get("/pacientes/{pac_id}/editar", response_class=HTMLResponse)
def editar_paciente(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "pacientes", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    pac = db.fetch_one("SELECT * FROM usuarios WHERE id = %s AND tipo = 'paciente'", (pac_id,))
    if not pac:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "pacientes/editar.html",
        {"request": request, "usuario": usuario, "pac": pac},
    )


@app.post("/pacientes/{pac_id}/editar")
def salvar_paciente(
    pac_id: int,
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(None),
    cpf: str = Form(None),
    data_nascimento: str = Form(None),
    endereco: str = Form(None),
    logradouro: str = Form(None),
    numero: str = Form(None),
    complemento: str = Form(None),
    bairro: str = Form(None),
    cidade: str = Form(None),
    estado: str = Form(None),
    cep: str = Form(None),
    foto_url: str = Form(None),
    senha: str = Form(""),
    codigo_paciente: str = Form(None),
    numero_documentacao: str = Form(None),
    indicacao: str = Form(None),
    estado_civil: str = Form(None),
    profissao: str = Form(None),
    nome_pai: str = Form(None),
    nome_mae: str = Form(None),
    tipo_pagamento: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    partes_end = [p for p in (logradouro, numero, complemento, bairro, cidade, cep) if p and p.strip()]
    endereco_final = ", ".join(partes_end) if partes_end else (endereco or None)

    base_fields = """nome = %s, email = %s, telefone = %s, cpf = %s, data_nascimento = %s,
                     endereco = %s, foto_url = %s, codigo_paciente = %s, numero_documentacao = %s,
                     indicacao = %s, estado_civil = %s, profissao = %s, nome_pai = %s, nome_mae = %s"""
    base_params = (
        nome, email, telefone, cpf or None, data_nascimento or None,
        endereco_final, foto_url, codigo_paciente or None, numero_documentacao or None,
        indicacao or None, estado_civil or None, profissao or None, nome_pai or None, nome_mae or None,
    )

    if senha and senha.strip():
        from utils.auth import hash_senha
        senha_hash = hash_senha(senha.strip())
        db.execute(
            f"UPDATE usuarios SET {base_fields}, senha_hash = %s WHERE id = %s",
            (*base_params, senha_hash, pac_id),
        )
    else:
        db.execute(
            f"UPDATE usuarios SET {base_fields} WHERE id = %s",
            (*base_params, pac_id),
        )
    return RedirectResponse("/prontuarios", status_code=302)


@app.get("/consultas", response_class=HTMLResponse)
def listar_consultas(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
    estab_id = resolver_estabelecimento(request, usuario)
    exigir_permissao(usuario, "consultas", "ver", estab_id)
    pacientes_filtro = obter_pacientes_para_filtro(usuario, estab_id)
    paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    if usuario["tipo"] == "paciente":
        consultas = db.fetch_all(
            """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome,
                      u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
               FROM consultas c
               JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
               JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
               WHERE c.paciente_usuario_id = %s
               ORDER BY c.data_hora DESC""",
            (usuario["id"],),
        )
    elif usuario["tipo"] == "profissional":
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome,
                          u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                   WHERE c.profissional_usuario_id = %s"""
        params = [usuario["id"]]
        if estab_id:
            query += " AND c.estabelecimento_id = %s"
            params.append(estab_id)
        if paciente_id_int:
            query += " AND c.paciente_usuario_id = %s"
            params.append(paciente_id_int)
        query += " ORDER BY c.data_hora DESC"
        consultas = db.fetch_all(query, tuple(params))
    elif estab_id:
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome,
                          u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                   WHERE c.estabelecimento_id = %s"""
        params = [estab_id]
        if paciente_id_int:
            query += " AND c.paciente_usuario_id = %s"
            params.append(paciente_id_int)
        query += " ORDER BY c.data_hora DESC"
        consultas = db.fetch_all(query, tuple(params))
    else:
        if usuario.get("is_super"):
            query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome,
                              u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                       FROM consultas c
                       JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                       JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                       WHERE 1=1"""
            params = []
            if paciente_id_int:
                query += " AND c.paciente_usuario_id = %s"
                params.append(paciente_id_int)
            query += " ORDER BY c.data_hora DESC"
            consultas = db.fetch_all(query, tuple(params))
        else:
            consultas = []

    return templates.TemplateResponse(
        "consultas/lista.html",
        {"request": request, "usuario": usuario, "consultas": consultas,
         "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int},
    )


@app.get("/consultas/nova", response_class=HTMLResponse)
def nova_consulta(request: Request, usuario=Depends(exigir_login)):
    estab_id = resolver_estabelecimento(request, usuario)
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    estabelecimentos = []
    if usuario["tipo"] == "admin" and not request.cookies.get("estabelecimento_id"):
        estabelecimentos = db.fetch_all(
            "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
        )

    procedimentos = db.fetch_all(
        "SELECT id, nome, duracao_minutos FROM procedimentos WHERE ativo = TRUE ORDER BY nome"
    )

    convenios = db.fetch_all("SELECT id, nome FROM convenios WHERE ativo = TRUE ORDER BY nome")

    if not estab_id:
        return templates.TemplateResponse(
            "consultas/formulario.html",
            {"request": request, "usuario": usuario, "pacientes": [], "profissionais": [],
             "estabelecimentos": estabelecimentos, "estabelecimento_selecionado": None,
             "procedimentos": procedimentos, "convenios": convenios},
        )

    pacientes = db.fetch_all(
        """SELECT u.id, u.nome FROM usuarios u
           JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
           WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
        (estab_id,),
    )

    profissionais = db.fetch_all(
        """SELECT u.id, u.nome FROM usuarios u
           JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
           WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
        (estab_id,),
    )

    return templates.TemplateResponse(
        "consultas/formulario.html",
        {"request": request, "usuario": usuario, "pacientes": pacientes, "profissionais": profissionais,
         "estabelecimentos": estabelecimentos, "estabelecimento_selecionado": estab_id,
         "procedimentos": procedimentos, "convenios": convenios},
    )


@app.post("/consultas/criar")
def criar_consulta(
    request: Request,
    paciente_id: int = Form(...),
    profissional_id: int = Form(...),
    data_hora: str = Form(...),
    duracao: int = Form(30),
    procedimento_id: str = Form(""),
    observacoes: str = Form(None),
    estabelecimento_id: str = Form(None),
    origem: str = Form(None),
    usuario=Depends(exigir_login),
):
    procedimento_id = int(procedimento_id) if procedimento_id and procedimento_id.strip() else None
    exigir_permissao(usuario, "consultas", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if not estab_id or usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    try:
        bloquear_se_limite(estab_id, "consultas_mes")
    except LimiteAtingidoError as e:
        return RedirectResponse(f"/consultas?erro_quota={e}", status_code=302)

    prontuario = db.fetch_one(
        "SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
        (paciente_id, estab_id),
    )

    if settings.DB_ENGINE == "postgresql":
        cursor = db.execute(
            """INSERT INTO consultas
               (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, prontuario_id, procedimento_id, data_hora, duracao_minutos, observacoes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (paciente_id, profissional_id, estab_id, prontuario["id"] if prontuario else None, procedimento_id, data_hora, duracao, observacoes),
        )
        row = cursor.fetchone()
        consulta_id_val = row["id"] if row else None
    else:
        cursor = db.execute(
            """INSERT INTO consultas
               (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, prontuario_id, procedimento_id, data_hora, duracao_minutos, observacoes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (paciente_id, profissional_id, estab_id, prontuario["id"] if prontuario else None, procedimento_id, data_hora, duracao, observacoes),
        )
        consulta_id_val = cursor.lastrowid

    if prontuario:
        from datetime import datetime as _dt
        data_consulta = _dt.strptime(data_hora, "%Y-%m-%dT%H:%M").date() if "T" in data_hora else _dt.strptime(data_hora, "%Y-%m-%d").date()
        db.execute(
            """INSERT INTO evolucoes
               (prontuario_id, consulta_id, profissional_usuario_id, data)
               VALUES (%s, %s, %s, %s)""",
            (prontuario["id"], consulta_id_val, profissional_id, data_consulta),
        )

    try:
        dados_paciente = db.fetch_one("SELECT nome, email FROM usuarios WHERE id = %s", (paciente_id,))
        dados_profissional = db.fetch_one("SELECT nome FROM usuarios WHERE id = %s", (profissional_id,))
        dados_estab = db.fetch_one("SELECT nome, endereco FROM estabelecimentos WHERE id = %s", (estab_id,))
        dados_proc = db.fetch_one("SELECT nome FROM procedimentos WHERE id = %s", (procedimento_id,)) if procedimento_id else None

        if dados_paciente and dados_paciente.get("email"):
            from datetime import datetime as _dt3
            dt_consulta = _dt3.strptime(data_hora, "%Y-%m-%dT%H:%M") if "T" in data_hora else _dt3.strptime(data_hora, "%Y-%m-%d")
            corpo = montar_confirmacao_agendamento(
                paciente_nome=dados_paciente["nome"],
                profissional_nome=dados_profissional["nome"] if dados_profissional else "-",
                data_formatada=dt_consulta.strftime("%d/%m/%Y"),
                hora_formatada=dt_consulta.strftime("%H:%M"),
                duracao=duracao,
                procedimento=dados_proc["nome"] if dados_proc else None,
                estabelecimento_nome=dados_estab["nome"] if dados_estab else None,
                estabelecimento_endereco=dados_estab["endereco"] if dados_estab else None,
            )
            enviar_email(
                destinatario=dados_paciente["email"],
                assunto=f"Consulta agendada - {dt_consulta.strftime('%d/%m/%Y')} as {dt_consulta.strftime('%H:%M')}",
                corpo_html=corpo,
            )
    except Exception as e:
        logger.warning(f"Erro ao enviar email de confirmacao: {e}")

    if origem == "agenda":
        from datetime import datetime as _dt2
        dt_consulta = _dt2.strptime(data_hora, "%Y-%m-%dT%H:%M") if "T" in data_hora else _dt2.strptime(data_hora, "%Y-%m-%d")
        return RedirectResponse(f"/agenda?data={dt_consulta.strftime('%Y-%m-%d')}", status_code=302)
    return RedirectResponse("/consultas", status_code=302)


@app.get("/consultas/{consulta_id}/editar", response_class=HTMLResponse)
def editar_consulta_form(consulta_id: int, request: Request, usuario=Depends(exigir_login), origem: str = Query(None)):
    exigir_permissao(usuario, "consultas", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    consulta = db.fetch_one(
        """SELECT c.*, u.nome AS paciente_nome, p2.nome AS profissional_nome
           FROM consultas c
           JOIN usuarios u ON u.id = c.paciente_usuario_id
           JOIN usuarios p2 ON p2.id = c.profissional_usuario_id
           WHERE c.id = %s""",
        (consulta_id,),
    )
    if not consulta:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and consulta["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    procedimentos = db.fetch_all(
        "SELECT id, nome, duracao_minutos FROM procedimentos WHERE ativo = TRUE ORDER BY nome"
    )

    return templates.TemplateResponse(
        "consultas/editar.html",
        {"request": request, "usuario": usuario, "consulta": consulta, "procedimentos": procedimentos, "origem": origem},
    )


@app.post("/consultas/{consulta_id}/editar")
def salvar_edicao_consulta(
    consulta_id: int,
    request: Request,
    data_hora: str = Form(...),
    duracao: int = Form(30),
    procedimento_id: str = Form(""),
    observacoes: str = Form(None),
    origem: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "consultas", "editar")
    if is_write_limited(request, usuario, "edit"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    consulta = db.fetch_one("SELECT * FROM consultas WHERE id = %s", (consulta_id,))
    if not consulta:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and consulta["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    procedimento_id_val = int(procedimento_id) if procedimento_id and procedimento_id.strip() else None

    from datetime import datetime as _dt
    nova_data = _dt.strptime(data_hora, "%Y-%m-%dT%H:%M") if "T" in data_hora else _dt.strptime(data_hora, "%Y-%m-%d")
    data_mudou = consulta["data_hora"] != nova_data

    db.execute(
        "UPDATE consultas SET data_hora = %s, duracao_minutos = %s, procedimento_id = %s, observacoes = %s WHERE id = %s",
        (nova_data, duracao, procedimento_id_val, observacoes or None, consulta_id),
    )

    if data_mudou and consulta.get("prontuario_id"):
        nova_data_date = nova_data.date()
        db.execute(
            "UPDATE evolucoes SET data = %s WHERE consulta_id = %s",
            (nova_data_date, consulta_id),
        )

    if origem == "agenda":
        destino = f"/agenda?data={nova_data.strftime('%Y-%m-%d')}"
    else:
        destino = "/consultas"
    return RedirectResponse(destino, status_code=302)


@app.post("/consultas/{consulta_id}/status")
def atualizar_status_consulta(
    consulta_id: int,
    request: Request,
    status: str = Form(...),
    origem: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "consultas", "editar")
    if is_write_limited(request, usuario, "status"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    consulta = db.fetch_one("SELECT * FROM consultas WHERE id = %s", (consulta_id,))
    if not consulta:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and consulta["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    valid_statuses = {"agendada", "confirmada", "em_andamento", "concluida", "cancelada", "faltou"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Status invalido")

    db.execute("UPDATE consultas SET status = %s WHERE id = %s", (status, consulta_id))

    if status in ("faltou", "cancelada") and consulta.get("prontuario_id"):
        evolucao = db.fetch_one(
            "SELECT id, queixa_principal, diagnostico, procedimento_realizado FROM evolucoes WHERE consulta_id = %s",
            (consulta_id,),
        )
        if evolucao and not evolucao["queixa_principal"] and not evolucao["diagnostico"] and not evolucao["procedimento_realizado"]:
            motivo = "Paciente faltou" if status == "faltou" else "Consulta cancelada"
            db.execute(
                "UPDATE evolucoes SET procedimento_realizado = %s WHERE id = %s",
                (motivo, evolucao["id"]),
            )

    destino = "/agenda" if origem == "agenda" else "/consultas"
    return RedirectResponse(destino, status_code=302)


@app.get("/consultas/{consulta_id}/atender", response_class=HTMLResponse)
def atender_consulta(consulta_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "consultas", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    consulta = db.fetch_one(
        """SELECT c.*, u.nome AS paciente_nome, u.email AS paciente_email,
                  u.telefone AS paciente_telefone, u.cpf AS paciente_cpf,
                  u.data_nascimento AS paciente_nascimento,
                  p2.nome AS profissional_nome,
                  proc.nome AS procedimento_nome
           FROM consultas c
           JOIN usuarios u ON u.id = c.paciente_usuario_id
           JOIN usuarios p2 ON p2.id = c.profissional_usuario_id
           LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
           WHERE c.id = %s""",
        (consulta_id,),
    )
    if not consulta:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and consulta["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    evolucao_data = None
    if consulta.get("prontuario_id"):
        evolucao_data = db.fetch_one(
            """SELECT id, queixa_principal, diagnostico, procedimento_realizado, observacoes
               FROM evolucoes WHERE consulta_id = %s""", (consulta_id,),
        )

    return templates.TemplateResponse(
        "consultas/atender.html",
        {"request": request, "usuario": usuario, "consulta": consulta, "evolucao": evolucao_data},
    )


@app.post("/consultas/{consulta_id}/atender")
def salvar_atendimento(
    consulta_id: int,
    request: Request,
    queixa: str = Form(None),
    diagnostico: str = Form(None),
    procedimento: str = Form(None),
    observacoes: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "consultas", "editar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    consulta = db.fetch_one("SELECT * FROM consultas WHERE id = %s", (consulta_id,))
    if not consulta:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and consulta["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    if consulta.get("status") in ("cancelada",):
        return RedirectResponse("/consultas", status_code=302)

    if consulta.get("prontuario_id"):
        evolucao = db.fetch_one(
            "SELECT id FROM evolucoes WHERE consulta_id = %s", (consulta_id,)
        )
        if evolucao:
            db.execute(
                """UPDATE evolucoes
                   SET queixa_principal = %s, diagnostico = %s, procedimento_realizado = %s, observacoes = %s
                   WHERE id = %s""",
                (queixa or None, diagnostico or None, procedimento or None, observacoes or None, evolucao["id"]),
            )
        else:
            db.execute(
                """INSERT INTO evolucoes
                   (prontuario_id, consulta_id, profissional_usuario_id, queixa_principal, diagnostico, procedimento_realizado, observacoes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (consulta["prontuario_id"], consulta_id, consulta["profissional_usuario_id"],
                 queixa or None, diagnostico or None, procedimento or None, observacoes or None),
            )

    if consulta.get("status") != "concluida":
        db.execute("UPDATE consultas SET status = 'concluida' WHERE id = %s", (consulta_id,))

    return RedirectResponse(f"/prontuarios/{consulta['prontuario_id']}" if consulta.get("prontuario_id") else "/consultas", status_code=302)


@app.get("/prontuarios", response_class=HTMLResponse)
def listar_prontuarios(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
    estab_id = resolver_estabelecimento(request, usuario)
    exigir_permissao(usuario, "prontuarios", "ver", estab_id)
    pacientes_filtro = obter_pacientes_para_filtro(usuario, estab_id)
    paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    if usuario["tipo"] == "paciente":
        prontuarios = db.fetch_all(
            """SELECT p.*, u.nome AS paciente_nome,
                      u.cpf AS paciente_cpf, u.telefone AS paciente_telefone, u.email AS paciente_email
               FROM prontuarios p
               JOIN usuarios u ON u.id = p.paciente_usuario_id
               WHERE p.paciente_usuario_id = %s""",
            (usuario["id"],),
        )
    elif usuario["tipo"] == "profissional":
        query = """SELECT p.*, u.nome AS paciente_nome,
                          u.cpf AS paciente_cpf, u.telefone AS paciente_telefone, u.email AS paciente_email
                   FROM prontuarios p
                   JOIN usuarios u ON u.id = p.paciente_usuario_id
                   WHERE p.paciente_usuario_id IN (
                       SELECT DISTINCT c.paciente_usuario_id FROM consultas c
                       WHERE c.profissional_usuario_id = %s"""
        params = [usuario["id"]]
        if estab_id:
            query += " AND c.estabelecimento_id = %s"
            params.append(estab_id)
        query += ") AND 1=1"
        if estab_id:
            query += " AND p.estabelecimento_id = %s"
            params.append(estab_id)
        if paciente_id_int:
            query += " AND p.paciente_usuario_id = %s"
            params.append(paciente_id_int)
        query += " ORDER BY p.criado_em DESC"
        prontuarios = db.fetch_all(query, tuple(params))
    elif usuario.get("is_super"):
        query = """SELECT p.*, u.nome AS paciente_nome,
                          u.cpf AS paciente_cpf, u.telefone AS paciente_telefone, u.email AS paciente_email
                   FROM prontuarios p
                   JOIN usuarios u ON u.id = p.paciente_usuario_id
                   WHERE 1=1"""
        params = []
        if paciente_id_int:
            query += " AND p.paciente_usuario_id = %s"
            params.append(paciente_id_int)
        query += " ORDER BY p.criado_em DESC"
        prontuarios = db.fetch_all(query, tuple(params))
    elif estab_id:
        query = """SELECT p.*, u.nome AS paciente_nome,
                          u.cpf AS paciente_cpf, u.telefone AS paciente_telefone, u.email AS paciente_email
                   FROM prontuarios p
                   JOIN usuarios u ON u.id = p.paciente_usuario_id
                   WHERE p.estabelecimento_id = %s"""
        params = [estab_id]
        if paciente_id_int:
            query += " AND p.paciente_usuario_id = %s"
            params.append(paciente_id_int)
        query += " ORDER BY p.criado_em DESC"
        prontuarios = db.fetch_all(query, tuple(params))
    else:
        prontuarios = []

    pacientes = []
    estabelecimentos_list = []
    if estab_id:
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome, u.email FROM usuarios u
               JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario["tipo"] == "admin":
        estabelecimentos_list = db.fetch_all(
            "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
        )

    return templates.TemplateResponse(
        "prontuarios/lista.html",
        {"request": request, "usuario": usuario, "prontuarios": prontuarios, "pacientes": pacientes,
         "estabelecimentos": estabelecimentos_list, "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int},
    )


@app.get("/prontuarios/{prontuario_id}", response_class=HTMLResponse)
def ver_prontuario(prontuario_id: int, request: Request, usuario=Depends(exigir_login), embedded: str = Query(None)):
    exigir_permissao(usuario, "prontuarios", "ver")
    prontuario = db.fetch_one(
        """SELECT p.*,
                  u.nome AS paciente_nome, u.email AS paciente_email, u.telefone AS paciente_telefone,
                  u.cpf AS paciente_cpf, u.data_nascimento AS paciente_nascimento,
                  u.logradouro AS paciente_logradouro, u.numero AS paciente_numero,
                  u.complemento AS paciente_complemento, u.bairro AS paciente_bairro,
                  u.cidade AS paciente_cidade, u.estado AS paciente_estado, u.cep AS paciente_cep,
                  u.estado_civil AS paciente_estado_civil, u.profissao AS paciente_profissao,
                  u.codigo_paciente AS paciente_codigo, u.numero_documentacao AS paciente_num_doc,
                  u.indicacao AS paciente_indicacao, u.nome_pai AS paciente_nome_pai,
                  u.nome_mae AS paciente_nome_mae
           FROM prontuarios p
           JOIN usuarios u ON u.id = p.paciente_usuario_id
           WHERE p.id = %s""",
        (prontuario_id,),
    )
    if not prontuario:
        raise HTTPException(status_code=404)

    verificar_acesso_registro(request, usuario, prontuario)

    evolucoes = db.fetch_all(
        """SELECT e.*, u.nome AS profissional_nome,
                  COALESCE(CAST(c.data_hora AS DATE), e.data) AS data_exibicao
           FROM evolucoes e
           JOIN usuarios u ON u.id = e.profissional_usuario_id
           LEFT JOIN consultas c ON c.id = e.consulta_id
           WHERE e.prontuario_id = %s
           ORDER BY COALESCE(c.data_hora, e.criado_em) DESC""",
        (prontuario_id,),
    )

    for ev in evolucoes:
        ev["tratamentos"] = db.fetch_all(
            "SELECT * FROM tratamentos WHERE evolucao_id = %s",
            (ev["id"],),
        )

    consultas = db.fetch_all(
        """SELECT c.*, u.nome AS profissional_nome, proc.nome AS procedimento_nome,
                  e.procedimento_realizado AS evolucao_procedimento
           FROM consultas c
           JOIN usuarios u ON u.id = c.profissional_usuario_id
           LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
           LEFT JOIN evolucoes e ON e.consulta_id = c.id
           WHERE c.prontuario_id = %s
           ORDER BY c.data_hora DESC""",
        (prontuario_id,),
    )

    imagens = db.fetch_all(
        "SELECT * FROM imaging WHERE prontuario_id = %s ORDER BY data DESC",
        (prontuario_id,),
    )

    profissionais = []
    estab_id = resolver_estabelecimento(request, usuario)
    if estab_id:
        profissionais = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE""",
            (estab_id,),
        )

    # Orcamentos do paciente neste estabelecimento (para vinculacao)
    paciente_user_id = prontuario["paciente_usuario_id"]
    estab_id_pront = prontuario["estabelecimento_id"]
    orcamentos_paciente = db.fetch_all(
        """SELECT o.id, o.status, o.valor_total, o.observacoes
           FROM orcamentos o
           WHERE o.paciente_usuario_id = %s AND o.estabelecimento_id = %s
             AND o.status IN ('rascunho','enviado','aprovado')
           ORDER BY o.criado_em DESC""",
        (paciente_user_id, estab_id_pront),
    )
    for orc in orcamentos_paciente:
        orc["itens"] = db.fetch_all(
            "SELECT * FROM orcamento_itens WHERE orcamento_id = %s",
            (orc["id"],),
        )

    # Tratamentos ja realizados com procedimento_id (para indicadores)
    evolucao_ids = [ev["id"] for ev in evolucoes]
    tratamentos_realizados = []
    if evolucao_ids:
        placeholders = ",".join(["%s"] * len(evolucao_ids))
        tratamentos_realizados = db.fetch_all(
            f"""SELECT t.*, e.prontuario_id
                FROM tratamentos t
                JOIN evolucoes e ON e.id = t.evolucao_id
                WHERE t.evolucao_id IN ({placeholders}) AND t.procedimento_id IS NOT NULL""",
            evolucao_ids,
        )

    # Procedimentos disponiveis para o select
    procedimentos = db.fetch_all(
        "SELECT id, nome FROM procedimentos WHERE ativo = TRUE ORDER BY nome"
    )

    # Contadores de realizacao por orcamento
    for orc in orcamentos_paciente:
        total_itens = len(orc["itens"])
        realizados = 0
        for item in orc["itens"]:
            if item["procedimento_id"] is not None:
                for t in tratamentos_realizados:
                    if t["procedimento_id"] == item["procedimento_id"]:
                        realizados += 1
                        break
        orc["total_itens"] = total_itens
        orc["realizados"] = realizados

    # Primeiro orcamento disponivel para adicionar item (rascunho ou aprovado)
    orcamento_disponivel_id = None
    for orc in orcamentos_paciente:
        if orc["status"] in ("rascunho", "aprovado"):
            orcamento_disponivel_id = orc["id"]
            break

    odontograma = db.fetch_all(
        """SELECT o.*, u.nome AS profissional_nome
           FROM odontograma o
           JOIN usuarios u ON u.id = o.profissional_usuario_id
           WHERE o.prontuario_id = %s
           ORDER BY o.data_registro DESC, o.dente, o.face""",
        (prontuario_id,),
    )

    return templates.TemplateResponse(
        "prontuarios/visualizar.html",
        {
            "request": request,
            "usuario": usuario,
            "prontuario": prontuario,
            "evolucoes": evolucoes,
            "consultas": consultas,
            "imagens": imagens,
            "alertas_farmaco": alertas_paciente(prontuario["paciente_usuario_id"]),
            "profissionais": profissionais,
            "orcamentos_paciente": orcamentos_paciente,
            "tratamentos_realizados": tratamentos_realizados,
            "procedimentos": procedimentos,
            "orcamento_disponivel_id": orcamento_disponivel_id,
            "odontograma": odontograma,
            "embedded": embedded in ("1", "True", "true"),
        },
    )


@app.post("/prontuarios/criar")
def criar_prontuario(
    request: Request,
    paciente_id: str = Form(""),
    numero: str = Form(None),
    estabelecimento_id: str = Form(None),
    criar_novo_paciente: str = Form("0"),
    novo_paciente_nome: str = Form(None),
    novo_paciente_email: str = Form(None),
    novo_paciente_senha: str = Form(None),
    novo_paciente_cpf: str = Form(None),
    novo_paciente_telefone: str = Form(None),
    novo_paciente_nascimento: str = Form(None),
    novo_paciente_tipo_pagamento: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if not estab_id or usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    if criar_novo_paciente == "1":
        if not novo_paciente_nome or not novo_paciente_email or not novo_paciente_senha:
            return RedirectResponse("/prontuarios?erro=Preencha nome, email e senha do paciente", status_code=302)
        novo_email = novo_paciente_email.strip().lower()
        existente = db.fetch_one("SELECT id FROM usuarios WHERE email = %s", (novo_email,))
        if existente:
            paciente_id_int = existente["id"]
        else:
            from utils.auth import criar_usuario
            paciente_id_int = criar_usuario(
                nome=novo_paciente_nome.strip(),
                email=novo_email,
                senha=novo_paciente_senha.strip(),
                tipo="paciente",
                telefone=novo_paciente_telefone or None,
            )
            if novo_paciente_cpf or novo_paciente_nascimento:
                db.execute(
                    "UPDATE usuarios SET cpf = %s, data_nascimento = %s WHERE id = %s",
                    (novo_paciente_cpf or None, novo_paciente_nascimento or None, paciente_id_int),
                )
            vincular_paciente(paciente_id_int, estab_id)

    if not paciente_id_int:
        return RedirectResponse("/prontuarios?erro=Selecione ou cadastre um paciente", status_code=302)

    try:
        bloquear_se_limite(estab_id, "prontuarios")
    except LimiteAtingidoError as e:
        return RedirectResponse(f"/prontuarios?erro_quota={e}", status_code=302)
    except Exception as e:
        logger.warning(f"criar_prontuario: erro ao verificar quota: {e}")

    existe_pront = db.fetch_one(
        "SELECT id, numero_prontuario FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
        (int(paciente_id_int), int(estab_id)),
    )
    if existe_pront:
        return RedirectResponse(
            f"/prontuarios?erro=Este paciente ja possui prontuario ({existe_pront['numero_prontuario']}) neste estabelecimento",
            status_code=302,
        )

    if not numero:
        numero = _proximo_numero_prontuario(int(estab_id))

    db.execute(
        "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
        (int(paciente_id_int), int(estab_id), numero),
    )
    resp = RedirectResponse("/prontuarios", status_code=302)
    cookie_kwargs = {"httponly": True, "samesite": "lax"}
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True
    resp.set_cookie("estabelecimento_id", str(estab_id), **cookie_kwargs)
    return resp


@app.post("/prontuarios/{prontuario_id}/evolucao")
def criar_evolucao(
    prontuario_id: int,
    request: Request,
    profissional_id: int = Form(...),
    queixa: str = Form(None),
    diagnostico: str = Form(None),
    procedimento: str = Form(None),
    observacoes: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "profissional"):
        raise HTTPException(status_code=403)

    if usuario["tipo"] == "profissional":
        profissional_id = usuario["id"]

    db.execute(
        """INSERT INTO evolucoes
           (prontuario_id, profissional_usuario_id, queixa_principal, diagnostico, procedimento_realizado, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (prontuario_id, profissional_id, queixa, diagnostico, procedimento, observacoes),
    )
    return RedirectResponse(f"/prontuarios/{prontuario_id}", status_code=302)


@app.post("/prontuarios/{prontuario_id}/evolucao/{evolucao_id}/tratamento")
def criar_tratamento(
    prontuario_id: int,
    evolucao_id: int,
    request: Request,
    tipo: str = Form(...),
    descricao: str = Form(None),
    dente: str = Form(None),
    face: str = Form(None),
    material: str = Form(None),
    valor: float = Form(None),
    procedimento_id: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "criar")
    if usuario["tipo"] not in ("admin", "profissional"):
        raise HTTPException(status_code=403)

    proc_id = int(procedimento_id) if procedimento_id and procedimento_id.strip() else None

    db.execute(
        """INSERT INTO tratamentos
           (evolucao_id, tipo, descricao, dente, face, material, valor, procedimento_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (evolucao_id, tipo, descricao, dente, face, material, valor, proc_id),
    )
    return RedirectResponse(f"/prontuarios/{prontuario_id}", status_code=302)


# ============================================
# ODONTOGRAMA - API
# ============================================

@app.get("/api/odontograma/{prontuario_id}")
def api_odontograma_listar(prontuario_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    prontuario = db.fetch_one("SELECT * FROM prontuarios WHERE id = %s", (prontuario_id,))
    if not prontuario:
        raise HTTPException(status_code=404)
    verificar_acesso_registro(request, usuario, prontuario)
    registros = db.fetch_all(
        """SELECT o.id, o.prontuario_id, o.dente, o.face, o.condicao, o.observacoes,
                  CAST(o.data_registro AS CHAR) AS data_registro,
                  o.profissional_usuario_id, CAST(o.criado_em AS CHAR) AS criado_em,
                  u.nome AS profissional_nome
           FROM odontograma o
           JOIN usuarios u ON u.id = o.profissional_usuario_id
           WHERE o.prontuario_id = %s
           ORDER BY o.data_registro DESC, o.dente, o.face""",
        (prontuario_id,),
    )
    return JSONResponse([dict(r) for r in registros])


@app.get("/api/odontograma/{prontuario_id}/historico")
def api_odontograma_historico(prontuario_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    prontuario = db.fetch_one("SELECT * FROM prontuarios WHERE id = %s", (prontuario_id,))
    if not prontuario:
        raise HTTPException(status_code=404)
    verificar_acesso_registro(request, usuario, prontuario)
    datas = db.fetch_all(
        """SELECT DISTINCT CAST(data_registro AS CHAR) AS data_registro
           FROM odontograma
           WHERE prontuario_id = %s
           ORDER BY data_registro ASC""",
        (prontuario_id,),
    )
    result = []
    for d in datas:
        dr = d["data_registro"]
        result.append({"data": dr if dr else ""})
    return JSONResponse(result)


@app.get("/api/odontograma/{prontuario_id}/estado")
def api_odontograma_estado(prontuario_id: int, request: Request, usuario=Depends(exigir_login), data: str = None):
    exigir_permissao(usuario, "prontuarios", "ver")
    prontuario = db.fetch_one("SELECT * FROM prontuarios WHERE id = %s", (prontuario_id,))
    if not prontuario:
        raise HTTPException(status_code=404)
    verificar_acesso_registro(request, usuario, prontuario)
    if data:
        registros = db.fetch_all(
            """SELECT o.id, o.prontuario_id, o.dente, o.face, o.condicao, o.observacoes,
                      CAST(o.data_registro AS CHAR) AS data_registro,
                      o.profissional_usuario_id, u.nome AS profissional_nome
               FROM odontograma o
               JOIN usuarios u ON u.id = o.profissional_usuario_id
               WHERE o.prontuario_id = %s AND o.data_registro <= %s
               ORDER BY o.data_registro ASC, o.dente, o.face""",
            (prontuario_id, data),
        )
    else:
        registros = db.fetch_all(
            """SELECT o.id, o.prontuario_id, o.dente, o.face, o.condicao, o.observacoes,
                      CAST(o.data_registro AS CHAR) AS data_registro,
                      o.profissional_usuario_id, u.nome AS profissional_nome
               FROM odontograma o
               JOIN usuarios u ON u.id = o.profissional_usuario_id
               WHERE o.prontuario_id = %s
               ORDER BY o.data_registro ASC, o.dente, o.face""",
            (prontuario_id,),
        )
    estado = {}
    for r in registros:
        dente = int(r["dente"])
        face = r["face"]
        key = f"{dente}_{face or 'geral'}"
        dr = r["data_registro"]
        estado[key] = {
            "dente": dente,
            "face": face,
            "condicao": r["condicao"],
            "observacoes": r["observacoes"],
            "data_registro": dr if dr else "",
            "profissional_nome": r["profissional_nome"],
            "id": r["id"],
        }
    return JSONResponse(list(estado.values()))


@app.post("/api/odontograma/{prontuario_id}")
def api_odontograma_criar(
    prontuario_id: int,
    request: Request,
    dente: int = Form(...),
    face: str = Form(None),
    condicao: str = Form(...),
    observacoes: str = Form(None),
    data_registro: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "criar")
    if usuario["tipo"] not in ("admin", "profissional"):
        raise HTTPException(status_code=403)
    prontuario = db.fetch_one("SELECT * FROM prontuarios WHERE id = %s", (prontuario_id,))
    if not prontuario:
        raise HTTPException(status_code=404)
    verificar_acesso_registro(request, usuario, prontuario)
    valid_faces = ["Mesial", "Distal", "Oclusal", "Incisal", "Vestibular", "Lingual", "Cervical", None, ""]
    if face and face not in valid_faces:
        raise HTTPException(status_code=400, detail="Face invalida")
    valid_condicoes = [
        "normal", "carie", "restauracao", "extracao", "coroa", "implante", "protese",
        "ausente", "fratura", "mancha", "desgaste", "mobilidade", "tratar", "observar",
        "encaminhar", "provisorio",
    ]
    if condicao not in valid_condicoes:
        raise HTTPException(status_code=400, detail="Condicao invalida")
    if face == "":
        face = None
    date_val = data_registro if data_registro else None
    if date_val:
        db.execute(
            """INSERT INTO odontograma
               (prontuario_id, dente, face, condicao, observacoes, data_registro, profissional_usuario_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (prontuario_id, dente, face, condicao, observacoes or None, date_val, usuario["id"]),
        )
    else:
        db.execute(
            """INSERT INTO odontograma
               (prontuario_id, dente, face, condicao, observacoes, profissional_usuario_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (prontuario_id, dente, face, condicao, observacoes or None, usuario["id"]),
        )
    return JSONResponse({"ok": True, "message": "Registro criado"})


@app.delete("/api/odontograma/{prontuario_id}/{registro_id}")
def api_odontograma_remover(
    prontuario_id: int,
    registro_id: int,
    request: Request,
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "excluir")
    if usuario["tipo"] not in ("admin", "profissional"):
        raise HTTPException(status_code=403)
    prontuario = db.fetch_one("SELECT * FROM prontuarios WHERE id = %s", (prontuario_id,))
    if not prontuario:
        raise HTTPException(status_code=404)
    verificar_acesso_registro(request, usuario, prontuario)
    existing = db.fetch_one(
        "SELECT id FROM odontograma WHERE id = %s AND prontuario_id = %s",
        (registro_id, prontuario_id),
    )
    if not existing:
        raise HTTPException(status_code=404)
    db.execute("DELETE FROM odontograma WHERE id = %s", (registro_id,))
    return JSONResponse({"ok": True, "message": "Registro removido"})


@app.get("/agenda", response_class=HTMLResponse)
def agenda_semanal(request: Request, usuario=Depends(exigir_login), data: str = None, profissional_id: str = Query(None)):
    estab_id = resolver_estabelecimento(request, usuario)
    exigir_permissao(usuario, "agenda", "ver", estab_id)
    profissional_id_int = int(profissional_id) if profissional_id and profissional_id.isdigit() else None

    if usuario["tipo"] == "profissional":
        profissionais_filtro = [{"id": usuario["id"], "nome": usuario["nome"]}]
        if not profissional_id_int:
            profissional_id_int = usuario["id"]
    elif usuario.get("is_super"):
        if estab_id:
            profissionais_filtro = db.fetch_all(
                """SELECT u.id, u.nome FROM usuarios u
                   JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
                   WHERE pe.estabelecimento_id = %s AND u.tipo = 'profissional' AND u.ativo = TRUE
                   ORDER BY u.nome""",
                (estab_id,),
            )
        else:
            profissionais_filtro = db.fetch_all(
                "SELECT id, nome FROM usuarios WHERE tipo = 'profissional' AND ativo = TRUE ORDER BY nome"
            )
    elif estab_id:
        profissionais_filtro = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.tipo = 'profissional' AND u.ativo = TRUE
               ORDER BY u.nome""",
            (estab_id,),
        )
    else:
        profissionais_filtro = []

    if data:
        try:
            data_inicio = datetime.strptime(data, "%Y-%m-%d")
            data_inicio -= timedelta(days=data_inicio.weekday())
        except ValueError:
            data_inicio = datetime.now() - timedelta(days=datetime.now().weekday())
    else:
        data_inicio = datetime.now() - timedelta(days=datetime.now().weekday())

    data_inicio = data_inicio.replace(hour=0, minute=0, second=0, microsecond=0)
    data_fim = data_inicio + timedelta(days=7)

    dias_semana = []
    for i in range(7):
        dia = data_inicio + timedelta(days=i)
        dias_semana.append({
            "data": dia,
            "dia_semana": dia.strftime("%A"),
            "dia_numero": dia.day,
            "mes": dia.strftime("%b"),
            "data_str": dia.strftime("%Y-%m-%d"),
            "eh_hoje": dia.date() == datetime.now().date(),
        })

    estabelecimentos = []
    if usuario["tipo"] == "admin" and not request.cookies.get("estabelecimento_id"):
        estabelecimentos = db.fetch_all(
            "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
        )

    return templates.TemplateResponse(
        "agenda/semanal.html",
        {
            "request": request,
            "usuario": usuario,
            "dias_semana": dias_semana,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "estabelecimentos": estabelecimentos,
            "estabelecimento_selecionado": estab_id,
            "profissionais_filtro": profissionais_filtro,
            "profissional_id": profissional_id_int,
        },
    )


@app.get("/api/consultas")
def api_consultas(
    request: Request,
    inicio: str = Query(...),
    fim: str = Query(...),
    estabelecimento_id: str = Query(None),
    paciente_id: str = Query(None),
    profissional_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    paciente_id_int_api = int(paciente_id) if paciente_id and paciente_id.isdigit() else None
    profissional_id_int_api = int(profissional_id) if profissional_id and profissional_id.isdigit() else None
    estab_id = estabelecimento_id or resolver_estabelecimento(request, usuario)

    if usuario["tipo"] == "paciente":
        consultas = db.fetch_all(
            """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome, COALESCE(pe.cor, '#6c757d') AS cor_profissional, proc.nome AS procedimento_nome
               FROM consultas c
               JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
               JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
               LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = c.profissional_usuario_id AND pe.estabelecimento_id = c.estabelecimento_id
               LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
               WHERE c.paciente_usuario_id = %s
               AND c.data_hora BETWEEN %s AND %s
               ORDER BY c.data_hora""",
            (usuario["id"], inicio, fim),
        )
    elif usuario["tipo"] == "profissional":
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome, COALESCE(pe.cor, '#6c757d') AS cor_profissional, proc.nome AS procedimento_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                   LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = c.profissional_usuario_id AND pe.estabelecimento_id = c.estabelecimento_id
                   LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
                   WHERE c.profissional_usuario_id = %s
                   AND c.data_hora BETWEEN %s AND %s"""
        params = [usuario["id"], inicio, fim]
        if estab_id:
            query += " AND c.estabelecimento_id = %s"
            params.append(estab_id)
        if profissional_id_int_api and profissional_id_int_api != usuario["id"]:
            query = query.replace("WHERE c.profissional_usuario_id = %s", "WHERE c.profissional_usuario_id = %s")
        query += " ORDER BY c.data_hora"
        consultas = db.fetch_all(query, tuple(params))
    elif estab_id:
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome, COALESCE(pe.cor, '#6c757d') AS cor_profissional, proc.nome AS procedimento_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                   LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = c.profissional_usuario_id AND pe.estabelecimento_id = c.estabelecimento_id
                   LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
                   WHERE c.estabelecimento_id = %s
                   AND c.data_hora BETWEEN %s AND %s"""
        params = [estab_id, inicio, fim]
        if profissional_id_int_api:
            query += " AND c.profissional_usuario_id = %s"
            params.append(profissional_id_int_api)
        if paciente_id_int_api:
            query += " AND c.paciente_usuario_id = %s"
            params.append(paciente_id_int_api)
        query += " ORDER BY c.data_hora"
        consultas = db.fetch_all(query, tuple(params))
    else:
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome, COALESCE(pe.cor, '#6c757d') AS cor_profissional, proc.nome AS procedimento_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
                   LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = c.profissional_usuario_id AND pe.estabelecimento_id = c.estabelecimento_id
                   LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
                   WHERE c.data_hora BETWEEN %s AND %s"""
        params = [inicio, fim]
        if profissional_id_int_api:
            query += " AND c.profissional_usuario_id = %s"
            params.append(profissional_id_int_api)
        if paciente_id_int_api:
            query += " AND c.paciente_usuario_id = %s"
            params.append(paciente_id_int_api)
        query += " ORDER BY c.data_hora"
        consultas = db.fetch_all(query, tuple(params))

    resultado = []
    for c in consultas:
        resultado.append({
            "id": c["id"],
            "titulo": f"{c['paciente_nome']} - {c['profissional_nome']}",
            "paciente": c["paciente_nome"],
            "profissional": c["profissional_nome"],
            "cor_profissional": c.get("cor_profissional") or "#6c757d",
            "procedimento": c.get("procedimento_nome") or "",
            "data_hora": c["data_hora"].strftime("%Y-%m-%dT%H:%M") if c["data_hora"] else None,
            "duracao": c["duracao_minutos"],
            "status": c["status"],
            "observacoes": c["observacoes"] or "",
            "horario_inicio": c["data_hora"].strftime("%H:%M") if c["data_hora"] else "",
            "horario_fim": (c["data_hora"] + timedelta(minutes=c["duracao_minutos"])).strftime("%H:%M") if c["data_hora"] else "",
        })

    return JSONResponse(content=resultado)


@app.get("/api/profissionais")
def api_profissionais(
    request: Request,
    estabelecimento_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    estab_id = estabelecimento_id or resolver_estabelecimento(request, usuario)
    if estab_id:
        profissionais = db.fetch_all(
            """SELECT u.id, u.nome, pe.especialidade, COALESCE(pe.cor, '#6c757d') as cor FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario.get("is_super"):
        profissionais = db.fetch_all(
            """SELECT u.id, u.nome, pe.especialidade, COALESCE(pe.cor, '#6c757d') as cor FROM usuarios u
               LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE u.tipo = 'profissional' AND u.ativo = TRUE ORDER BY u.nome"""
        )
    else:
        profissionais = []
    return JSONResponse(content=profissionais)


@app.get("/api/pacientes")
def api_pacientes(
    request: Request,
    estabelecimento_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    estab_id = estabelecimento_id or resolver_estabelecimento(request, usuario)
    if estab_id:
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario.get("is_super"):
        pacientes = db.fetch_all(
            "SELECT id, nome FROM usuarios WHERE tipo = 'paciente' AND ativo = TRUE ORDER BY nome"
        )
    else:
        pacientes = []
    return JSONResponse(content=pacientes)


@app.get("/convenios", response_class=HTMLResponse)
def listar_convenios(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "convenios", "ver")
    convenios = db.fetch_all("SELECT * FROM convenios ORDER BY nome")
    return templates.TemplateResponse(
        "convenios/lista.html",
        {"request": request, "usuario": usuario, "convenios": convenios},
    )


@app.get("/convenios/novo", response_class=HTMLResponse)
def novo_convenio(request: Request, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        "convenios/formulario.html",
        {"request": request, "usuario": usuario, "convenio": None},
    )


@app.post("/convenios/criar")
def criar_convenio(
    request: Request,
    nome: str = Form(...),
    cnpj: str = Form(None),
    telefone: str = Form(None),
    email: str = Form(None),
    plano_padrao: str = Form(None),
    limite_consultas_mes: int = Form(0),
    telefone_2: str = Form(None),
    contato_nome: str = Form(None),
    contato_email: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "convenios", "criar")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    db.execute(
        """INSERT INTO convenios (nome, cnpj, telefone, email, plano_padrao, limite_consultas_mes, telefone_2, contato_nome, contato_email)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (nome, cnpj, telefone, email, plano_padrao, limite_consultas_mes, telefone_2, contato_nome, contato_email),
    )
    return RedirectResponse("/convenios", status_code=302)


@app.get("/convenios/{conv_id}/editar", response_class=HTMLResponse)
def editar_convenio(conv_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "convenios", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    convenio = db.fetch_one("SELECT * FROM convenios WHERE id = %s", (conv_id,))
    if not convenio:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "convenios/formulario.html",
        {"request": request, "usuario": usuario, "convenio": convenio},
    )


@app.post("/convenios/{conv_id}/editar")
def salvar_convenio(
    conv_id: int,
    request: Request,
    nome: str = Form(...),
    cnpj: str = Form(None),
    telefone: str = Form(None),
    email: str = Form(None),
    plano_padrao: str = Form(None),
    limite_consultas_mes: int = Form(0),
    telefone_2: str = Form(None),
    contato_nome: str = Form(None),
    contato_email: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    db.execute(
        """UPDATE convenios SET nome = %s, cnpj = %s, telefone = %s, email = %s,
           plano_padrao = %s, limite_consultas_mes = %s, telefone_2 = %s,
           contato_nome = %s, contato_email = %s
           WHERE id = %s""",
        (nome, cnpj, telefone, email, plano_padrao, limite_consultas_mes, telefone_2, contato_nome, contato_email, conv_id),
    )
    return RedirectResponse("/convenios", status_code=302)


@app.post("/convenios/{conv_id}/desativar")
def desativar_convenio(conv_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    db.execute("UPDATE convenios SET ativo = FALSE WHERE id = %s", (conv_id,))
    return RedirectResponse("/convenios", status_code=302)


@app.get("/procedimentos", response_class=HTMLResponse)
def listar_procedimentos(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "procedimentos", "ver")
    procedimentos = db.fetch_all("SELECT * FROM procedimentos ORDER BY nome")
    return templates.TemplateResponse(
        "procedimentos/lista.html",
        {"request": request, "usuario": usuario, "procedimentos": procedimentos},
    )


@app.get("/procedimentos/novo", response_class=HTMLResponse)
def novo_procedimento(request: Request, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        "procedimentos/formulario.html",
        {"request": request, "usuario": usuario, "procedimento": None},
    )


@app.post("/procedimentos/criar")
def criar_procedimento(
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(None),
    duracao_minutos: int = Form(30),
    categoria: str = Form(None),
    codigo_tuss: str = Form(None),
    codigo_americano: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "procedimentos", "criar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    db.execute(
        """INSERT INTO procedimentos (nome, descricao, duracao_minutos, categoria, codigo_tuss, codigo_americano)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (nome, descricao, duracao_minutos, categoria or None, codigo_tuss or None, codigo_americano or None),
    )
    return RedirectResponse("/procedimentos", status_code=302)


@app.get("/procedimentos/{proc_id}/editar", response_class=HTMLResponse)
def editar_procedimento(proc_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "procedimentos", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    procedimento = db.fetch_one("SELECT * FROM procedimentos WHERE id = %s", (proc_id,))
    if not procedimento:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "procedimentos/formulario.html",
        {"request": request, "usuario": usuario, "procedimento": procedimento},
    )


@app.post("/procedimentos/{proc_id}/editar")
def salvar_procedimento(
    proc_id: int,
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(None),
    duracao_minutos: int = Form(30),
    categoria: str = Form(None),
    codigo_tuss: str = Form(None),
    codigo_americano: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    db.execute(
        """UPDATE procedimentos SET nome = %s, descricao = %s, duracao_minutos = %s,
           categoria = %s, codigo_tuss = %s, codigo_americano = %s WHERE id = %s""",
        (nome, descricao, duracao_minutos, categoria or None, codigo_tuss or None, codigo_americano or None, proc_id),
    )
    return RedirectResponse("/procedimentos", status_code=302)


@app.post("/procedimentos/{proc_id}/desativar")
def desativar_procedimento(proc_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    db.execute("UPDATE procedimentos SET ativo = FALSE WHERE id = %s", (proc_id,))
    return RedirectResponse("/procedimentos", status_code=302)


@app.get("/procedimentos/{proc_id}/valores", response_class=HTMLResponse)
def valores_procedimento(proc_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "procedimentos", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario)
    procedimento = db.fetch_one("SELECT * FROM procedimentos WHERE id = %s", (proc_id,))
    if not procedimento:
        raise HTTPException(status_code=404)

    convenios = db.fetch_all("SELECT id, nome FROM convenios WHERE ativo = TRUE ORDER BY nome")

    valores_existentes = db.fetch_all(
        """SELECT pv.*, c.nome AS convenio_nome
           FROM procedimento_valor pv
           LEFT JOIN convenios c ON c.id = pv.convenio_id
           WHERE pv.procedimento_id = %s AND pv.estabelecimento_id = %s""",
        (proc_id, estab_id),
    )

    return templates.TemplateResponse(
        "procedimentos/valores.html",
        {
            "request": request,
            "usuario": usuario,
            "procedimento": procedimento,
            "convenios": convenios,
            "valores": valores_existentes,
            "estabelecimento_id": estab_id,
        },
    )


@app.post("/procedimentos/{proc_id}/valores/salvar")
async def salvar_valores_procedimento(
    proc_id: int,
    request: Request,
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario)
    form = await request.form()

    db.execute(
        "DELETE FROM procedimento_valor WHERE procedimento_id = %s AND estabelecimento_id = %s",
        (proc_id, estab_id),
    )

    for key, value in form.items():
        if key.startswith("valor_") and value:
            convenio_id = key.replace("valor_", "")
            convenio_id = convenio_id if convenio_id != "particular" else None
            try:
                valor_num = float(value)
                db.execute(
                    """INSERT INTO procedimento_valor (procedimento_id, convenio_id, estabelecimento_id, valor)
                       VALUES (%s, %s, %s, %s)""",
                    (proc_id, convenio_id, estab_id, valor_num),
                )
            except (ValueError, TypeError):
                pass

    return RedirectResponse(f"/procedimentos/{proc_id}/valores", status_code=302)


@app.get("/api/procedimentos")
def api_procedimentos(
    request: Request,
    estabelecimento_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    procedimentos = db.fetch_all(
        "SELECT id, nome, duracao_minutos FROM procedimentos WHERE ativo = TRUE ORDER BY nome"
    )
    return JSONResponse(content=procedimentos)


@app.get("/api/procedimento-valor")
def api_procedimento_valor(
    request: Request,
    procedimento_id: int = Query(...),
    convenio_id: str = Query(None),
    estabelecimento_id: str = Query(None),
    usuario=Depends(exigir_login),
):
    estab_id = estabelecimento_id or resolver_estabelecimento(request, usuario)
    if not estab_id:
        return JSONResponse(content={"valor": None})

    if convenio_id and convenio_id != "null":
        resultado = db.fetch_one(
            """SELECT valor FROM procedimento_valor
               WHERE procedimento_id = %s AND convenio_id = %s AND estabelecimento_id = %s""",
            (procedimento_id, convenio_id, estab_id),
        )
    else:
        resultado = db.fetch_one(
            """SELECT valor FROM procedimento_valor
               WHERE procedimento_id = %s AND convenio_id IS NULL AND estabelecimento_id = %s""",
            (procedimento_id, estab_id),
        )

    return JSONResponse(content={"valor": float(resultado["valor"]) if resultado else None})


@app.get("/api/cep/{cep}")
def api_buscar_cep(cep: str):
    import re
    cep_limpo = re.sub(r'\D', '', cep)
    if len(cep_limpo) != 8:
        return JSONResponse(status_code=400, content={"erro": "CEP invalido"})
    try:
        import urllib.request
        import json
        url = f"https://brasilapi.com.br/api/cep/v2/{cep_limpo}"
        req = urllib.request.Request(url, headers={"User-Agent": "SISGERSA/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return JSONResponse(content={
            "cep": data.get("cep", ""),
            "logradouro": data.get("street", ""),
            "bairro": data.get("neighborhood", ""),
            "cidade": data.get("city", ""),
            "estado": data.get("state", ""),
        })
    except Exception as e:
        return JSONResponse(status_code=404, content={"erro": f"CEP nao encontrado: {e}"})


@app.get("/api/convenios-paciente")
def api_convenios_paciente(
    request: Request,
    paciente_id: int = Query(...),
    usuario=Depends(exigir_login),
):
    convenios = db.fetch_all(
        """SELECT c.id, c.nome, pc.numero_carteirinha
           FROM paciente_convenio pc
           JOIN convenios c ON c.id = pc.convenio_id
           WHERE pc.paciente_usuario_id = %s AND pc.ativo = TRUE""",
        (paciente_id,),
    )
    return JSONResponse(content=convenios)


@app.get("/pacientes/{pac_id}/convenio", response_class=HTMLResponse)
def paciente_convenio_page(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "convenios", "ver")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    pac = db.fetch_one("SELECT * FROM usuarios WHERE id = %s AND tipo = 'paciente'", (pac_id,))
    if not pac:
        raise HTTPException(status_code=404)

    convenios = db.fetch_all("SELECT id, nome FROM convenios WHERE ativo = TRUE ORDER BY nome")

    vinculos = db.fetch_all(
        """SELECT pc.*, c.nome AS convenio_nome
           FROM paciente_convenio pc
           JOIN convenios c ON c.id = pc.convenio_id
           WHERE pc.paciente_usuario_id = %s""",
        (pac_id,),
    )

    return templates.TemplateResponse(
        "pacientes/convenio.html",
        {"request": request, "usuario": usuario, "pac": pac, "convenios": convenios, "vinculos": vinculos},
    )


@app.post("/pacientes/{pac_id}/convenio/salvar")
def salvar_paciente_convenio(
    pac_id: int,
    request: Request,
    convenio_id: str = Form(""),
    numero_carteirinha: str = Form(None),
    validade: str = Form(None),
    usuario=Depends(exigir_login),
):
    convenio_id = int(convenio_id) if convenio_id and convenio_id.strip() else None
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    if convenio_id:
        db.execute(
            """INSERT INTO paciente_convenio (paciente_usuario_id, convenio_id, numero_carteirinha, validade)
               VALUES (%s, %s, %s, %s)""",
            (pac_id, convenio_id, numero_carteirinha, validade if validade else None),
        )

    return RedirectResponse(f"/pacientes/{pac_id}/convenio", status_code=302)


@app.post("/pacientes/{pac_id}/convenio/{vc_id}/remover")
def remover_paciente_convenio(pac_id: int, vc_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    db.execute("DELETE FROM paciente_convenio WHERE id = %s", (vc_id,))
    return RedirectResponse(f"/pacientes/{pac_id}/convenio", status_code=302)


@app.get("/orcamentos", response_class=HTMLResponse)
def listar_orcamentos(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None), embedded: str = Query(None)):
    try:
        estab_id = resolver_estabelecimento(request, usuario)
        exigir_permissao(usuario, "orcamentos", "ver", estab_id)
        pacientes_filtro = obter_pacientes_para_filtro(usuario, estab_id)
        paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

        if usuario["tipo"] == "paciente":
            orcamentos = db.fetch_all(
                """SELECT o.*, u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                          u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                   FROM orcamentos o
                   JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
                   JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
                   WHERE o.paciente_usuario_id = %s
                   ORDER BY o.criado_em DESC""",
                (usuario["id"],),
            )
        elif usuario["tipo"] == "profissional":
            query = """SELECT o.*, u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                              u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                       FROM orcamentos o
                       JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
                       JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
                       WHERE o.profissional_usuario_id = %s"""
            params = [usuario["id"]]
            if estab_id:
                query += " AND o.estabelecimento_id = %s"
                params.append(estab_id)
            if paciente_id_int:
                query += " AND o.paciente_usuario_id = %s"
                params.append(paciente_id_int)
            query += " ORDER BY o.criado_em DESC"
            orcamentos = db.fetch_all(query, tuple(params))
        elif estab_id:
            query = """SELECT o.*, u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                              u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                       FROM orcamentos o
                       JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
                       JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
                       WHERE o.estabelecimento_id = %s"""
            params = [estab_id]
            if paciente_id_int:
                query += " AND o.paciente_usuario_id = %s"
                params.append(paciente_id_int)
            query += " ORDER BY o.criado_em DESC"
            orcamentos = db.fetch_all(query, tuple(params))
        else:
            if usuario.get("is_super"):
                query = """SELECT o.*, u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                                  u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                           FROM orcamentos o
                           JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
                           JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
                           WHERE 1=1"""
                params = []
                if paciente_id_int:
                    query += " AND o.paciente_usuario_id = %s"
                    params.append(paciente_id_int)
                query += " ORDER BY o.criado_em DESC"
                orcamentos = db.fetch_all(query, tuple(params))
            else:
                orcamentos = []

        for o in orcamentos:
            itens = db.fetch_all(
                "SELECT descricao, quantidade, valor_unitario, subtotal FROM orcamento_itens WHERE orcamento_id = %s ORDER BY id",
                (o["id"],),
            )
            o["_itens_resumo"] = ", ".join(
                f"{i['descricao']} ({i['quantidade']}x R$ {float(i['valor_unitario']):.2f})"
                for i in itens[:4]
            )
            o["_total_pago"] = db.fetch_one(
                "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'",
                (o["id"],),
            )["total"]

        return templates.TemplateResponse(
            "orcamentos/lista.html",
             {"request": request, "usuario": usuario, "orcamentos": orcamentos,
             "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int,
             "embedded": embedded in ("1", "True", "true")},
        )
    except Exception as e:
        import traceback
        logger.error(f"Erro listar_orcamentos: {e}\n{traceback.format_exc()}")
        return templates.TemplateResponse(
            "orcamentos/lista.html",
            {"request": request, "usuario": usuario, "orcamentos": [],
             "pacientes_filtro": [], "paciente_id": None, "embedded": False},
        )


@app.get("/orcamentos/novo", response_class=HTMLResponse)
def novo_orcamento(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
    estab_id = resolver_estabelecimento(request, usuario)
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    pacientes = []
    profissionais = []
    convenios = db.fetch_all("SELECT id, nome FROM convenios WHERE ativo = TRUE ORDER BY nome")
    paciente_selecionado = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    if estab_id:
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
        profissionais = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )

    return templates.TemplateResponse(
        "orcamentos/formulario.html",
        {
            "request": request, "usuario": usuario, "orcamento": None,
            "pacientes": pacientes, "profissionais": profissionais,
            "convenios": convenios, "estabelecimento_id": estab_id,
            "paciente_selecionado": paciente_selecionado,
        },
    )


@app.post("/orcamentos/criar")
def criar_orcamento(
    request: Request,
    paciente_id: int = Form(...),
    profissional_id: int = Form(...),
    convenio_id: str = Form(None),
    data_validade: str = Form(None),
    observacoes: str = Form(None),
    estabelecimento_id: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "orcamentos", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if not estab_id or usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    try:
        bloquear_se_limite(estab_id, "orcamentos_mes")
    except LimiteAtingidoError as e:
        return RedirectResponse(f"/orcamentos?erro_quota={e}", status_code=302)

    conv_id = int(convenio_id) if convenio_id and convenio_id.strip() else None
    dv = data_validade if data_validade and data_validade.strip() else None

    if settings.DB_ENGINE == "postgresql":
        cursor = db.execute(
            """INSERT INTO orcamentos
               (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, convenio_id, data_validade, observacoes)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (paciente_id, profissional_id, estab_id, conv_id, dv, observacoes),
        )
        row = cursor.fetchone()
        new_id = row["id"] if row else None
    else:
        cursor = db.execute(
            """INSERT INTO orcamentos
               (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, convenio_id, data_validade, observacoes)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (paciente_id, profissional_id, estab_id, conv_id, dv, observacoes),
        )
        new_id = cursor.lastrowid
    return RedirectResponse(f"/orcamentos/{new_id}", status_code=302)


@app.get("/orcamentos/{orc_id}", response_class=HTMLResponse)
def ver_orcamento(orc_id: int, request: Request, usuario=Depends(exigir_login), embedded: str = Query(None)):
    exigir_permissao(usuario, "orcamentos", "ver")
    orcamento = db.fetch_one(
        """SELECT o.*, u_pac.nome AS paciente_nome, u_pac.email AS paciente_email,
                  u_prof.nome AS profissional_nome, e.nome AS estabelecimento_nome,
                  e.telefone AS estab_telefone, e.email AS estab_email, e.endereco AS estab_endereco,
                  c.nome AS convenio_nome
           FROM orcamentos o
           JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
           JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
           JOIN estabelecimentos e ON e.id = o.estabelecimento_id
           LEFT JOIN convenios c ON c.id = o.convenio_id
           WHERE o.id = %s""",
        (orc_id,),
    )
    if not orcamento:
        raise HTTPException(status_code=404)

    verificar_acesso_registro(request, usuario, orcamento)

    itens = db.fetch_all(
        """SELECT oi.*, p.nome AS procedimento_nome, p.duracao_minutos
           FROM orcamento_itens oi
           LEFT JOIN procedimentos p ON p.id = oi.procedimento_id
           WHERE oi.orcamento_id = %s
           ORDER BY oi.id""",
        (orc_id,),
    )

    procedimentos = db.fetch_all(
        "SELECT id, nome, duracao_minutos FROM procedimentos WHERE ativo = TRUE ORDER BY nome"
    )

    # Tratamentos realizados com procedimento_id para indicadores
    prontuario_row = db.fetch_one(
        "SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
        (orcamento["paciente_usuario_id"], orcamento["estabelecimento_id"]),
    )
    tratamentos_realizados = []
    if prontuario_row:
        evolucoes_ids_rows = db.fetch_all(
            "SELECT id FROM evolucoes WHERE prontuario_id = %s",
            (prontuario_row["id"],),
        )
        ev_ids = [r["id"] for r in evolucoes_ids_rows]
        if ev_ids:
            placeholders = ",".join(["%s"] * len(ev_ids))
            tratamentos_realizados = db.fetch_all(
                f"SELECT procedimento_id FROM tratamentos WHERE evolucao_id IN ({placeholders}) AND procedimento_id IS NOT NULL",
                ev_ids,
            )

    pagamentos = db.fetch_all(
        "SELECT * FROM pagamentos WHERE orcamento_id = %s ORDER BY criado_em DESC",
        (orc_id,),
    )
    total_pago = db.fetch_one(
        "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'",
        (orc_id,),
    )
    saldo = float(orcamento["valor_total"] or 0) - float(total_pago["total"])

    return templates.TemplateResponse(
        "orcamentos/visualizar.html",
        {
            "request": request, "usuario": usuario,
            "orcamento": orcamento, "itens": itens,
            "procedimentos": procedimentos,
            "tratamentos_realizados": tratamentos_realizados,
            "embedded": embedded in ("1", "True", "true"),
            "total_pago": float(total_pago["total"]),
            "saldo": saldo,
            "pagamentos": pagamentos,
            "status_class": {
                "rascunho": "secondary",
                "enviado": "primary",
                "aprovado": "success",
                "rejeitado": "danger",
                "pago": "success",
                "pago_parcial": "warning",
                "cancelado": "danger",
            },
        },
    )


@app.post("/orcamentos/{orc_id}/item/adicionar")
def adicionar_item_orcamento(
    orc_id: int,
    request: Request,
    procedimento_id: str = Form(None),
    descricao: str = Form(None),
    quantidade: int = Form(1),
    valor_unitario: float = Form(0),
    desconto: float = Form(0),
    usuario=Depends(exigir_login),
):
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    proc_id = int(procedimento_id) if procedimento_id and procedimento_id.strip() else None

    if not descricao and proc_id:
        proc = db.fetch_one("SELECT nome FROM procedimentos WHERE id = %s", (proc_id,))
        descricao = proc["nome"] if proc else ""

    subtotal = (valor_unitario * quantidade) - desconto
    if subtotal < 0:
        subtotal = 0

    db.execute(
        """INSERT INTO orcamento_itens
           (orcamento_id, procedimento_id, descricao, quantidade, valor_unitario, desconto, subtotal)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (orc_id, proc_id, descricao, quantidade, valor_unitario, desconto, subtotal),
    )

    total = db.fetch_one("SELECT COALESCE(SUM(subtotal), 0) AS total FROM orcamento_itens WHERE orcamento_id = %s", (orc_id,))
    db.execute("UPDATE orcamentos SET valor_total = %s WHERE id = %s", (total["total"], orc_id))

    return RedirectResponse(f"/orcamentos/{orc_id}", status_code=302)


@app.post("/orcamentos/{orc_id}/item/{item_id}/remover")
def remover_item_orcamento(orc_id: int, item_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    db.execute("DELETE FROM orcamento_itens WHERE id = %s AND orcamento_id = %s", (item_id, orc_id))

    total = db.fetch_one("SELECT COALESCE(SUM(subtotal), 0) AS total FROM orcamento_itens WHERE orcamento_id = %s", (orc_id,))
    db.execute("UPDATE orcamentos SET valor_total = %s WHERE id = %s", (total["total"], orc_id))

    return RedirectResponse(f"/orcamentos/{orc_id}", status_code=302)


@app.post("/orcamentos/{orc_id}/desconto")
def atualizar_desconto_orcamento(orc_id: int, desconto: float = Form(0), usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "orcamentos", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    db.execute("UPDATE orcamentos SET desconto = %s WHERE id = %s", (desconto, orc_id))
    return RedirectResponse(f"/orcamentos/{orc_id}", status_code=302)


@app.post("/orcamentos/{orc_id}/status")
def atualizar_status_orcamento(
    orc_id: int,
    request: Request,
    status: str = Form(...),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "orcamentos", "editar")
    if is_write_limited(request, usuario, "status"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super"):
        orc = db.fetch_one("SELECT * FROM orcamentos WHERE id = %s", (orc_id,))
        if not orc or orc["profissional_usuario_id"] != usuario["id"]:
            raise HTTPException(status_code=403)

    db.execute("UPDATE orcamentos SET status = %s WHERE id = %s", (status, orc_id))
    return RedirectResponse(f"/orcamentos/{orc_id}", status_code=302)


@app.post("/orcamentos/{orc_id}/converter")
def converter_orcamento_em_consulta(
    orc_id: int,
    request: Request,
    data_hora: str = Form(...),
    duracao: int = Form(30),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    orcamento = db.fetch_one("SELECT * FROM orcamentos WHERE id = %s", (orc_id,))
    if not orcamento:
        raise HTTPException(status_code=404)

    if usuario["tipo"] == "profissional" and not usuario.get("is_super") and orcamento["profissional_usuario_id"] != usuario["id"]:
        raise HTTPException(status_code=403)

    try:
        bloquear_se_limite(orcamento["estabelecimento_id"], "consultas_mes")
    except LimiteAtingidoError as e:
        return RedirectResponse(f"/orcamentos/{orc_id}?erro_quota={e}", status_code=302)

    prontuario = db.fetch_one(
        "SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
        (orcamento["paciente_usuario_id"], orcamento["estabelecimento_id"]),
    )

    db.execute(
        """INSERT INTO consultas
           (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, prontuario_id, data_hora, duracao_minutos, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            orcamento["paciente_usuario_id"],
            orcamento["profissional_usuario_id"],
            orcamento["estabelecimento_id"],
            prontuario["id"] if prontuario else None,
            data_hora,
            duracao,
            f"Gerado a partir do orcamento #{orc_id}",
        ),
    )

    db.execute("UPDATE orcamentos SET status = 'aprovado' WHERE id = %s", (orc_id,))

    return RedirectResponse("/consultas", status_code=302)


@app.get("/orcamentos/{orc_id}/imprimir", response_class=HTMLResponse)
def imprimir_orcamento(orc_id: int, request: Request, usuario=Depends(exigir_login)):
    orcamento = db.fetch_one(
        """SELECT o.*, u_pac.nome AS paciente_nome, u_pac.email AS paciente_email, u_pac.telefone AS paciente_telefone,
                  u_prof.nome AS profissional_nome, e.nome AS estabelecimento_nome,
                  e.telefone AS estab_telefone, e.email AS estab_email, e.endereco AS estab_endereco, e.cnpj AS estab_cnpj,
                  c.nome AS convenio_nome
           FROM orcamentos o
           JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
           JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
           JOIN estabelecimentos e ON e.id = o.estabelecimento_id
           LEFT JOIN convenios c ON c.id = o.convenio_id
           WHERE o.id = %s""",
        (orc_id,),
    )
    if not orcamento:
        raise HTTPException(status_code=404)

    verificar_acesso_registro(request, usuario, orcamento)

    itens = db.fetch_all(
        """SELECT oi.*, p.nome AS procedimento_nome
           FROM orcamento_itens oi
           LEFT JOIN procedimentos p ON p.id = oi.procedimento_id
           WHERE oi.orcamento_id = %s
           ORDER BY oi.id""",
        (orc_id,),
    )

    return templates.TemplateResponse(
        "orcamentos/imprimir.html",
        {"request": request, "usuario": usuario, "orcamento": orcamento, "itens": itens},
    )


@app.get("/orcamentos/{orc_id}/pagar", response_class=HTMLResponse)
def pagar_orcamento(orc_id: int, request: Request, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    orcamento = db.fetch_one(
        """SELECT o.*, u_pac.nome AS paciente_nome, e.nome AS estabelecimento_nome
           FROM orcamentos o
           JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
           JOIN estabelecimentos e ON e.id = o.estabelecimento_id
           WHERE o.id = %s""",
        (orc_id,),
    )
    if not orcamento:
        raise HTTPException(status_code=404)

    estab_id_check = request.cookies.get("estabelecimento_id")
    if usuario["tipo"] != "admin" and not usuario.get("is_super"):
        if estab_id_check and str(orcamento["estabelecimento_id"]) != str(estab_id_check):
            raise HTTPException(status_code=403)

    pagamentos = db.fetch_all(
        "SELECT * FROM pagamentos WHERE orcamento_id = %s ORDER BY criado_em DESC",
        (orc_id,),
    )

    total_pago = db.fetch_one(
        "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'",
        (orc_id,),
    )
    saldo = float(orcamento["valor_total"]) - float(total_pago["total"])

    return templates.TemplateResponse(
        "orcamentos/pagar.html",
        {"request": request, "usuario": usuario, "orcamento": orcamento, "pagamentos": pagamentos, "total_pago": float(total_pago["total"]), "saldo": saldo},
    )


@app.post("/orcamentos/{orc_id}/pagar")
def registrar_pagamento(
    orc_id: int,
    request: Request,
    valor: float = Form(...),
    metodo: str = Form(...),
    parcelas: int = Form(1),
    data_pagamento: str = Form(None),
    data_vencimento: str = Form(None),
    observacao: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    orcamento = db.fetch_one("SELECT * FROM orcamentos WHERE id = %s", (orc_id,))
    if not orcamento:
        raise HTTPException(status_code=404)

    valor_parcela = round(valor / parcelas, 2)

    if parcelas > 1 and not data_vencimento:
        data_vencimento = datetime.now().strftime("%Y-%m-%d")

    db.execute(
        """INSERT INTO pagamentos (orcamento_id, valor, metodo, parcelas, valor_parcela, data_pagamento, data_vencimento, observacao, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pago')""",
        (orc_id, valor, metodo, parcelas, valor_parcela, data_pagamento or datetime.now().strftime("%Y-%m-%d"), data_vencimento, observacao),
    )

    total_pago = db.fetch_one(
        "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'",
        (orc_id,),
    )

    if float(total_pago["total"]) >= float(orcamento["valor_total"]):
        db.execute("UPDATE orcamentos SET status = 'pago' WHERE id = %s", (orc_id,))
    elif float(total_pago["total"]) > 0:
        db.execute("UPDATE orcamentos SET status = 'pago_parcial' WHERE id = %s", (orc_id,))

    return RedirectResponse(f"/orcamentos/{orc_id}/pagar", status_code=302)


@app.post("/orcamentos/{orc_id}/pagamento/{pag_id}/cancelar")
def cancelar_pagamento(orc_id: int, pag_id: int, request: Request, usuario=Depends(exigir_login)):
    if is_write_limited(request, usuario, "delete"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista") and not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    db.execute("UPDATE pagamentos SET status = 'cancelado' WHERE id = %s AND orcamento_id = %s", (pag_id, orc_id))

    total_pago = db.fetch_one(
        "SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'",
        (orc_id,),
    )
    orcamento = db.fetch_one("SELECT valor_total, status FROM orcamentos WHERE id = %s", (orc_id,))

    if float(total_pago["total"]) >= float(orcamento["valor_total"]):
        db.execute("UPDATE orcamentos SET status = 'pago' WHERE id = %s", (orc_id,))
    elif float(total_pago["total"]) > 0:
        db.execute("UPDATE orcamentos SET status = 'pago_parcial' WHERE id = %s", (orc_id,))
    else:
        db.execute("UPDATE orcamentos SET status = 'aprovado' WHERE id = %s", (orc_id,))

    return RedirectResponse(f"/orcamentos/{orc_id}/pagar", status_code=302)


@app.get("/orcamentos/{orc_id}/nota-fiscal", response_class=HTMLResponse)
def nota_fiscal(orc_id: int, request: Request, usuario=Depends(exigir_login), valor: float = Query(None)):
    orcamento = db.fetch_one(
        """SELECT o.*, u_pac.nome AS paciente_nome, u_pac.email AS paciente_email, u_pac.telefone AS paciente_telefone,
                  u_prof.nome AS profissional_nome, e.nome AS estabelecimento_nome,
                  e.telefone AS estab_telefone, e.email AS estab_email, e.endereco AS estab_endereco, e.cnpj AS estab_cnpj,
                  c.nome AS convenio_nome
           FROM orcamentos o
           JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
           JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
           JOIN estabelecimentos e ON e.id = o.estabelecimento_id
           LEFT JOIN convenios c ON c.id = o.convenio_id
           WHERE o.id = %s""",
        (orc_id,),
    )
    if not orcamento:
        raise HTTPException(status_code=404)

    verificar_acesso_registro(request, usuario, orcamento)

    itens = db.fetch_all(
        """SELECT oi.*, p.nome AS procedimento_nome
           FROM orcamento_itens oi
           LEFT JOIN procedimentos p ON p.id = oi.procedimento_id
           WHERE oi.orcamento_id = %s ORDER BY oi.id""",
        (orc_id,),
    )

    pagamentos = db.fetch_all(
        "SELECT * FROM pagamentos WHERE orcamento_id = %s AND status = 'pago' ORDER BY data_pagamento",
        (orc_id,),
    )

    total_pago = sum(float(p["valor"]) for p in pagamentos)
    valor_nota = valor if valor is not None and valor > 0 else float(orcamento["valor_total"] or 0) - float(orcamento["desconto"] or 0)

    return templates.TemplateResponse(
        "orcamentos/nota_fiscal.html",
        {"request": request, "usuario": usuario, "orcamento": orcamento, "itens": itens, "pagamentos": pagamentos, "total_pago": total_pago, "valor_nota": valor_nota},
    )


@app.get("/financeiro", response_class=HTMLResponse)
def relatorio_financeiro(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None), embedded: str = Query(None)):
    exigir_permissao(usuario, "financeiro", "ver")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario)
    pacientes_filtro = obter_pacientes_para_filtro(usuario, estab_id)
    paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    periodo = request.query_params.get("periodo", "mes")
    hoje = datetime.now()

    if periodo == "hoje":
        ini = hoje.strftime("%Y-%m-%d")
        fim = hoje.strftime("%Y-%m-%d") + " 23:59:59"
    elif periodo == "semana":
        seg = hoje - timedelta(days=hoje.weekday())
        ini = seg.strftime("%Y-%m-%d")
        fim = (seg + timedelta(days=6)).strftime("%Y-%m-%d") + " 23:59:59"
    elif periodo == "ano":
        ini = hoje.strftime("%Y-01-01")
        fim = hoje.strftime("%Y-12-31") + " 23:59:59"
    else:
        ini = hoje.strftime("%Y-%m-01")
        fim = hoje.strftime("%Y-%m-31") + " 23:59:59"

    estab_filter = ""
    estab_params = []
    if estab_id:
        estab_filter = " AND o.estabelecimento_id = %s"
        estab_params = [estab_id]
    elif usuario["tipo"] == "profissional":
        estab_filter = " AND o.profissional_usuario_id = %s"
        estab_params = [usuario["id"]]

    pac_filter = ""
    pac_params = []
    if paciente_id_int:
        pac_filter = " AND o.paciente_usuario_id = %s"
        pac_params = [paciente_id_int]

    query_pag = f"""SELECT p.*, o.id AS orc_id, u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                          u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
                   FROM pagamentos p
                   JOIN orcamentos o ON o.id = p.orcamento_id
                   JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
                   JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
                   WHERE p.status = 'pago' AND p.data_pagamento BETWEEN %s AND %s{estab_filter}{pac_filter}"""
    params_pag = [ini, fim] + estab_params + pac_params

    pagamentos = db.fetch_all(query_pag + " ORDER BY p.data_pagamento DESC", tuple(params_pag))

    resumo_pag = db.fetch_one(
        f"""SELECT COUNT(*) AS qtd, COALESCE(SUM(p.valor), 0) AS total
            FROM pagamentos p JOIN orcamentos o ON o.id = p.orcamento_id
            WHERE p.status = 'pago' AND p.data_pagamento BETWEEN %s AND %s{estab_filter}{pac_filter}""",
        tuple([ini, fim] + estab_params + pac_params),
    )
    resumo = {"qtd": resumo_pag["qtd"] if resumo_pag else 0, "total": float(resumo_pag["total"]) if resumo_pag else 0}

    por_metodo = db.fetch_all(
        f"""SELECT p.metodo, COUNT(*) AS qtd, SUM(p.valor) AS total
            FROM pagamentos p JOIN orcamentos o ON o.id = p.orcamento_id
            WHERE p.status = 'pago' AND p.data_pagamento BETWEEN %s AND %s{estab_filter}{pac_filter}
            GROUP BY p.metodo ORDER BY total DESC""",
        tuple([ini, fim] + estab_params + pac_params),
    )

    por_profissional = db.fetch_all(
        f"""SELECT u_prof.nome AS profissional_nome, COUNT(p.id) AS qtd, SUM(p.valor) AS total
            FROM pagamentos p
            JOIN orcamentos o ON o.id = p.orcamento_id
            JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
            WHERE p.status = 'pago' AND p.data_pagamento BETWEEN %s AND %s{estab_filter}{pac_filter}
            GROUP BY o.profissional_usuario_id, u_prof.nome ORDER BY total DESC""",
        tuple([ini, fim] + estab_params + pac_params),
    )

    return templates.TemplateResponse(
        "financeiro/relatorio.html",
        {"request": request, "usuario": usuario, "periodo": periodo,
         "pagamentos": pagamentos, "resumo": resumo, "por_metodo": por_metodo, "por_profissional": por_profissional,
         "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int,
         "embedded": embedded in ("1", "True", "true")},
    )


@app.get("/pagamentos", response_class=HTMLResponse)
def listar_pagamentos(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
    exigir_permissao(usuario, "pagamentos", "ver")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario)
    pacientes_filtro = obter_pacientes_para_filtro(usuario, estab_id)
    paciente_id_int = int(paciente_id) if paciente_id and paciente_id.isdigit() else None

    query = """SELECT p.*, o.id AS orc_id, o.valor_total AS orc_valor_total,
                      u_pac.nome AS paciente_nome, u_prof.nome AS profissional_nome,
                      u_pac.cpf AS paciente_cpf, u_pac.telefone AS paciente_telefone, u_pac.email AS paciente_email
               FROM pagamentos p
               JOIN orcamentos o ON o.id = p.orcamento_id
               JOIN usuarios u_pac ON u_pac.id = o.paciente_usuario_id
               JOIN usuarios u_prof ON u_prof.id = o.profissional_usuario_id
               WHERE 1=1"""
    params = []

    if estab_id:
        query += " AND o.estabelecimento_id = %s"
        params.append(estab_id)
    elif usuario["tipo"] == "profissional":
        query += " AND o.profissional_usuario_id = %s"
        params.append(usuario["id"])
    if paciente_id_int:
        query += " AND o.paciente_usuario_id = %s"
        params.append(paciente_id_int)

    query += " ORDER BY p.criado_em DESC"
    pagamentos = db.fetch_all(query, tuple(params))

    resumo = {"total_pago": 0, "total_cancelado": 0, "qtd_pago": 0, "qtd_cancelado": 0}
    for p in pagamentos:
        if p["status"] == "pago":
            resumo["total_pago"] += float(p["valor"])
            resumo["qtd_pago"] += 1
        elif p["status"] == "cancelado":
            resumo["total_cancelado"] += float(p["valor"])
            resumo["qtd_cancelado"] += 1

    return templates.TemplateResponse(
        "pagamentos/lista.html",
        {"request": request, "usuario": usuario, "pagamentos": pagamentos,
         "resumo": resumo, "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int},
    )


@app.get("/api/verificar-email")
def api_verificar_email(request: Request, email: str, usuario=Depends(exigir_login)):
    if not email or "@" not in email:
        return JSONResponse(content={"existe": False})

    estab_id = resolver_estabelecimento(request, usuario)

    usuarios = db.fetch_all(
        "SELECT id, nome, tipo, email FROM usuarios WHERE email = %s AND ativo = TRUE",
        (email,),
    )

    prontuarios_encontrados = []
    for u in usuarios:
        if u["tipo"] != "paciente":
            continue

        vinculos = db.fetch_all(
            "SELECT estabelecimento_id FROM paciente_estabelecimento WHERE usuario_id = %s",
            (u["id"],),
        )
        estab_ids = [v["estabelecimento_id"] for v in vinculos]

        if estab_id and int(estab_id) in estab_ids:
            pronts = db.fetch_all(
                """SELECT pr.id, pr.numero_prontuario, pr.criado_em
                   FROM prontuarios pr
                   WHERE pr.paciente_usuario_id = %s""",
                (u["id"],),
            )
            pode_acessar = True
        elif usuario["tipo"] == "admin":
            pronts = db.fetch_all(
                """SELECT pr.id, pr.numero_prontuario, pr.criado_em
                   FROM prontuarios pr
                   WHERE pr.paciente_usuario_id = %s""",
                (u["id"],),
            )
            pode_acessar = True
        else:
            pronts = []
            pode_acessar = False

        prontuarios_encontrados.append({
            "usuario_id": u["id"],
            "nome": u["nome"],
            "pode_acessar": pode_acessar,
            "prontuarios": [{"id": p["id"], "numero": p["numero_prontuario"]} for p in pronts],
        })

    return JSONResponse(content={
        "existe": len(usuarios) > 0,
        "pacientes": prontuarios_encontrados,
    })


@app.get("/api/verificar-duplicata")
def api_verificar_duplicata(
    request: Request,
    cpf: str = Query(None),
    nome: str = Query(None),
    email: str = Query(None),
    usuario=Depends(exigir_login),
):
    estab_id = resolver_estabelecimento(request, usuario)
    resultado = {"cpf_duplicado": None, "nome_duplicados": [], "email_duplicado": None}

    if cpf and len(cpf.replace(".", "").replace("-", "").strip()) >= 11:
        cpf_limpo = cpf.replace(".", "").replace("-", "").strip()
        existente = db.fetch_one(
            "SELECT id, nome, email FROM usuarios WHERE cpf = %s AND ativo = TRUE",
            (cpf_limpo,),
        )
        if existente:
            pronts = db.fetch_all(
                """SELECT pr.id, pr.numero_prontuario FROM prontuarios pr
                   WHERE pr.paciente_usuario_id = %s AND pr.estabelecimento_id = %s""",
                (existente["id"], estab_id),
            )
            resultado["cpf_duplicado"] = {
                "usuario_id": existente["id"],
                "nome": existente["nome"],
                "email": existente["email"],
                "prontuarios": [{"id": p["id"], "numero": p["numero_prontuario"]} for p in pronts],
            }

    if nome and len(nome.strip()) >= 3:
        duplicados = db.fetch_all(
            "SELECT id, nome, email, cpf FROM usuarios WHERE nome = %s AND tipo = 'paciente' AND ativo = TRUE",
            (nome.strip(),),
        )
        for d in duplicados:
            pronts = db.fetch_all(
                """SELECT pr.id, pr.numero_prontuario FROM prontuarios pr
                   WHERE pr.paciente_usuario_id = %s AND pr.estabelecimento_id = %s""",
                (d["id"], estab_id),
            )
            resultado["nome_duplicados"].append({
                "usuario_id": d["id"],
                "nome": d["nome"],
                "email": d["email"],
                "cpf": d["cpf"],
                "prontuarios": [{"id": p["id"], "numero": p["numero_prontuario"]} for p in pronts],
            })

    if email and "@" in email:
        existente = db.fetch_one(
            "SELECT id, nome, cpf FROM usuarios WHERE email = %s AND tipo = 'paciente' AND ativo = TRUE",
            (email.strip().lower(),),
        )
        if existente:
            pronts = db.fetch_all(
                """SELECT pr.id, pr.numero_prontuario FROM prontuarios pr
                   WHERE pr.paciente_usuario_id = %s AND pr.estabelecimento_id = %s""",
                (existente["id"], estab_id),
            )
            resultado["email_duplicado"] = {
                "usuario_id": existente["id"],
                "nome": existente["nome"],
                "cpf": existente["cpf"],
                "prontuarios": [{"id": p["id"], "numero": p["numero_prontuario"]} for p in pronts],
            }

    return JSONResponse(content=resultado)


@app.get("/api/fix-orphan-patients")
def fix_orphan_patients(request: Request, usuario=Depends(exigir_login)):
    if not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    orfaos = db.fetch_all("""
        SELECT u.id, u.nome, u.email FROM usuarios u
        WHERE u.tipo = 'paciente' AND u.ativo = TRUE
          AND NOT EXISTS (SELECT 1 FROM prontuarios p WHERE p.paciente_usuario_id = u.id)
    """)

    if not orfaos:
        return JSONResponse({"mensagem": "Nenhum paciente orfo", "criados": 0})

    estab = db.fetch_one("SELECT id FROM estabelecimentos WHERE ativo = TRUE ORDER BY id LIMIT 1")
    if not estab:
        return JSONResponse({"erro": "Nenhum estabelecimento ativo"}, status_code=400)

    estab_id = estab["id"]
    criados = []
    for pac in orfaos:
        numero = _proximo_numero_prontuario(estab_id)
        db.execute(
            "INSERT IGNORE INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s)",
            (pac["id"], estab_id),
        )
        db.execute(
            "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
            (pac["id"], estab_id, numero),
        )
        criados.append({"nome": pac["nome"], "numero": numero})

    return JSONResponse({"mensagem": f"{len(criados)} prontuarios criados", "criados": criados})
