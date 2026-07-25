from datetime import datetime, timedelta
import os
import uuid
import secrets
from collections import defaultdict
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sisgersa")

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from database.connection import db
from config import settings
from utils.auth import (
    usuario_por_email,
    verificar_senha,
    criar_token,
    verificar_token,
    obter_estabelecimentos_usuario,
    criar_usuario,
    vincular_paciente,
)
from utils.permissoes import (
    MODULOS, DEFAULT_PERMISSIONS,
    pode_acessar, obter_permissoes_usuario, obter_permissoes_para_nav,
    salvar_permissoes, limpar_permissoes, exigir_permissao,
)
from utils.planos import verificar_limite, LimiteAtingidoError, obter_plano_estabelecimento, contar_uso, bloquear_se_limite

app = FastAPI(title="SISGERSA", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["MODULOS_INFO"] = MODULOS
templates.env.globals["pode_acessar"] = pode_acessar


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 302 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data:"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)


login_attempts = defaultdict(list)
RATE_LIMIT_WINDOW = 300
RATE_LIMIT_MAX = 10

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    return len(login_attempts[ip]) >= RATE_LIMIT_MAX

def record_login_attempt(ip: str):
    login_attempts[ip].append(time.time())


write_requests = defaultdict(list)
WRITE_RATE_WINDOW = 60
WRITE_RATE_LIMIT_CREATE = 50
WRITE_RATE_LIMIT_DELETE = 15

def _is_write_limited(key: str, limit: int) -> bool:
    now = time.time()
    write_requests[key] = [t for t in write_requests[key] if now - t < WRITE_RATE_WINDOW]
    return len(write_requests[key]) >= limit

def record_write(key: str):
    write_requests[key].append(time.time())

def is_write_limited(request: Request, usuario: dict, action: str = "create") -> bool:
    key = f"{usuario['id']}:{action}"
    limit = WRITE_RATE_LIMIT_DELETE if action == "delete" else WRITE_RATE_LIMIT_CREATE
    if _is_write_limited(key, limit):
        return True
    record_write(key)
    return False


def obter_usuario_atual(request: Request):
    token = request.cookies.get("token")
    if not token:
        return None
    payload = verificar_token(token)
    if not payload:
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
    if not estab_id and usuario["tipo"] == "admin":
        todos = db.fetch_all("SELECT id FROM estabelecimentos WHERE ativo = TRUE")
        if len(todos) == 1:
            estab_id = str(todos[0]["id"])
        elif len(todos) > 1 and not estab_id_form:
            estab_id = str(todos[0]["id"])
    return estab_id


def verificar_acesso_registro(request: Request, usuario: dict, registro: dict):
    if usuario.get("is_super"):
        return
    estab_id_check = request.cookies.get("estabelecimento_id")
    if usuario["tipo"] in ("admin", "profissional"):
        if estab_id_check and str(registro.get("estabelecimento_id")) != str(estab_id_check):
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


@app.on_event("startup")
def startup():
    logger.info(f"Startup: ENVIRONMENT={settings.ENVIRONMENT}, DB_ENGINE={settings.DB_ENGINE}")
    try:
        db.get_connection()
        logger.info("Startup: conexao DB OK")
    except Exception as e:
        logger.error(f"Startup: falha na conexao DB: {e}")

    if settings.DB_ENGINE == "postgresql":
        try:
            from init_db import criar_banco, criar_admin_padrao, seed_planos, seed_cupons
            criar_banco()
            criar_admin_padrao()
            seed_planos()
            seed_cupons()
            logger.info("Startup: banco inicializado com sucesso")
        except Exception as e:
            logger.error(f"Startup: erro ao inicializar banco: {e}", exc_info=True)
    else:
        try:
            from init_db import seed_planos, seed_cupons
            seed_planos()
            seed_cupons()
        except Exception as e:
            logger.error(f"Startup: erro ao semear dados: {e}")


@app.on_event("shutdown")
def shutdown():
    db.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    usuario = obter_usuario_atual(request)
    if usuario:
        return RedirectResponse("/dashboard", status_code=302)
    planos = db.fetch_all("SELECT * FROM planos WHERE ativo = TRUE ORDER BY valor_mensal ASC")
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "planos": planos},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "erro": None})


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), senha: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"

    if is_rate_limited(client_ip):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Muitas tentativas. Aguarde 5 minutos."},
        )

    usuario = usuario_por_email(email)
    if not usuario or not verificar_senha(senha, usuario["senha_hash"]):
        record_login_attempt(client_ip)
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "erro": "Email ou senha invalidos"},
        )

    token = criar_token(usuario["id"], usuario["tipo"], bool(usuario.get("is_super", False)))

    estabelecimentos = []
    if usuario["tipo"] in ("profissional", "recepcionista"):
        estabelecimentos = obter_estabelecimentos_usuario(usuario["id"])

    cookie_kwargs = dict(httponly=True, max_age=172800, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard?welcome=1", status_code=302)
    response.set_cookie("token", token, **cookie_kwargs)

    if len(estabelecimentos) == 1:
        response.set_cookie("estabelecimento_id", str(estabelecimentos[0]["id"]), **cookie_kwargs)

    return response


@app.get("/registrar", response_class=HTMLResponse)
def registrar_page(request: Request):
    usuario = obter_usuario_atual(request)
    if usuario:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("auth/registrar.html", {"request": request})


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

    if cupom["max_usos"] > 0 and cupom["usos_atual"] >= cupom["max_usos"]:
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
):
    if senha != senha2:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "As senhas não coincidem"
        })

    if len(senha) < 6:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "A senha deve ter no mínimo 6 caracteres"
        })

    from database.connection import db
    existente = db.fetch_one("SELECT id FROM usuarios WHERE email = %s", (email,))
    if existente:
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": "Já existe uma conta com este email"
        })

    cupom_id = None
    plano_slug = "gratis"
    if cupom and cupom.strip():
        cupom_row = db.fetch_one(
            "SELECT * FROM cupons WHERE codigo = %s AND ativo = TRUE",
            (cupom.strip().upper(),),
        )
        if cupom_row:
            if cupom_row["max_usos"] > 0 and cupom_row["usos_atual"] >= cupom_row["max_usos"]:
                return templates.TemplateResponse("auth/registrar.html", {
                    "request": request, "erro": "Cupom atingiu o limite de uso"
                })
            cupom_id = cupom_row["id"]
            plano_slug = cupom_row["plano_destino"]

    plano_row = db.fetch_one("SELECT id FROM planos WHERE slug = %s", (plano_slug,))
    plano_id = plano_row["id"] if plano_row else None

    try:
        if settings.DB_ENGINE == "postgresql":
            db.execute(
                """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, plano_id, cupom_id)
                   VALUES (%s, %s, NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), %s, %s)""",
                (nome_estabelecimento, tipo, cnpj or "", telefone or "", email_estab or "", endereco or "", plano_id, cupom_id),
            )
        else:
            db.execute(
                """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, plano_id, cupom_id)
                   VALUES (%s, %s, NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), NULLIF(%s,''), %s, %s)""",
                (nome_estabelecimento, tipo, cnpj or "", telefone or "", email_estab or "", endereco or "", plano_id, cupom_id),
            )

        estab = db.fetch_one("SELECT id FROM estabelecimentos ORDER BY id DESC LIMIT 1")
        estab_id = estab["id"]

        if cupom_id:
            db.execute("UPDATE cupons SET usos_atual = usos_atual + 1 WHERE id = %s", (cupom_id,))
    except Exception as e:
        logger.error(f"registrar: erro ao criar estabelecimento: {e}")
        return templates.TemplateResponse("auth/registrar.html", {
            "request": request, "erro": f"Erro ao criar estabelecimento: {e}"
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
            "request": request, "erro": f"Erro ao criar usuário: {e}"
        })

    token = criar_token(admin_id, "admin", False)

    cookie_kwargs = dict(httponly=True, max_age=172800, samesite="lax")
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if is_https:
        cookie_kwargs["secure"] = True

    response = RedirectResponse("/dashboard?welcome=1", status_code=302)
    response.set_cookie("token", token, **cookie_kwargs)
    response.set_cookie("estabelecimento_id", str(estab_id), **cookie_kwargs)

    logger.info(f"registrar: nova clínica '{nome_estabelecimento}' (ID={estab_id}), admin={email}")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("token")
    response.delete_cookie("estabelecimento_id")
    return response


@app.post("/estabelecimento/selecionar")
def selecionar_estabelecimento(
    request: Request,
    estabelecimento_id: str = Form(""),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin" or not usuario.get("is_super"):
        raise HTTPException(status_code=403)

    redirect = request.headers.get("referer", "/dashboard")
    cookie_kwargs = dict(httponly=True, max_age=172800, samesite="lax")
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
    if usuario["tipo"] != "admin":
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
    if usuario["tipo"] != "admin":
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


@app.get("/api/usuarios-por-estab")
def api_usuarios_por_estab(
    request: Request,
    estabelecimento_id: int = Query(...),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin":
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
    if estab_id:
        plano_info = obter_plano_estabelecimento(estab_id)
        uso_info = contar_uso(estab_id)

    return templates.TemplateResponse(
        f"dashboard/{usuario['tipo']}.html",
        {
            "request": request, "usuario": usuario, "now": datetime.now(),
            "plano_info": plano_info, "uso_info": uso_info,
        },
    )


@app.get("/api/dashboard-stats")
def dashboard_stats(
    request: Request,
    periodo: str = Query("mes"),
    data_inicio: str = Query(None),
    data_fim: str = Query(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    pacientes = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM usuarios WHERE tipo = 'paciente' AND ativo = TRUE{estab_filter}",
        tuple(estab_params),
    )
    profissionais = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM usuarios WHERE tipo = 'profissional' AND ativo = TRUE{estab_filter}",
        tuple(estab_params),
    )
    convenios = db.fetch_one("SELECT COUNT(*) AS total FROM convenios WHERE ativo = TRUE")
    procedimentos = db.fetch_one("SELECT COUNT(*) AS total FROM procedimentos WHERE ativo = TRUE")

    consultas_periodo = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM consultas WHERE data_hora BETWEEN %s AND %s{estab_filter}",
        (ini, fim) + tuple(estab_params),
    )

    consultas_status = db.fetch_all(
        f"SELECT status, COUNT(*) AS total FROM consultas WHERE data_hora BETWEEN %s AND %s{estab_filter} GROUP BY status",
        (ini, fim) + tuple(estab_params),
    )

    orc_rascunho = db.fetch_one(
        "SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'rascunho' AND criado_em BETWEEN %s AND %s",
        (ini, fim),
    )
    orc_enviados = db.fetch_one(
        "SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'enviado' AND criado_em BETWEEN %s AND %s",
        (ini, fim),
    )
    orc_aprovados = db.fetch_one(
        "SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'aprovado' AND criado_em BETWEEN %s AND %s",
        (ini, fim),
    )
    orc_rejeitados = db.fetch_one(
        "SELECT COUNT(*) AS total FROM orcamentos WHERE status = 'rejeitado' AND criado_em BETWEEN %s AND %s",
        (ini, fim),
    )

    faturamento = db.fetch_one(
        """SELECT COALESCE(SUM(valor_total), 0) AS total
           FROM orcamentos WHERE status = 'aprovado'
           AND atualizado_em BETWEEN %s AND %s""",
        (ini, fim),
    )

    faturamento_por_prof = db.fetch_all(
        """SELECT u.nome AS profissional_nome, COUNT(o.id) AS qtd, COALESCE(SUM(o.valor_total), 0) AS valor
           FROM orcamentos o
           JOIN usuarios u ON u.id = o.profissional_usuario_id
           WHERE o.status = 'aprovado' AND o.atualizado_em BETWEEN %s AND %s
           GROUP BY o.profissional_usuario_id, u.nome ORDER BY valor DESC""",
        (ini, fim),
    )

    return JSONResponse(content={
        "estabelecimentos": estabelecimentos["total"],
        "pacientes": pacientes["total"],
        "profissionais": profissionais["total"],
        "convenios": convenios["total"],
        "procedimentos": procedimentos["total"],
        "consultas_total": consultas_periodo["total"],
        "consultas_status": {r["status"]: r["total"] for r in consultas_status},
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
    if usuario["tipo"] != "admin" or not usuario.get("is_super"):
        raise HTTPException(status_code=403)
    estabs = db.fetch_all(
        "SELECT id, nome FROM estabelecimentos WHERE ativo = TRUE ORDER BY nome"
    )
    return JSONResponse(content={"estabelecimentos": estabs})


_server_start_time = time.time()

@app.get("/api/status")
def sistema_status():
    db_ok = False
    db_latency_ms = -1
    try:
        t0 = time.time()
        conn = db.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_ok = True
            db_latency_ms = round((time.time() - t0) * 1000, 1)
    except Exception:
        db_ok = False

    return JSONResponse(content={
        "banco": db_ok,
        "db_latency_ms": db_latency_ms,
        "uptime_seg": round(time.time() - _server_start_time),
        "hora_servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


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


@app.get("/pacientes", response_class=HTMLResponse)
def listar_pacientes(request: Request, usuario=Depends(exigir_login)):
    estab_id = resolver_estabelecimento(request, usuario)
    exigir_permissao(usuario, "pacientes", "ver", estab_id)
    if estab_id:
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome, u.email, u.telefone, u.cpf, pe.data_cadastro
               FROM usuarios u
               JOIN paciente_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE
               ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario.get("is_super"):
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome, u.email, u.telefone, u.cpf, NULL as data_cadastro
               FROM usuarios u WHERE u.tipo = 'paciente' AND u.ativo = TRUE ORDER BY u.nome"""
        )
    elif usuario["tipo"] == "paciente":
        pacientes = [usuario]
    else:
        pacientes = []

    return templates.TemplateResponse(
        "pacientes/lista.html",
        {"request": request, "usuario": usuario, "pacientes": pacientes},
    )


@app.get("/estabelecimentos", response_class=HTMLResponse)
def listar_estabelecimentos(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "estabelecimentos", "ver")
    if usuario["tipo"] != "admin":
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
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    db.execute(
        """INSERT INTO estabelecimentos (nome, tipo, cnpj, telefone, email, endereco, logo_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (nome, tipo, cnpj, telefone, email, endereco, logo_url),
    )
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.post("/estabelecimentos/{estab_id}/desativar")
def desativar_estabelecimento(estab_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    db.execute("UPDATE estabelecimentos SET ativo = FALSE WHERE id = %s", (estab_id,))
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.get("/estabelecimentos/{estab_id}/editar", response_class=HTMLResponse)
def editar_estabelecimento(estab_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "estabelecimentos", "editar")
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    estab = db.fetch_one("SELECT * FROM estabelecimentos WHERE id = %s", (estab_id,))
    if not estab:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "estabelecimentos/editar.html",
        {"request": request, "usuario": usuario, "estab": estab},
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
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    db.execute(
        """UPDATE estabelecimentos
           SET nome = %s, tipo = %s, cnpj = %s, telefone = %s, email = %s, endereco = %s, logo_url = %s
           WHERE id = %s""",
        (nome, tipo, cnpj, telefone, email, endereco, logo_url, estab_id),
    )
    return RedirectResponse("/estabelecimentos", status_code=302)


@app.get("/profissionais", response_class=HTMLResponse)
def listar_profissionais(request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "profissionais", "ver")
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    profissionais = db.fetch_all(
        """SELECT u.*, pe.especialidade, pe.cargo, pe.estabelecimento_id,
                  e.nome AS estabelecimento_nome
           FROM usuarios u
           LEFT JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
           LEFT JOIN estabelecimentos e ON e.id = pe.estabelecimento_id
           WHERE u.tipo = 'profissional' AND u.ativo = TRUE
           ORDER BY u.nome"""
    )

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
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "profissionais", "criar")
    if usuario["tipo"] != "admin":
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
            "INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id, especialidade, cargo, registro_profissional) VALUES (%s, %s, %s, %s, %s)",
            (user_id, int(estabelecimento_id), especialidade, cargo, registro_profissional),
        )

    return RedirectResponse("/profissionais", status_code=302)


@app.get("/profissionais/{prof_id}/editar", response_class=HTMLResponse)
def editar_profissional(prof_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "profissionais", "editar")
    if usuario["tipo"] != "admin":
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
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] != "admin":
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
                   SET estabelecimento_id = %s, especialidade = %s, cargo = %s, registro_profissional = %s
                   WHERE usuario_id = %s""",
                (int(estabelecimento_id), especialidade, cargo, registro_profissional, prof_id),
            )
        else:
            vincular_profissional(prof_id, int(estabelecimento_id), especialidade, cargo, registro_profissional)

    return RedirectResponse("/profissionais", status_code=302)


@app.post("/profissionais/{prof_id}/desativar")
def desativar_profissional(prof_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] != "admin":
        raise HTTPException(status_code=403)

    db.execute("UPDATE usuarios SET ativo = FALSE WHERE id = %s", (prof_id,))
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
    senha: str = Form(...),
    foto_url: str = Form(None),
    estabelecimento_id: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "pacientes", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista"):
        raise HTTPException(status_code=403)

    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if estab_id:
        try:
            bloquear_se_limite(estab_id, "pacientes")
        except LimiteAtingidoError as e:
            return RedirectResponse(f"/pacientes?erro_quota={e}", status_code=302)

    user_id = criar_usuario(nome, email, senha, "paciente", telefone)
    db.execute(
        "UPDATE usuarios SET cpf = %s, data_nascimento = %s, endereco = %s WHERE id = %s",
        (cpf or None, data_nascimento or None, endereco or None, user_id),
    )
    if foto_url:
        db.execute("UPDATE usuarios SET foto_url = %s WHERE id = %s", (foto_url, user_id))

    if estab_id:
        vincular_paciente(user_id, int(estab_id))

    return RedirectResponse("/pacientes", status_code=302)


@app.get("/pacientes/{pac_id}/editar", response_class=HTMLResponse)
def editar_paciente(pac_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "pacientes", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    foto_url: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista"):
        raise HTTPException(status_code=403)

    db.execute(
        "UPDATE usuarios SET nome = %s, email = %s, telefone = %s, cpf = %s, data_nascimento = %s, endereco = %s, foto_url = %s WHERE id = %s",
        (nome, email, telefone, cpf or None, data_nascimento or None, endereco or None, foto_url, pac_id),
    )
    return RedirectResponse("/pacientes", status_code=302)


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
    procedimento_id: int = Form(None),
    observacoes: str = Form(None),
    estabelecimento_id: str = Form(None),
    usuario=Depends(exigir_login),
):
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

    db.execute(
        """INSERT INTO consultas
           (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, prontuario_id, procedimento_id, data_hora, duracao_minutos, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (paciente_id, profissional_id, estab_id, prontuario["id"] if prontuario else None, procedimento_id, data_hora, duracao, observacoes),
    )
    return RedirectResponse("/consultas", status_code=302)


@app.post("/consultas/{consulta_id}/status")
def atualizar_status_consulta(
    consulta_id: int,
    request: Request,
    status: str = Form(...),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "consultas", "editar")
    if is_write_limited(request, usuario, "status"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    if usuario["tipo"] == "profissional":
        consulta = db.fetch_one("SELECT * FROM consultas WHERE id = %s", (consulta_id,))
        if not consulta or consulta["profissional_usuario_id"] != usuario["id"]:
            raise HTTPException(status_code=403)

    valid_statuses = {"agendada", "confirmada", "em_andamento", "concluida", "cancelada", "faltou"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Status invalido")

    db.execute("UPDATE consultas SET status = %s WHERE id = %s", (status, consulta_id))
    return RedirectResponse("/consultas", status_code=302)


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
        if usuario.get("is_super"):
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
        else:
            prontuarios = []

    pacientes = []
    estabelecimentos_list = []
    if estab_id:
        pacientes = db.fetch_all(
            """SELECT u.id, u.nome FROM usuarios u
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
def ver_prontuario(prontuario_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "prontuarios", "ver")
    prontuario = db.fetch_one(
        """SELECT p.*, u.nome AS paciente_nome, u.email AS paciente_email, u.telefone AS paciente_telefone
           FROM prontuarios p
           JOIN usuarios u ON u.id = p.paciente_usuario_id
           WHERE p.id = %s""",
        (prontuario_id,),
    )
    if not prontuario:
        raise HTTPException(status_code=404)

    verificar_acesso_registro(request, usuario, prontuario)

    evolucoes = db.fetch_all(
        """SELECT e.*, u.nome AS profissional_nome
           FROM evolucoes e
           JOIN usuarios u ON u.id = e.profissional_usuario_id
           WHERE e.prontuario_id = %s
           ORDER BY e.data DESC""",
        (prontuario_id,),
    )

    for ev in evolucoes:
        ev["tratamentos"] = db.fetch_all(
            "SELECT * FROM tratamentos WHERE evolucao_id = %s",
            (ev["id"],),
        )

    consultas = db.fetch_all(
        """SELECT c.*, u.nome AS profissional_nome
           FROM consultas c
           JOIN usuarios u ON u.id = c.profissional_usuario_id
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

    return templates.TemplateResponse(
        "prontuarios/visualizar.html",
        {
            "request": request,
            "usuario": usuario,
            "prontuario": prontuario,
            "evolucoes": evolucoes,
            "consultas": consultas,
            "imagens": imagens,
            "profissionais": profissionais,
            "orcamentos_paciente": orcamentos_paciente,
            "tratamentos_realizados": tratamentos_realizados,
            "procedimentos": procedimentos,
            "orcamento_disponivel_id": orcamento_disponivel_id,
        },
    )


@app.post("/prontuarios/criar")
def criar_prontuario(
    request: Request,
    paciente_id: int = Form(...),
    numero: str = Form(None),
    estabelecimento_id: str = Form(None),
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "prontuarios", "criar")
    if is_write_limited(request, usuario, "create"):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde 1 minuto.")
    estab_id = resolver_estabelecimento(request, usuario, estabelecimento_id)
    if not estab_id or usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    try:
        bloquear_se_limite(estab_id, "prontuarios")
    except LimiteAtingidoError as e:
        return RedirectResponse(f"/prontuarios?erro_quota={e}", status_code=302)
    except Exception as e:
        logger.warning(f"criar_prontuario: erro ao verificar quota: {e}")

    if not numero:
        count = db.fetch_one(
            "SELECT COUNT(*) AS total FROM prontuarios WHERE estabelecimento_id = %s",
            (estab_id,),
        )
        numero = f"PRONT-{int(count['total']) + 1:05d}"

    db.execute(
        "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
        (paciente_id, estab_id, numero),
    )
    return RedirectResponse("/prontuarios", status_code=302)


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
            """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome
               FROM consultas c
               JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
               JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
               WHERE c.paciente_usuario_id = %s
               AND c.data_hora BETWEEN %s AND %s
               ORDER BY c.data_hora""",
            (usuario["id"], inicio, fim),
        )
    elif usuario["tipo"] == "profissional":
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
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
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
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
        query = """SELECT c.*, u_prof.nome AS profissional_nome, u_pac.nome AS paciente_nome
                   FROM consultas c
                   JOIN usuarios u_prof ON u_prof.id = c.profissional_usuario_id
                   JOIN usuarios u_pac ON u_pac.id = c.paciente_usuario_id
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
            """SELECT u.id, u.nome FROM usuarios u
               JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
               WHERE pe.estabelecimento_id = %s AND u.ativo = TRUE ORDER BY u.nome""",
            (estab_id,),
        )
    elif usuario.get("is_super"):
        profissionais = db.fetch_all(
            "SELECT id, nome FROM usuarios WHERE tipo = 'profissional' AND ativo = TRUE ORDER BY nome"
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "convenios", "criar")
    if usuario["tipo"] not in ("admin", "recepcionista"):
        raise HTTPException(status_code=403)
    db.execute(
        "INSERT INTO convenios (nome, cnpj, telefone, email) VALUES (%s, %s, %s, %s)",
        (nome, cnpj, telefone, email),
    )
    return RedirectResponse("/convenios", status_code=302)


@app.get("/convenios/{conv_id}/editar", response_class=HTMLResponse)
def editar_convenio(conv_id: int, request: Request, usuario=Depends(exigir_login)):
    exigir_permissao(usuario, "convenios", "editar")
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista"):
        raise HTTPException(status_code=403)
    db.execute(
        "UPDATE convenios SET nome = %s, cnpj = %s, telefone = %s, email = %s WHERE id = %s",
        (nome, cnpj, telefone, email, conv_id),
    )
    return RedirectResponse("/convenios", status_code=302)


@app.post("/convenios/{conv_id}/desativar")
def desativar_convenio(conv_id: int, usuario=Depends(exigir_login)):
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    usuario=Depends(exigir_login),
):
    exigir_permissao(usuario, "procedimentos", "criar")
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    db.execute(
        "INSERT INTO procedimentos (nome, descricao, duracao_minutos) VALUES (%s, %s, %s)",
        (nome, descricao, duracao_minutos),
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
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)
    db.execute(
        "UPDATE procedimentos SET nome = %s, descricao = %s, duracao_minutos = %s WHERE id = %s",
        (nome, descricao, duracao_minutos, proc_id),
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    convenio_id: int = Form(None),
    numero_carteirinha: str = Form(None),
    validade: str = Form(None),
    usuario=Depends(exigir_login),
):
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
        raise HTTPException(status_code=403)
    db.execute("DELETE FROM paciente_convenio WHERE id = %s", (vc_id,))
    return RedirectResponse(f"/pacientes/{pac_id}/convenio", status_code=302)


@app.get("/orcamentos", response_class=HTMLResponse)
def listar_orcamentos(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
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

    return templates.TemplateResponse(
        "orcamentos/lista.html",
        {"request": request, "usuario": usuario, "orcamentos": orcamentos,
         "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int},
    )


@app.get("/orcamentos/novo", response_class=HTMLResponse)
def novo_orcamento(request: Request, usuario=Depends(exigir_login)):
    estab_id = resolver_estabelecimento(request, usuario)
    if usuario["tipo"] not in ("admin", "recepcionista", "profissional"):
        raise HTTPException(status_code=403)

    pacientes = []
    profissionais = []
    convenios = db.fetch_all("SELECT id, nome FROM convenios WHERE ativo = TRUE ORDER BY nome")

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

    cursor = db.execute(
        """INSERT INTO orcamentos
           (paciente_usuario_id, profissional_usuario_id, estabelecimento_id, convenio_id, data_validade, observacoes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (paciente_id, profissional_id, estab_id, conv_id, dv, observacoes),
    )

    new_id = cursor.lastrowid
    return RedirectResponse(f"/orcamentos/{new_id}", status_code=302)


@app.get("/orcamentos/{orc_id}", response_class=HTMLResponse)
def ver_orcamento(orc_id: int, request: Request, usuario=Depends(exigir_login)):
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

    return templates.TemplateResponse(
        "orcamentos/visualizar.html",
        {
            "request": request, "usuario": usuario,
            "orcamento": orcamento, "itens": itens,
            "procedimentos": procedimentos,
            "tratamentos_realizados": tratamentos_realizados,
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

    if usuario["tipo"] == "profissional":
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

    if usuario["tipo"] == "profissional" and orcamento["profissional_usuario_id"] != usuario["id"]:
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    if usuario["tipo"] != "admin":
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
    if usuario["tipo"] not in ("admin", "recepcionista"):
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
def nota_fiscal(orc_id: int, request: Request, usuario=Depends(exigir_login)):
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

    return templates.TemplateResponse(
        "orcamentos/nota_fiscal.html",
        {"request": request, "usuario": usuario, "orcamento": orcamento, "itens": itens, "pagamentos": pagamentos, "total_pago": total_pago},
    )


@app.get("/financeiro", response_class=HTMLResponse)
def relatorio_financeiro(request: Request, usuario=Depends(exigir_login), paciente_id: str = Query(None)):
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
         "pacientes_filtro": pacientes_filtro, "paciente_id": paciente_id_int},
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
