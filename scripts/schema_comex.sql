-- Schema CockroachDB — tabelas ComexStat (MDIC)
-- Executar uma vez antes do primeiro carregamento via carregar_comex.py
-- Conexão: vcz-comex cluster no CockroachDB (aws-us-east-1)

CREATE TABLE IF NOT EXISTS comex_pais (
    cod      INT         PRIMARY KEY,
    nome_pt  TEXT        NOT NULL,
    nome_ing TEXT,
    iso3     VARCHAR(3)
);

CREATE TABLE IF NOT EXISTS comex_ncm (
    cod       VARCHAR(8)  PRIMARY KEY,
    descricao TEXT        NOT NULL DEFAULT '',
    sh4       VARCHAR(4),
    sh2       VARCHAR(2),
    secao     VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS comex_uf (
    sigla  VARCHAR(2)  PRIMARY KEY,
    nome   VARCHAR(50),
    regiao VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS comex_via (
    cod       INT  PRIMARY KEY,
    descricao TEXT NOT NULL
);

-- Tabela fato: ~1-2M linhas/ano após agregação por (fluxo,ano,mes,ncm,pais,uf)
CREATE TABLE IF NOT EXISTS comex_fato (
    fluxo      CHAR(1)       NOT NULL,  -- 'I' importação | 'E' exportação
    ano        SMALLINT      NOT NULL,
    mes        SMALLINT      NOT NULL,
    ncm        VARCHAR(8)    NOT NULL,
    pais_cod   INT           NOT NULL,
    uf         VARCHAR(2)    NOT NULL DEFAULT '',
    kg_liquido NUMERIC(20,3) NOT NULL DEFAULT 0,
    valor_fob  NUMERIC(20,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (fluxo, ano, mes, ncm, pais_cod, uf)
);

-- Índice secundário para queries de dashboard que filtram só por ano
-- (PK começa com fluxo, então ano-only range scan precisa deste índice)
CREATE INDEX IF NOT EXISTS idx_fato_ano_mes  ON comex_fato (ano, mes);
CREATE INDEX IF NOT EXISTS idx_fato_pais_cod ON comex_fato (pais_cod);
CREATE INDEX IF NOT EXISTS idx_fato_uf       ON comex_fato (uf);
CREATE INDEX IF NOT EXISTS idx_fato_ncm      ON comex_fato (ncm);
