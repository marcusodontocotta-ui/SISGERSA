import threading
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("scheduler")

_scheduler_thread = None
_running = False


def _buscar_consultas_para_lembrete():
    from database.connection import db
    from utils.email import enviar_email, montar_lembrete_consulta

    agora = datetime.now()
    janela_inicio = agora + timedelta(hours=23)
    janela_fim = agora + timedelta(hours=25)

    consultas = db.fetch_all(
        """SELECT c.id, c.data_hora, c.duracao_minutos, c.paciente_usuario_id,
                  c.profissional_usuario_id, c.estabelecimento_id, c.procedimento_id,
                  c.lembrete_enviado,
                  u.nome AS paciente_nome, u.email AS paciente_email,
                  p.nome AS profissional_nome,
                  proc.nome AS procedimento_nome,
                  e.nome AS estabelecimento_nome
           FROM consultas c
           JOIN usuarios u ON u.id = c.paciente_usuario_id
           JOIN usuarios p ON p.id = c.profissional_usuario_id
           LEFT JOIN procedimentos proc ON proc.id = c.procedimento_id
           LEFT JOIN estabelecimentos e ON e.id = c.estabelecimento_id
           WHERE c.status IN ('agendada', 'confirmada')
             AND c.lembrete_enviado = FALSE
             AND c.data_hora >= %s
             AND c.data_hora <= %s""",
        (janela_inicio, janela_fim),
    )

    if not consultas:
        return

    for c in consultas:
        if not c.get("paciente_email"):
            logger.info(f"Consulta {c['id']}: paciente sem email, lembrete ignorado.")
            db.execute("UPDATE consultas SET lembrete_enviado = TRUE WHERE id = %s", (c["id"],))
            continue

        data_hora = c["data_hora"]
        if isinstance(data_hora, str):
            data_hora = datetime.strptime(data_hora, "%Y-%m-%d %H:%M:%S")

        data_fmt = data_hora.strftime("%d/%m/%Y")
        hora_fmt = data_hora.strftime("%H:%M")

        corpo = montar_lembrete_consulta(
            paciente_nome=c["paciente_nome"],
            profissional_nome=c["profissional_nome"],
            data_formatada=data_fmt,
            hora_formatada=hora_fmt,
            duracao=c["duracao_minutos"],
            procedimento=c.get("procedimento_nome"),
            estabelecimento_nome=c.get("estabelecimento_nome"),
        )

        enviado = enviar_email(
            destinatario=c["paciente_email"],
            assunto=f"Lembrete: Sua consulta e amanha ({data_fmt} as {hora_fmt})",
            corpo_html=corpo,
        )

        db.execute("UPDATE consultas SET lembrete_enviado = TRUE WHERE id = %s", (c["id"],))
        status = "enviado" if enviado else "falhou"
        logger.info(f"Lembrete consulta {c['id']} -> {c['paciente_email']}: {status}")


def _loop_scheduler():
    global _running
    while _running:
        try:
            _buscar_consultas_para_lembrete()
        except Exception as e:
            logger.error(f"Erro no scheduler de lembretes: {e}")
        time.sleep(1800)


def iniciar_scheduler():
    global _scheduler_thread, _running
    if _running:
        return
    _running = True
    _scheduler_thread = threading.Thread(target=_loop_scheduler, daemon=True)
    _scheduler_thread.start()
    logger.info("Scheduler de lembretes iniciado (verifica a cada 30 min)")


def parar_scheduler():
    global _running
    _running = False
    logger.info("Scheduler de lembretes parado")
