import json
import logging
import urllib.request
import urllib.error
from config import settings

logger = logging.getLogger("email")


def _email_habilitado_no_banco() -> bool:
    try:
        from database.connection import db
        row = db.fetch_one("SELECT valor FROM config_sistema WHERE chave = 'email_habilitado'")
        if row:
            val = row["valor"] if isinstance(row, dict) else row.get("valor", "true")
            return str(val).lower() == "true"
    except Exception:
        pass
    return True


def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> bool:
    if not settings.EMAIL_HABILITADO:
        logger.info("Email desabilitado (variavel de ambiente). Envio ignorado.")
        return False
    if not _email_habilitado_no_banco():
        logger.info("Email desabilitado (config_sistema). Envio ignorado.")
        return False
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY nao configurada.")
        return False
    if not destinatario:
        logger.warning("Destinatario vazio. Envio ignorado.")
        return False

    from_email = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    payload = json.dumps({
        "from": from_email,
        "to": [destinatario],
        "subject": assunto,
        "html": corpo_html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "SISGERSA/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            logger.info(f"Email enviado para {destinatario}: {assunto} (id={data.get('id')})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"Resend API erro {e.code} para {destinatario}: {body}")
        return False
    except Exception as e:
        logger.error(f"Erro ao enviar email para {destinatario}: {e}")
        return False


def montar_confirmacao_agendamento(
    paciente_nome: str,
    profissional_nome: str,
    data_formatada: str,
    hora_formatada: str,
    duracao: int,
    procedimento: str = None,
    estabelecimento_nome: str = None,
    estabelecimento_endereco: str = None,
) -> str:
    proc_linha = f"""
    <tr>
        <td style="padding:8px 0;color:#666;font-size:14px;">Procedimento</td>
        <td style="padding:8px 0;font-weight:600;font-size:14px;">{procedimento}</td>
    </tr>""" if procedimento else ""

    local_linha = ""
    if estabelecimento_nome:
        local_linha = f"""
    <tr>
        <td style="padding:8px 0;color:#666;font-size:14px;">Local</td>
        <td style="padding:8px 0;font-weight:600;font-size:14px;">{estabelecimento_nome}</td>
    </tr>"""
    if estabelecimento_endereco:
        local_linha += f"""
    <tr>
        <td style="padding:8px 0;color:#666;font-size:14px;">Endereco</td>
        <td style="padding:8px 0;font-size:14px;">{estabelecimento_endereco}</td>
    </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Tahoma,sans-serif;">
<div style="max-width:560px;margin:30px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <div style="background:linear-gradient(135deg,#1a5276,#2e86c1);padding:28px 30px;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:22px;">Consulta Agendada</h1>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:14px;">SISGERSA - Sistema de Gestao</p>
    </div>

    <div style="padding:28px 30px;">
        <p style="font-size:15px;color:#333;margin:0 0 20px;">Ola <strong>{paciente_nome}</strong>,</p>
        <p style="font-size:14px;color:#555;margin:0 0 20px;">Sua consulta foi confirmada com sucesso. Confira os detalhes abaixo:</p>

        <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
            <tr>
                <td style="padding:8px 0;color:#666;font-size:14px;">Data</td>
                <td style="padding:8px 0;font-weight:600;font-size:14px;">{data_formatada}</td>
            </tr>
            <tr>
                <td style="padding:8px 0;color:#666;font-size:14px;">Horario</td>
                <td style="padding:8px 0;font-weight:600;font-size:14px;">{hora_formatada} ({duracao} min)</td>
            </tr>
            <tr>
                <td style="padding:8px 0;color:#666;font-size:14px;">Profissional</td>
                <td style="padding:8px 0;font-weight:600;font-size:14px;">Dr(a). {profissional_nome}</td>
            </tr>
            {proc_linha}
            {local_linha}
        </table>

        <p style="font-size:13px;color:#888;margin:0;">Se precisar remarcar ou cancelar, entre em contato conosco.</p>
    </div>

    <div style="background:#f8f9fa;padding:16px 30px;text-align:center;border-top:1px solid #eee;">
        <p style="font-size:11px;color:#aaa;margin:0;">SISGERSA &copy; 2026 - Sistema de Gestao de Prontuarios</p>
    </div>
</div>
</body>
</html>"""


def montar_lembrete_consulta(
    paciente_nome: str,
    profissional_nome: str,
    data_formatada: str,
    hora_formatada: str,
    duracao: int,
    procedimento: str = None,
    estabelecimento_nome: str = None,
) -> str:
    proc_linha = f"""
    <tr>
        <td style="padding:8px 0;color:#666;font-size:14px;">Procedimento</td>
        <td style="padding:8px 0;font-weight:600;font-size:14px;">{procedimento}</td>
    </tr>""" if procedimento else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Tahoma,sans-serif;">
<div style="max-width:560px;margin:30px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <div style="background:linear-gradient(135deg,#1a3c5e,#3b7dd8);padding:28px 30px;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:22px;">Lembrete de Consulta</h1>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:14px;">Sua consulta e amanha!</p>
    </div>

    <div style="padding:28px 30px;">
        <p style="font-size:15px;color:#333;margin:0 0 20px;">Ola <strong>{paciente_nome}</strong>,</p>
        <p style="font-size:14px;color:#555;margin:0 0 20px;">Este e um lembrete de que voce tem uma consulta agendada para amanha:</p>

        <table style="width:100%;border-collapse:collapse;margin-bottom:20px;background:#f0f7ff;border-radius:8px;padding:12px;">
            <tr>
                <td style="padding:8px 12px;color:#666;font-size:14px;">Data</td>
                <td style="padding:8px 12px;font-weight:600;font-size:14px;">{data_formatada}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;color:#666;font-size:14px;">Horario</td>
                <td style="padding:8px 12px;font-weight:600;font-size:14px;">{hora_formatada} ({duracao} min)</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;color:#666;font-size:14px;">Profissional</td>
                <td style="padding:8px 12px;font-weight:600;font-size:14px;">Dr(a). {profissional_nome}</td>
            </tr>
            {proc_linha}
            {"<tr><td style='padding:8px 12px;color:#666;font-size:14px;'>Local</td><td style='padding:8px 12px;font-weight:600;font-size:14px;'>" + estabelecimento_nome + "</td></tr>" if estabelecimento_nome else ""}
        </table>

        <p style="font-size:14px;color:#c0392b;font-weight:600;margin:0 0 15px;">Por favor, chegue com 10 minutos de antecedencia.</p>
        <p style="font-size:13px;color:#888;margin:0;">Se precisar remarcar ou cancelar, entre em contato o quanto antes.</p>
    </div>

    <div style="background:#f8f9fa;padding:16px 30px;text-align:center;border-top:1px solid #eee;">
        <p style="font-size:11px;color:#aaa;margin:0;">SISGERSA &copy; 2026 - Sistema de Gestao de Prontuarios</p>
    </div>
</div>
</body>
</html>"""
