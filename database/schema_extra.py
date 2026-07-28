SQL_SCHEMA_EXTRA = """
-- ============================================================
-- SISGERSA - Extra Schema: Views, Functions, Triggers, Indexes
-- ============================================================
-- Este arquivo contém as definições que NÃO estão nos CREATE TABLE
-- do models.py. Essas estruturas foram criadas manualmente no DB
-- e precisam ser reproduzíveis via código.
-- ============================================================

-- ============================================================
-- FUNCTIONS (usadas pelos triggers)
-- ============================================================

CREATE OR REPLACE FUNCTION sync_endereco_paciente()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.principal = TRUE THEN
        UPDATE pacientes SET
            logradouro = NEW.logradouro,
            numero = NEW.numero,
            complemento = NEW.complemento,
            bairro = NEW.bairro,
            cidade = NEW.cidade,
            estado = NEW.estado,
            cep = NEW.cep
        WHERE id = NEW.paciente_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION sync_profissional_cargo_booleans()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.cargo IS DISTINCT FROM OLD.cargo THEN
        NEW.is_dentista := (NEW.cargo = 'dentista');
        NEW.is_medico := (NEW.cargo = 'medico');
        NEW.is_enfermeiro := (NEW.cargo = 'enfermeiro');
        NEW.is_admin_geral := (NEW.cargo = 'admin');
        NEW.is_admin_estabelecimento := (NEW.cargo = 'admin');
        NEW.is_recepcionista := (NEW.cargo = 'recepcionista');
    END IF;
    RETURN NEW;
END;
$$;

-- ============================================================
-- TRIGGERS
-- ============================================================

DROP TRIGGER IF EXISTS trg_sync_endereco_paciente ON enderecos;
CREATE TRIGGER trg_sync_endereco_paciente
AFTER INSERT OR UPDATE ON enderecos
FOR EACH ROW EXECUTE FUNCTION sync_endereco_paciente();

DROP TRIGGER IF EXISTS trg_sync_cargo_booleans ON profissionais;
CREATE TRIGGER trg_sync_cargo_booleans
BEFORE INSERT OR UPDATE ON profissionais
FOR EACH ROW EXECUTE FUNCTION sync_profissional_cargo_booleans();

-- ============================================================
-- VIEWS
-- ============================================================

CREATE OR REPLACE VIEW pacientes_com_endereco AS
SELECT
    p.id,
    p.nome,
    p.cpf,
    p.email,
    p.senha_hash,
    p.telefone,
    p.data_nascimento,
    p.foto_url,
    p.ativo,
    p.criado_em,
    p.atualizado_em,
    p.codigo_paciente,
    p.numero_documentacao,
    p.indicacao,
    p.estado_civil,
    p.profissao,
    p.nome_pai,
    p.nome_mae,
    p.logradouro,
    p.numero,
    p.complemento,
    p.bairro,
    p.cidade,
    p.estado,
    p.cep,
    p.tipo_pagamento,
    e.logradouro        AS end_logradouro,
    e.numero            AS end_numero,
    e.complemento       AS end_complemento,
    e.bairro            AS end_bairro,
    e.cidade            AS end_cidade,
    e.estado            AS end_estado,
    e.cep               AS end_cep,
    e.tipo              AS end_tipo
FROM pacientes p
LEFT JOIN enderecos e ON e.paciente_id = p.id AND e.principal = TRUE;

CREATE OR REPLACE VIEW usuarios AS
SELECT
    p.id,
    p.nome,
    p.cpf,
    p.email,
    p.senha_hash,
    p.telefone,
    p.data_nascimento,
    p.foto_url,
    p.ativo,
    p.criado_em,
    p.atualizado_em,
    CAST('paciente' AS VARCHAR) AS tipo,
    FALSE                   AS is_super,
    CAST(NULL AS VARCHAR)   AS cargo,
    p.codigo_paciente,
    p.numero_documentacao,
    p.indicacao,
    p.estado_civil,
    p.profissao,
    p.nome_pai,
    p.nome_mae,
    COALESCE(e.logradouro, p.logradouro)  AS logradouro,
    COALESCE(e.numero, p.numero)          AS numero,
    COALESCE(e.complemento, p.complemento)AS complemento,
    COALESCE(e.bairro, p.bairro)          AS bairro,
    COALESCE(e.cidade, p.cidade)          AS cidade,
    COALESCE(e.estado, p.estado)          AS estado,
    COALESCE(e.cep, p.cep)                AS cep,
    p.tipo_pagamento
FROM pacientes p
LEFT JOIN enderecos e ON e.paciente_id = p.id AND e.principal = TRUE

UNION ALL

SELECT
    pr.id,
    pr.nome,
    pr.cpf,
    pr.email,
    pr.senha_hash,
    pr.telefone,
    CAST(NULL AS DATE)      AS data_nascimento,
    pr.foto_url,
    pr.ativo,
    pr.criado_em,
    pr.atualizado_em,
    CAST(
        CASE
            WHEN pr.is_admin_geral OR pr.is_admin_estabelecimento THEN 'admin'
            WHEN pr.is_recepcionista THEN 'recepcionista'
            ELSE 'profissional'
        END AS VARCHAR
    ) AS tipo,
    pr.is_super,
    pr.cargo,
    CAST(NULL AS VARCHAR)   AS codigo_paciente,
    CAST(NULL AS VARCHAR)   AS numero_documentacao,
    CAST(NULL AS VARCHAR)   AS indicacao,
    CAST(NULL AS VARCHAR)   AS estado_civil,
    CAST(NULL AS VARCHAR)   AS profissao,
    CAST(NULL AS VARCHAR)   AS nome_pai,
    CAST(NULL AS VARCHAR)   AS nome_mae,
    CAST(NULL AS VARCHAR)   AS logradouro,
    CAST(NULL AS VARCHAR)   AS numero,
    CAST(NULL AS VARCHAR)   AS complemento,
    CAST(NULL AS VARCHAR)   AS bairro,
    CAST(NULL AS VARCHAR)   AS cidade,
    CAST(NULL AS VARCHAR)   AS estado,
    CAST(NULL AS VARCHAR)   AS cep,
    CAST(NULL AS VARCHAR)   AS tipo_pagamento
FROM profissionais pr;

-- ============================================================
-- INDEXES (não-PK, não-UNIQUE)
-- NOTA: UNIQUE indexes já estão definidos nas constraints das tabelas
-- Abaixo apenas indexes que melhoram performance de queries comuns
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_consultas_estabelecimento_data
    ON consultas (estabelecimento_id, data_hora);

CREATE INDEX IF NOT EXISTS idx_consultas_paciente
    ON consultas (paciente_usuario_id);

CREATE INDEX IF NOT EXISTS idx_consultas_profissional
    ON consultas (profissional_usuario_id);

CREATE INDEX IF NOT EXISTS idx_orcamentos_paciente
    ON orcamentos (paciente_usuario_id);

CREATE INDEX IF NOT EXISTS idx_orcamentos_estabelecimento
    ON orcamentos (estabelecimento_id);

CREATE INDEX IF NOT EXISTS idx_prontuarios_paciente
    ON prontuarios (paciente_usuario_id);

CREATE INDEX IF NOT EXISTS idx_evolucoes_prontuario
    ON evolucoes (prontuario_id);

CREATE INDEX IF NOT EXISTS idx_pagamentos_orcamento
    ON pagamentos (orcamento_id);

CREATE INDEX IF NOT EXISTS idx_enderecos_paciente
    ON enderecos (paciente_id);

CREATE INDEX IF NOT EXISTS idx_paciente_convenio_paciente
    ON paciente_convenio (paciente_usuario_id);

CREATE INDEX IF NOT EXISTS idx_profissional_estabelecimento_usuario
    ON profissional_estabelecimento (usuario_id);

CREATE INDEX IF NOT EXISTS idx_paciente_estabelecimento_usuario
    ON paciente_estabelecimento (usuario_id);
"""
