# Testes legados (pré-migração Postgres)

Testes escritos para a versão MySQL do SISGERSA. **Não rodar no Postgres do
Render (produção)** — todos apagam/reescrevem tabelas e resetam IDs.

Motivo do arquivamento:
- `test_full_functional.py`: conecta direto em MySQL localhost
  (`pymysql`, `root`/`root123`, `medical_db`) e usa `ALTER TABLE ... AUTO_INCREMENT`.
- `test_routes.py`, `test_acesso_prontuarios.py`, `test_audit.py`,
  `test_comprehensive.py`: usam `ALTER TABLE ... AUTO_INCREMENT` (sintaxe
  exclusiva do MySQL) e apagam dados.

Cobertura atual (rodam no Postgres do Render, sem apagar dados):
- `test_farmaco.py` — regressão do motor farmacológico (64 testes).
- `test_integracao_http.py` — integração HTTP via uvicorn real (15 testes).

Se for criar uma suíte de fluxos gerais (auth, agenda, orçamentos), adaptá-la
ao Postgres e rodar contra um banco descartável.
