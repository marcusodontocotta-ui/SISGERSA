from config import settings

SCHEMA_MYSQL = """

-- ============================================
-- TABELAS DE CONTROLE E AUTENTICACAO
-- ============================================

CREATE TABLE IF NOT EXISTS estabelecimentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    tipo ENUM('consultorio', 'clinica', 'hospital', 'laboratorio', 'outro') NOT NULL DEFAULT 'clinica',
    cnpj VARCHAR(18) UNIQUE,
    telefone VARCHAR(20),
    email VARCHAR(200),
    endereco TEXT,
    logo_url VARCHAR(500),
    responsavel_usuario_id INT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    email VARCHAR(200) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    tipo ENUM('admin', 'profissional', 'recepcionista', 'paciente') NOT NULL,
    is_super BOOLEAN DEFAULT FALSE,
    telefone VARCHAR(20),
    cpf VARCHAR(20),
    data_nascimento DATE,
    endereco VARCHAR(500),
    logradouro VARCHAR(255),
    numero VARCHAR(20),
    complemento VARCHAR(100),
    bairro VARCHAR(150),
    cidade VARCHAR(150),
    estado VARCHAR(5),
    cep VARCHAR(9),
    foto_url VARCHAR(500),
    codigo_paciente VARCHAR(20),
    numero_documentacao VARCHAR(50),
    indicacao VARCHAR(200),
    estado_civil VARCHAR(30),
    profissao VARCHAR(100),
    nome_pai VARCHAR(200),
    nome_mae VARCHAR(200),
    tipo_pagamento VARCHAR(20) DEFAULT 'particular',
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_codigo_paciente (codigo_paciente)
);

CREATE TABLE IF NOT EXISTS profissional_estabelecimento (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    especialidade VARCHAR(150),
    cargo VARCHAR(100),
    registro_profissional VARCHAR(50),
    cor VARCHAR(7) DEFAULT '#6c757d',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE KEY uk_prof_estab (usuario_id, estabelecimento_id)
);

CREATE TABLE IF NOT EXISTS paciente_estabelecimento (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    data_cadastro DATE DEFAULT (CURRENT_DATE),
    observacoes TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE KEY uk_pac_estab (usuario_id, estabelecimento_id)
);

-- ============================================
-- CONTROLE DE PERMISSOES DO PACIENTE
-- ============================================

CREATE TABLE IF NOT EXISTS convenios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    cnpj VARCHAR(18),
    telefone VARCHAR(20),
    email VARCHAR(200),
    plano_padrao VARCHAR(100),
    limite_consultas_mes INT DEFAULT 0,
    telefone_2 VARCHAR(20),
    contato_nome VARCHAR(200),
    contato_email VARCHAR(200),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procedimentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    descricao TEXT,
    duracao_minutos INT DEFAULT 30,
    categoria VARCHAR(100),
    codigo_tuss VARCHAR(50),
    codigo_americano VARCHAR(50),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procedimento_valor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    procedimento_id INT NOT NULL,
    convenio_id INT DEFAULT NULL,
    estabelecimento_id INT NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE KEY uk_proc_conv_estab (procedimento_id, convenio_id, estabelecimento_id)
);

CREATE TABLE IF NOT EXISTS paciente_convenio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    convenio_id INT NOT NULL,
    numero_carteirinha VARCHAR(50),
    validade DATE,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS permissoes_paciente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estabelecimento_id INT NOT NULL,
    paciente_usuario_id INT NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    pode_ver BOOLEAN DEFAULT FALSE,
    pode_criar BOOLEAN DEFAULT FALSE,
    pode_editar BOOLEAN DEFAULT FALSE,
    pode_excluir BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE KEY uk_perm_paciente (estabelecimento_id, paciente_usuario_id, modulo)
);

CREATE TABLE IF NOT EXISTS permissoes_usuario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    pode_ver BOOLEAN DEFAULT NULL,
    pode_criar BOOLEAN DEFAULT NULL,
    pode_editar BOOLEAN DEFAULT NULL,
    pode_excluir BOOLEAN DEFAULT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE KEY uk_perm_usuario (usuario_id, estabelecimento_id, modulo)
);

-- ============================================
-- PRONTUARIO E ATENDIMENTO
-- ============================================

CREATE TABLE IF NOT EXISTS prontuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    numero_prontuario VARCHAR(30),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE KEY uk_prontuario (estabelecimento_id, numero_prontuario)
);

CREATE TABLE IF NOT EXISTS consultas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    profissional_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    prontuario_id INT,
    procedimento_id INT,
    data_hora DATETIME NOT NULL,
    duracao_minutos INT DEFAULT 30,
    status ENUM('agendada', 'confirmada', 'em_andamento', 'concluida', 'cancelada', 'faltou') DEFAULT 'agendada',
    observacoes TEXT,
    lembrete_enviado BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evolucoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prontuario_id INT NOT NULL,
    consulta_id INT,
    profissional_usuario_id INT NOT NULL,
    data DATE DEFAULT (CURRENT_DATE),
    queixa_principal TEXT,
    diagnostico TEXT,
    procedimento_realizado TEXT,
    observacoes TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (consulta_id) REFERENCES consultas(id) ON DELETE SET NULL,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tratamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    evolucao_id INT NOT NULL,
    tipo VARCHAR(100) NOT NULL,
    descricao TEXT,
    dente VARCHAR(10),
    face VARCHAR(20),
    material VARCHAR(100),
    procedimento_id INT DEFAULT NULL,
    valor DECIMAL(10, 2),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evolucao_id) REFERENCES evolucoes(id) ON DELETE CASCADE,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS imaging (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prontuario_id INT NOT NULL,
    consulta_id INT,
    tipo ENUM('raio_x', 'foto', 'scan', 'tomografia', 'outro') NOT NULL,
    descricao VARCHAR(255),
    caminho_arquivo VARCHAR(500) NOT NULL,
    data DATE DEFAULT (CURRENT_DATE),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (consulta_id) REFERENCES consultas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS odontograma (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prontuario_id INT NOT NULL,
    dente INT NOT NULL,
    face VARCHAR(20) DEFAULT NULL,
    condicao VARCHAR(30) NOT NULL,
    observacoes TEXT DEFAULT NULL,
    data_registro DATE DEFAULT (CURRENT_DATE),
    profissional_usuario_id INT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS estoque (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estabelecimento_id INT NOT NULL,
    nome VARCHAR(200) NOT NULL,
    categoria VARCHAR(100),
    quantidade DECIMAL(10, 2) DEFAULT 0,
    unidade VARCHAR(20) DEFAULT 'un',
    estoque_minimo DECIMAL(10, 2) DEFAULT 0,
    preco_unitario DECIMAL(10, 2),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE
);

-- ============================================
-- LOG DE ATIVIDADES (AUDITORIA)
-- ============================================

CREATE TABLE IF NOT EXISTS log_atividades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    estabelecimento_id INT,
    acao VARCHAR(50) NOT NULL,
    tabela VARCHAR(50),
    registro_id INT,
    detalhes JSON,
    ip_address VARCHAR(45),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE SET NULL
);

-- ============================================
-- ORCAMENTOS
-- ============================================

CREATE TABLE IF NOT EXISTS orcamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    profissional_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    convenio_id INT DEFAULT NULL,
    status ENUM('rascunho', 'enviado', 'aprovado', 'rejeitado', 'expirado', 'pago', 'pago_parcial') DEFAULT 'rascunho',
    data_validade DATE,
    observacoes TEXT,
    valor_total DECIMAL(10,2) DEFAULT 0,
    desconto DECIMAL(10,2) DEFAULT 0,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS orcamento_itens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    orcamento_id INT NOT NULL,
    procedimento_id INT DEFAULT NULL,
    descricao VARCHAR(500),
    quantidade INT DEFAULT 1,
    valor_unitario DECIMAL(10,2) NOT NULL,
    desconto DECIMAL(10,2) DEFAULT 0,
    subtotal DECIMAL(10,2) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

-- ============================================
-- TABELAS DE PAGAMENTO
-- ============================================

CREATE TABLE IF NOT EXISTS pagamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    orcamento_id INT NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    metodo ENUM('dinheiro', 'cartao_credito', 'cartao_debito', 'pix', 'transferencia', 'boleto', 'cheque', 'outros') NOT NULL,
    parcelas INT DEFAULT 1,
    valor_parcela DECIMAL(10,2) NOT NULL,
    data_pagamento DATE DEFAULT (CURRENT_DATE),
    data_vencimento DATE DEFAULT NULL,
    observacao TEXT,
    status ENUM('pago', 'pendente', 'atrasado', 'cancelado') DEFAULT 'pago',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE
);

-- ============================================
-- PLANOS E ASSINATURAS
-- ============================================

CREATE TABLE IF NOT EXISTS planos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    descricao TEXT,
    valor_mensal DECIMAL(10,2) NOT NULL DEFAULT 0,
    limite_estabelecimentos INT DEFAULT 1,
    limite_consultas_mes INT DEFAULT 100,
    limite_profissionais INT DEFAULT 3,
    limite_pacientes INT DEFAULT 50,
    limite_prontuarios INT DEFAULT 50,
    limite_orcamentos_mes INT DEFAULT 50,
    limite_procedimentos INT DEFAULT 50,
    recursos TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cupons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    descricao TEXT,
    desconto_percentual INT DEFAULT 0,
    desconto_valor DECIMAL(10,2) DEFAULT 0,
    plano_destino VARCHAR(50) DEFAULT 'basico',
    validade_dias INT DEFAULT 30,
    max_usos INT DEFAULT 0,
    usos_atual INT DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- CONFIGURACAO DO SISTEMA
-- ============================================

CREATE TABLE IF NOT EXISTS config_sistema (
    chave VARCHAR(100) PRIMARY KEY,
    valor VARCHAR(200) NOT NULL
);

-- ============================================
-- ANAMNESE / SINAIS VITAIS / MEDICAMENTOS
-- ============================================

CREATE TABLE IF NOT EXISTS anamnese (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_id INT NOT NULL,
    estabelecimento_id INT,
    prontuario_id INT,
    profissional_usuario_id INT,
    queixa_principal TEXT,
    historico_doenca_atual TEXT,
    impressao TEXT,
    historico_medico TEXT,
    historico_familiar TEXT,
    alergias TEXT,
    habits TEXT,
    atividade_fisica VARCHAR(255),
    tabagismo VARCHAR(20),
    etilismo VARCHAR(20),
    refeicoes_dia INT,
    horas_sono DECIMAL(4,1),
    gestante BOOLEAN,
    numero_gestacoes INT,
    observacoes TEXT,
    revisao_sistemas JSON,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_anamnese_paciente (paciente_id)
);

CREATE TABLE IF NOT EXISTS sinais_vitais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_id INT NOT NULL,
    prontuario_id INT,
    profissional_usuario_id INT,
    pressao_sistolica INT,
    pressao_diastolica INT,
    frequencia_cardiaca INT,
    frequencia_respiratoria INT,
    saturacao_oxigenio DOUBLE,
    temperatura DOUBLE,
    glicemia DOUBLE,
    peso DOUBLE,
    observacoes TEXT,
    aferido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_sinais_paciente (paciente_id)
);

CREATE TABLE IF NOT EXISTS medicamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    principio_ativo VARCHAR(255),
    anvisa_registro VARCHAR(20),
    classe_terapeutica VARCHAR(255),
    fabricante VARCHAR(255),
    situacao_registro VARCHAR(20),
    UNIQUE KEY uq_medicamentos_nome (nome)
);

CREATE TABLE IF NOT EXISTS paciente_medicamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_id INT NOT NULL,
    medicamento_id INT,
    nome_medicamento VARCHAR(255),
    dose VARCHAR(100),
    frequencia VARCHAR(100),
    via VARCHAR(100),
    observacoes TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_pac_med_paciente (paciente_id)
);

CREATE TABLE IF NOT EXISTS exames_laboratoriais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paciente_id INT NOT NULL,
    prontuario_id INT,
    profissional_usuario_id INT,
    nome_exame VARCHAR(255) NOT NULL,
    data_solicitacao DATE,
    data_resultado DATE,
    resultado VARCHAR(255),
    valor_referencia VARCHAR(255),
    laboratorio VARCHAR(255),
    observacoes TEXT,
    arquivo_pdf LONGTEXT,
    arquivo_nome VARCHAR(255),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_exames_paciente (paciente_id)
);

"""

SCHEMA_POSTGRESQL = """

-- ============================================
-- TABELAS DE CONTROLE E AUTENTICACAO
-- ============================================

CREATE TABLE IF NOT EXISTS estabelecimentos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'clinica' CHECK (tipo IN ('consultorio', 'clinica', 'hospital', 'laboratorio', 'outro')),
    cnpj VARCHAR(18) UNIQUE,
    telefone VARCHAR(20),
    email VARCHAR(200),
    endereco TEXT,
    logo_url VARCHAR(500),
    responsavel_usuario_id INT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    email VARCHAR(200) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('admin', 'profissional', 'recepcionista', 'paciente')),
    is_super BOOLEAN DEFAULT FALSE,
    telefone VARCHAR(20),
    cpf VARCHAR(20),
    data_nascimento DATE,
    endereco VARCHAR(500),
    logradouro VARCHAR(255),
    numero VARCHAR(20),
    complemento VARCHAR(100),
    bairro VARCHAR(150),
    cidade VARCHAR(150),
    estado VARCHAR(5),
    cep VARCHAR(9),
    foto_url VARCHAR(500),
    codigo_paciente VARCHAR(20),
    numero_documentacao VARCHAR(50),
    indicacao VARCHAR(200),
    estado_civil VARCHAR(30),
    profissao VARCHAR(100),
    nome_pai VARCHAR(200),
    nome_mae VARCHAR(200),
    tipo_pagamento VARCHAR(20) DEFAULT 'particular',
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (codigo_paciente)
);

CREATE TABLE IF NOT EXISTS profissional_estabelecimento (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    especialidade VARCHAR(150),
    cargo VARCHAR(100),
    registro_profissional VARCHAR(50),
    cor VARCHAR(7) DEFAULT '#6c757d',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE (usuario_id, estabelecimento_id)
);

CREATE TABLE IF NOT EXISTS paciente_estabelecimento (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    data_cadastro DATE DEFAULT CURRENT_DATE,
    observacoes TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE (usuario_id, estabelecimento_id)
);

-- ============================================
-- CONTROLE DE PERMISSOES
-- ============================================

CREATE TABLE IF NOT EXISTS convenios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    cnpj VARCHAR(18),
    telefone VARCHAR(20),
    email VARCHAR(200),
    plano_padrao VARCHAR(100),
    limite_consultas_mes INT DEFAULT 0,
    telefone_2 VARCHAR(20),
    contato_nome VARCHAR(200),
    contato_email VARCHAR(200),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procedimentos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    descricao TEXT,
    duracao_minutos INT DEFAULT 30,
    categoria VARCHAR(100),
    codigo_tuss VARCHAR(50),
    codigo_americano VARCHAR(50),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS procedimento_valor (
    id SERIAL PRIMARY KEY,
    procedimento_id INT NOT NULL,
    convenio_id INT DEFAULT NULL,
    estabelecimento_id INT NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE (procedimento_id, convenio_id, estabelecimento_id)
);

CREATE TABLE IF NOT EXISTS paciente_convenio (
    id SERIAL PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    convenio_id INT NOT NULL,
    numero_carteirinha VARCHAR(50),
    validade DATE,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS permissoes_paciente (
    id SERIAL PRIMARY KEY,
    estabelecimento_id INT NOT NULL,
    paciente_usuario_id INT NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    pode_ver BOOLEAN DEFAULT FALSE,
    pode_criar BOOLEAN DEFAULT FALSE,
    pode_editar BOOLEAN DEFAULT FALSE,
    pode_excluir BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE (estabelecimento_id, paciente_usuario_id, modulo)
);

CREATE TABLE IF NOT EXISTS permissoes_usuario (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    pode_ver BOOLEAN DEFAULT NULL,
    pode_criar BOOLEAN DEFAULT NULL,
    pode_editar BOOLEAN DEFAULT NULL,
    pode_excluir BOOLEAN DEFAULT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE (usuario_id, estabelecimento_id, modulo)
);

-- ============================================
-- PRONTUARIO E ATENDIMENTO
-- ============================================

CREATE TABLE IF NOT EXISTS prontuarios (
    id SERIAL PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    numero_prontuario VARCHAR(30),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    UNIQUE (estabelecimento_id, numero_prontuario)
);

CREATE TABLE IF NOT EXISTS consultas (
    id SERIAL PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    profissional_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    prontuario_id INT,
    procedimento_id INT,
    data_hora TIMESTAMP NOT NULL,
    duracao_minutos INT DEFAULT 30,
    status VARCHAR(20) DEFAULT 'agendada' CHECK (status IN ('agendada', 'confirmada', 'em_andamento', 'concluida', 'cancelada', 'faltou')),
    observacoes TEXT,
    lembrete_enviado BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evolucoes (
    id SERIAL PRIMARY KEY,
    prontuario_id INT NOT NULL,
    consulta_id INT,
    profissional_usuario_id INT NOT NULL,
    data DATE DEFAULT CURRENT_DATE,
    queixa_principal TEXT,
    diagnostico TEXT,
    procedimento_realizado TEXT,
    observacoes TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (consulta_id) REFERENCES consultas(id) ON DELETE SET NULL,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tratamentos (
    id SERIAL PRIMARY KEY,
    evolucao_id INT NOT NULL,
    tipo VARCHAR(100) NOT NULL,
    descricao TEXT,
    dente VARCHAR(10),
    face VARCHAR(20),
    material VARCHAR(100),
    procedimento_id INT DEFAULT NULL,
    valor DECIMAL(10, 2),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evolucao_id) REFERENCES evolucoes(id) ON DELETE CASCADE,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS imaging (
    id SERIAL PRIMARY KEY,
    prontuario_id INT NOT NULL,
    consulta_id INT,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('raio_x', 'foto', 'scan', 'tomografia', 'outro')),
    descricao VARCHAR(255),
    caminho_arquivo VARCHAR(500) NOT NULL,
    data DATE DEFAULT CURRENT_DATE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (consulta_id) REFERENCES consultas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS odontograma (
    id SERIAL PRIMARY KEY,
    prontuario_id INT NOT NULL,
    dente INT NOT NULL,
    face VARCHAR(20) DEFAULT NULL,
    condicao VARCHAR(30) NOT NULL,
    observacoes TEXT DEFAULT NULL,
    data_registro DATE DEFAULT CURRENT_DATE,
    profissional_usuario_id INT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prontuario_id) REFERENCES prontuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS estoque (
    id SERIAL PRIMARY KEY,
    estabelecimento_id INT NOT NULL,
    nome VARCHAR(200) NOT NULL,
    categoria VARCHAR(100),
    quantidade DECIMAL(10, 2) DEFAULT 0,
    unidade VARCHAR(20) DEFAULT 'un',
    estoque_minimo DECIMAL(10, 2) DEFAULT 0,
    preco_unitario DECIMAL(10, 2),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE
);

-- ============================================
-- LOG DE ATIVIDADES (AUDITORIA)
-- ============================================

CREATE TABLE IF NOT EXISTS log_atividades (
    id SERIAL PRIMARY KEY,
    usuario_id INT,
    estabelecimento_id INT,
    acao VARCHAR(50) NOT NULL,
    tabela VARCHAR(50),
    registro_id INT,
    detalhes JSONB,
    ip_address VARCHAR(45),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE SET NULL
);

-- ============================================
-- ORCAMENTOS
-- ============================================

CREATE TABLE IF NOT EXISTS orcamentos (
    id SERIAL PRIMARY KEY,
    paciente_usuario_id INT NOT NULL,
    profissional_usuario_id INT NOT NULL,
    estabelecimento_id INT NOT NULL,
    convenio_id INT DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'enviado', 'aprovado', 'rejeitado', 'expirado', 'pago', 'pago_parcial')),
    data_validade DATE,
    observacoes TEXT,
    valor_total DECIMAL(10,2) DEFAULT 0,
    desconto DECIMAL(10,2) DEFAULT 0,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (profissional_usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id) ON DELETE CASCADE,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS orcamento_itens (
    id SERIAL PRIMARY KEY,
    orcamento_id INT NOT NULL,
    procedimento_id INT DEFAULT NULL,
    descricao VARCHAR(500),
    quantidade INT DEFAULT 1,
    valor_unitario DECIMAL(10,2) NOT NULL,
    desconto DECIMAL(10,2) DEFAULT 0,
    subtotal DECIMAL(10,2) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
    FOREIGN KEY (procedimento_id) REFERENCES procedimentos(id) ON DELETE SET NULL
);

-- ============================================
-- TABELAS DE PAGAMENTO
-- ============================================

CREATE TABLE IF NOT EXISTS pagamentos (
    id SERIAL PRIMARY KEY,
    orcamento_id INT NOT NULL,
    valor DECIMAL(10,2) NOT NULL,
    metodo VARCHAR(20) NOT NULL CHECK (metodo IN ('dinheiro', 'cartao_credito', 'cartao_debito', 'pix', 'transferencia', 'boleto', 'cheque', 'outros')),
    parcelas INT DEFAULT 1,
    valor_parcela DECIMAL(10,2) NOT NULL,
    data_pagamento DATE DEFAULT CURRENT_DATE,
    data_vencimento DATE DEFAULT NULL,
    observacao TEXT,
    status VARCHAR(20) DEFAULT 'pago' CHECK (status IN ('pago', 'pendente', 'atrasado', 'cancelado')),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE
);

-- ============================================
-- PLANOS E ASSINATURAS
-- ============================================

CREATE TABLE IF NOT EXISTS planos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    descricao TEXT,
    valor_mensal DECIMAL(10,2) NOT NULL DEFAULT 0,
    limite_estabelecimentos INT DEFAULT 1,
    limite_consultas_mes INT DEFAULT 100,
    limite_profissionais INT DEFAULT 3,
    limite_pacientes INT DEFAULT 50,
    limite_prontuarios INT DEFAULT 50,
    limite_orcamentos_mes INT DEFAULT 50,
    limite_procedimentos INT DEFAULT 50,
    recursos TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- CUPONS DE DESCONTO
-- ============================================

CREATE TABLE IF NOT EXISTS cupons (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    descricao TEXT,
    desconto_percentual INT DEFAULT 0 CHECK (desconto_percentual >= 0 AND desconto_percentual <= 100),
    desconto_valor DECIMAL(10,2) DEFAULT 0,
    plano_destino VARCHAR(50) DEFAULT 'basico',
    validade_dias INT DEFAULT 30,
    max_usos INT DEFAULT 0,
    usos_atual INT DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS cupom_id INT REFERENCES cupons(id);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS plano_id INT REFERENCES planos(id);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS plano_expira_em DATE;
ALTER TABLE profissional_estabelecimento ADD COLUMN IF NOT EXISTS cor VARCHAR(7) DEFAULT '#6c757d';
ALTER TABLE consultas ADD COLUMN IF NOT EXISTS lembrete_enviado BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigo_paciente VARCHAR(20);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS numero_documentacao VARCHAR(50);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS indicacao VARCHAR(200);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS estado_civil VARCHAR(30);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS profissao VARCHAR(100);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nome_pai VARCHAR(200);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nome_mae VARCHAR(200);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tipo_pagamento VARCHAR(20) DEFAULT 'particular';

CREATE TABLE IF NOT EXISTS config_sistema (
    chave VARCHAR(100) PRIMARY KEY,
    valor VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS medicamentos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    principio_ativo VARCHAR(255),
    anvisa_registro VARCHAR(20),
    classe_terapeutica VARCHAR(255),
    fabricante VARCHAR(255),
    situacao_registro VARCHAR(20),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paciente_medicamentos (
    id SERIAL PRIMARY KEY,
    paciente_id INT NOT NULL,
    medicamento_id INT,
    nome_medicamento VARCHAR(255),
    dose VARCHAR(100),
    frequencia VARCHAR(100),
    via VARCHAR(100),
    observacoes TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pac_med_paciente ON paciente_medicamentos (paciente_id);

-- ============================================
-- BASE DE CONHECIMENTO FARMACOLOGICA (FASE 0)
-- ============================================

CREATE TABLE IF NOT EXISTS principios_ativos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    atc_codigo VARCHAR(20),
    classe_terapeutica VARCHAR(255),
    indicacao TEXT,
    posologia TEXT,
    contra_indicacoes TEXT,
    mecanismo_acao TEXT,
    fonte VARCHAR(100),
    revisado_em TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS medicamento_principios (
    id SERIAL PRIMARY KEY,
    medicamento_id INT NOT NULL REFERENCES medicamentos(id) ON DELETE CASCADE,
    principio_ativo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    UNIQUE (medicamento_id, principio_ativo_id)
);

CREATE TABLE IF NOT EXISTS sintomas (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    categoria VARCHAR(100),
    cid10 VARCHAR(20),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicacoes (
    id SERIAL PRIMARY KEY,
    principio_ativo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    sintoma_id INT NOT NULL REFERENCES sintomas(id) ON DELETE CASCADE,
    linha_tratamento INT DEFAULT 1,
    eficacia INT DEFAULT 5,
    observacoes TEXT,
    UNIQUE (principio_ativo_id, sintoma_id)
);

CREATE TABLE IF NOT EXISTS efeitos_colaterais (
    id SERIAL PRIMARY KEY,
    principio_ativo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,
    probabilidade NUMERIC(5,2),
    severidade VARCHAR(20) DEFAULT 'leve',
    UNIQUE (principio_ativo_id, nome)
);

CREATE TABLE IF NOT EXISTS interacoes_medicamentosas (
    id SERIAL PRIMARY KEY,
    medicamento_a_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    medicamento_b_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    severidade VARCHAR(20) NOT NULL DEFAULT 'moderada',
    descricao TEXT,
    conduta TEXT,
    fonte VARCHAR(100),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (medicamento_a_id, medicamento_b_id),
    CHECK (medicamento_a_id < medicamento_b_id)
);

CREATE TABLE IF NOT EXISTS contra_indicacoes (
    id SERIAL PRIMARY KEY,
    principio_ativo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    descricao VARCHAR(255) NOT NULL,
    severidade VARCHAR(20) DEFAULT 'moderada',
    UNIQUE (principio_ativo_id, tipo, descricao)
);

CREATE TABLE IF NOT EXISTS principio_sinonimos (
    id SERIAL PRIMARY KEY,
    sinonimo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    canonico_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
    UNIQUE (sinonimo_id, canonico_id)
);

"""


SCHEMA_ALTER_MYSQL = [
    "ALTER TABLE estabelecimentos ADD COLUMN plano_id INT NULL",
    "ALTER TABLE estabelecimentos ADD COLUMN plano_expira_em DATE NULL",
    "ALTER TABLE estabelecimentos ADD COLUMN cupom_id INT NULL",
    "ALTER TABLE planos ADD COLUMN limite_prontuarios INT DEFAULT 50",
    "ALTER TABLE planos ADD COLUMN limite_orcamentos_mes INT DEFAULT 50",
    "ALTER TABLE planos ADD COLUMN limite_procedimentos INT DEFAULT 50",
    "ALTER TABLE profissional_estabelecimento ADD COLUMN cor VARCHAR(7) DEFAULT '#6c757d'",
    "ALTER TABLE consultas ADD COLUMN lembrete_enviado BOOLEAN DEFAULT FALSE",
    "ALTER TABLE procedimentos ADD COLUMN categoria VARCHAR(100) NULL",
    "ALTER TABLE procedimentos ADD COLUMN codigo_tuss VARCHAR(50) NULL",
    "ALTER TABLE procedimentos ADD COLUMN codigo_americano VARCHAR(50) NULL",
    "ALTER TABLE orcamentos ADD COLUMN desconto DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE usuarios ADD COLUMN logradouro VARCHAR(255) NULL",
    "ALTER TABLE usuarios ADD COLUMN numero VARCHAR(20) NULL",
    "ALTER TABLE usuarios ADD COLUMN complemento VARCHAR(100) NULL",
    "ALTER TABLE usuarios ADD COLUMN bairro VARCHAR(150) NULL",
    "ALTER TABLE usuarios ADD COLUMN cidade VARCHAR(150) NULL",
    "ALTER TABLE usuarios ADD COLUMN estado VARCHAR(5) NULL",
    "ALTER TABLE usuarios ADD COLUMN cep VARCHAR(9) NULL",
    "ALTER TABLE usuarios ADD COLUMN tipo_pagamento VARCHAR(20) DEFAULT 'particular'",
    "ALTER TABLE estabelecimentos ADD COLUMN responsavel_usuario_id INT NULL",
    "ALTER TABLE convenios ADD COLUMN plano_padrao VARCHAR(100) NULL",
    "ALTER TABLE convenios ADD COLUMN limite_consultas_mes INT DEFAULT 0",
    "ALTER TABLE convenios ADD COLUMN telefone_2 VARCHAR(20) NULL",
    "ALTER TABLE convenios ADD COLUMN contato_nome VARCHAR(200) NULL",
    "ALTER TABLE convenios ADD COLUMN contato_email VARCHAR(200) NULL",
]

def _get_mysql_alter_safe():
    """Return ALTER statements that safely check column existence via Python."""
    return [
        ("usuarios", "codigo_paciente", "VARCHAR(20)"),
        ("usuarios", "numero_documentacao", "VARCHAR(50)"),
        ("usuarios", "indicacao", "VARCHAR(200)"),
        ("usuarios", "estado_civil", "VARCHAR(30)"),
        ("usuarios", "profissao", "VARCHAR(100)"),
        ("usuarios", "nome_pai", "VARCHAR(200)"),
        ("usuarios", "nome_mae", "VARCHAR(200)"),
        ("usuarios", "tipo_pagamento", "VARCHAR(20)"),
        ("usuarios", "logradouro", "VARCHAR(255)"),
        ("usuarios", "numero", "VARCHAR(20)"),
        ("usuarios", "complemento", "VARCHAR(100)"),
        ("usuarios", "bairro", "VARCHAR(150)"),
        ("usuarios", "cidade", "VARCHAR(150)"),
        ("usuarios", "estado", "VARCHAR(5)"),
        ("usuarios", "cep", "VARCHAR(9)"),
    ]


def get_schema():
    if settings.DB_ENGINE == "postgresql":
        return SCHEMA_POSTGRESQL
    return SCHEMA_MYSQL


def get_alter_tables():
    if settings.DB_ENGINE == "postgresql":
        return []
    return SCHEMA_ALTER_MYSQL


SCHEMA_SQL = SCHEMA_MYSQL
