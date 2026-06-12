"""
extrair_ceasa.py — Extrator de cotacoes de precos do CEASA/SC

O CEASA (Central de Abastecimento) publica diariamente um PDF com os precos
praticados no mercado atacadista de hortifruti. Este script:
  1. Acessa o site do CEASA/SC e descobre automaticamente as paginas de cada mes
  2. Baixa os PDFs de cotacao de preco (um por dia util)
  3. Extrai os dados de preco de cada produto a partir das posicoes X das colunas no PDF
  4. Salva tudo em CSV separado por ano (ceasa_2025.csv, ceasa_2026.csv, ...)
  5. Nao re-baixa dias ja processados — seguro para rodar multiplas vezes por dia

Arquivos gerados em dados/:
  ceasa_AAAA.csv — cotacoes do ano, uma linha por produto por dia

Uso:
  python extrair_ceasa.py              # extrai dados novos do ano atual
  python extrair_ceasa.py --validar    # so verifica os ultimos 3 dias
  python extrair_ceasa.py --ano 2025   # backfill de um ano especifico

Dependencias (instalar uma vez):
  pip install requests pdfplumber pandas beautifulsoup4
"""

import bisect          # busca binaria eficiente para mapeamento de colunas
import io              # leitura de PDF em memoria (sem salvar arquivo temporario)
import os
import re
import sys
import time
from datetime import date, datetime

import pdfplumber      # extrai texto e posicoes de palavras de PDFs
import pandas as pd
import requests
from bs4 import BeautifulSoup  # faz o parse do HTML do site

# ============================================================
# CONFIGURACOES GLOBAIS
# ============================================================

BASE_URL = "https://www.ceasa.sc.gov.br"

# Pasta onde os CSVs serao salvos (relativa ao diretorio deste script)
DIR_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

# Headers HTTP para simular um navegador real (alguns sites bloqueiam scripts sem isso)
HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

# ============================================================
# MAPEAMENTO DE COLUNAS DO PDF POR POSICAO X
#
# Os PDFs do CEASA tem colunas fixas. Cada palavra extraida tem uma
# coordenada X (horizontal). Sabendo os limites de cada coluna, conseguimos
# classificar cada palavra na coluna correta.
#
# Como descobrir esses limites: rodar debug_layout.py para ver as posicoes
# reais das palavras em um PDF de amostra.
#
# Formato de cada entrada: ("nome_da_coluna", x_inicio, x_fim)
# ============================================================

COLUNAS_X = [
    ("produto_variedade",   0,   155),  # nome do produto + variedade
    ("classificacao",     155,   230),  # classificacao (ex: Grande, Medio)
    ("tipo",              230,   278),  # tipo de cultivo (ex: Convenci, Organico)
    ("origem",            278,   327),  # Nacional ou Importado
    ("embalagem",         327,   385),  # tipo de embalagem (ex: Caixa, Saco)
    ("conv_kg",           385,   420),  # fator de conversao para kg
    ("preco_minimo",      420,   457),  # menor preco praticado no dia (R$)
    ("preco_comum",       457,   499),  # preco mais comum (R$)
    ("preco_maximo",      499,   538),  # maior preco praticado (R$)
    ("preco_comum_kg",    538,   620),  # preco comum por kg (R$)
]

# Pre-calcula os limites de inicio para busca binaria (mais rapido que loop)
_X_STARTS = [x_ini for _, x_ini, _ in COLUNAS_X]


def coluna_por_x(x0: float) -> str | None:
    """
    Dado um valor X de uma palavra no PDF, retorna o nome da coluna correspondente.
    Usa busca binaria (bisect) — mais eficiente que percorrer a lista toda,
    importante porque esta funcao e chamada para cada palavra de cada pagina.
    """
    i = bisect.bisect_right(_X_STARTS, x0) - 1
    if i < 0:
        return None
    nome, _, x_fim = COLUNAS_X[i]
    return nome if x0 < x_fim else None


# ============================================================
# GERENCIAMENTO DE ARQUIVOS POR ANO
# ============================================================

def arquivo_do_ano(ano: int) -> str:
    """Retorna o caminho do CSV para o ano informado, criando a pasta se necessario."""
    os.makedirs(DIR_DADOS, exist_ok=True)
    return os.path.join(DIR_DADOS, f"ceasa_{ano}.csv")


# ============================================================
# DESCOBERTA AUTOMATICA DE PAGINAS DO SITE
#
# O CEASA organiza o site em: /cotacao-de-precos/ANO/MES
# Este codigo acessa a pagina do ano e extrai os links dos meses
# automaticamente — sem lista hardcoded que precisaria ser atualizada
# a cada ano novo.
# ============================================================

_RE_MES_NUM = re.compile(r"/(\d{2})-\w")  # extrai numero do mes do caminho URL


def _mes_do_path(path: str) -> int:
    """Extrai o numero do mes (1-12) de um caminho de URL do CEASA."""
    m = _RE_MES_NUM.search(path)
    return int(m.group(1)) if m else 0


def descobrir_paginas_meses(ano: int, session: requests.Session) -> list[str]:
    """
    Acessa a pagina do ano no site do CEASA e retorna a lista de caminhos
    (paths) de cada mes disponivel.

    O CEASA usa dois formatos de URL dependendo do ano:
      - Anos ate 2025: /cotacao-de-precos/2025/
      - 2026 em diante: /cotacao-de-precos/2026-1/
    Esta funcao tenta os dois formatos automaticamente.
    """
    sufixos = [str(ano), f"{ano}-1"]
    for sufixo in sufixos:
        url = f"{BASE_URL}/index.php/cotacao-de-precos/{sufixo}"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.content, "html.parser")
            seen: set[str] = set()
            paths: list[str] = []

            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Filtra links que sao paginas de mes (nao PDFs, nao raiz do ano)
                if (
                    f"cotacao-de-precos/{sufixo}/" in href
                    and "/file" not in href
                    and href not in seen
                    and _mes_do_path(href) > 0
                ):
                    seen.add(href)
                    paths.append(href)

            if paths:
                print(f"  {len(paths)} meses encontrados em /{sufixo}")
                return paths

        except Exception as e:
            print(f"  Aviso: falha ao buscar pagina do ano {ano} ({e})")

    return []


# ============================================================
# COLETA DE LINKS DE PDF EM UMA PAGINA DE MES
# ============================================================

_RE_DATA_PDF = re.compile(r"(\d{2}-\d{2}-\d{4})")  # extrai data do nome do arquivo PDF


def get_pdf_links(session: requests.Session, month_path: str) -> list[dict]:
    """
    Acessa a pagina de listagem de um mes e retorna todos os links de PDF
    disponiveis, sem duplicatas.

    O site do CEASA repete o mesmo link varias vezes no HTML (botoes, icones, texto).
    O set 'seen' garante que cada URL seja processada apenas uma vez.

    Retorna lista de dicts: [{"url": "https://...", "data": date(2026, 1, 5)}, ...]
    """
    resp = session.get(BASE_URL + month_path, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")
    seen: set[str] = set()
    links: list[dict] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        # So interessa links que apontam para arquivos PDF de cotacao
        if "/file" not in href or "cotacao" not in href:
            continue

        full_url = BASE_URL + href if href.startswith("/") else href

        # Ignora se ja vimos essa URL nesta pagina
        if full_url in seen:
            continue
        seen.add(full_url)

        # Extrai a data do nome do arquivo (ex: "05-01-2026" no caminho)
        m = _RE_DATA_PDF.search(href)
        data = datetime.strptime(m.group(1), "%d-%m-%Y").date() if m else None
        links.append({"url": full_url, "data": data})

    return links


# ============================================================
# EXTRACAO DE DADOS DO PDF
# ============================================================

_RE_UNIDADE = re.compile(r"Unidade\s*:\s*\n?\s*(.+?)(?:\n|$)")


def extract_unidade(text: str) -> str | None:
    """
    Extrai o nome da unidade CEASA do texto do cabecalho de uma pagina.
    O cabecalho tem o formato:
      '...CEASA/SC Unidade :'
      'Sao Jose'

    A cidade pode estar na linha seguinte ao "Unidade :", por isso o regex
    inclui \n? para capturar os dois casos.

    Retorna None se nao encontrar (a funcao chamadora mantem o ultimo valor).
    """
    m = _RE_UNIDADE.search(text)
    if m:
        nome = m.group(1).strip()
        if nome:
            return nome
    return None


def to_float(text: str) -> float:
    """Converte string de preco brasileiro (ex: '12,50') para float."""
    return float(text.replace(",", "."))


def parse_row(cols: dict) -> dict | None:
    """
    Recebe um dicionario com as colunas de uma linha do PDF e tenta converter
    para um registro de dados valido.

    Retorna None se:
    - Faltar produto, preco/kg ou preco minimo (linha incompleta)
    - Os valores nao forem numericos (linha de cabecalho ou rodape)
    - Os precos forem zero ou negativos (linha invalida)
    """
    produto      = cols.get("produto_variedade", "").strip()
    preco_kg_str = cols.get("preco_comum_kg", "").strip()
    preco_min_str = cols.get("preco_minimo", "").strip()

    if not produto or not preco_kg_str or not preco_min_str:
        return None

    try:
        preco_kg  = to_float(preco_kg_str)
        preco_min = to_float(preco_min_str)
        preco_com = to_float(cols.get("preco_comum", "0"))
        preco_max = to_float(cols.get("preco_maximo", "0"))
    except ValueError:
        return None  # linha de cabecalho como "Minimo", "Kg", etc.

    if preco_kg <= 0 or preco_min <= 0:
        return None

    return {
        "produto_variedade": produto,
        "classificacao":     cols.get("classificacao", "").strip(),
        "tipo":              cols.get("tipo", "").strip(),
        "origem":            cols.get("origem", "").strip(),
        "embalagem":         cols.get("embalagem", "").strip(),
        "conv_kg":           cols.get("conv_kg", "").strip(),
        "preco_minimo":      preco_min,
        "preco_comum":       preco_com,
        "preco_maximo":      preco_max,
        "preco_comum_kg":    preco_kg,
    }


def extract_from_pdf(pdf_bytes: bytes, data_ref) -> list[dict]:
    """
    Extrai todos os registros de preco de um PDF.

    Estrategia:
    1. Para cada pagina, le as palavras com suas posicoes X e Y
    2. Agrupa palavras na mesma linha (Y similar, tolerancia de 6 pontos)
    3. Para cada linha, classifica cada palavra na coluna correta pelo X
    4. Tenta converter a linha em um registro de preco valido

    A unidade CEASA (ex: 'Sao Jose') e lida do cabecalho de cada pagina
    separadamente — suporta PDFs com multiplas unidades no futuro.
    """
    rows = []
    unidade_atual = "Desconhecida"

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            # Atualiza unidade se o cabecalho desta pagina indicar uma
            texto_pagina = page.extract_text() or ""
            unidade_pagina = extract_unidade(texto_pagina)
            if unidade_pagina:
                unidade_atual = unidade_pagina

            # extract_words agrupa caracteres em palavras usando tolerancia de posicao
            words = page.extract_words(x_tolerance=4, y_tolerance=4)

            # Agrupa palavras por linha: arredonda Y para o multiplo de 6 mais proximo
            # (palavras na mesma linha visual podem ter Y ligeiramente diferente)
            line_map: dict[int, list] = {}
            for word in words:
                y_key = round(word["top"] / 6) * 6
                line_map.setdefault(y_key, []).append(word)

            # Processa cada linha em ordem crescente de Y (de cima para baixo)
            for y_key in sorted(line_map):
                col_words: dict[str, list[str]] = {}
                for word in line_map[y_key]:
                    col = coluna_por_x(word["x0"])
                    if col:
                        col_words.setdefault(col, []).append(word["text"])

                # Une palavras de cada coluna em uma string unica
                cols = {col: " ".join(ws) for col, ws in col_words.items()}

                parsed = parse_row(cols)
                if parsed:
                    parsed["data"]    = str(data_ref)
                    parsed["unidade"] = unidade_atual
                    rows.append(parsed)

    return rows


# ============================================================
# PERSISTENCIA — LEITURA E ESCRITA DO CSV
# ============================================================

# Colunas que identificam unicamente um registro (usadas para deduplicacao)
CHAVE_DEDUP = [
    "data", "unidade", "produto_variedade", "classificacao",
    "tipo", "origem", "embalagem", "conv_kg",
]

# Ordem das colunas no CSV final
COLUNAS_CSV = [
    "data", "unidade", "produto_variedade", "classificacao",
    "tipo", "origem", "embalagem", "conv_kg",
    "preco_minimo", "preco_comum", "preco_maximo", "preco_comum_kg",
]


def load_datas_existentes(arquivo: str) -> set:
    """
    Le apenas a coluna 'data' do CSV existente e retorna um set com todas
    as datas ja presentes. Usado para evitar re-baixar dias ja processados.
    Retorna set vazio se o arquivo nao existir.
    """
    if not os.path.exists(arquivo):
        return set()
    try:
        df = pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", usecols=["data"])
        return set(df["data"].unique())
    except Exception:
        return set()


def salvar_novos_registros(arquivo: str, novos: list[dict]) -> int:
    """
    Salva novos registros no CSV usando modo append (adiciona ao final sem
    re-ler o arquivo existente). Muito mais rapido do que ler+reescrever
    o arquivo inteiro a cada execucao.

    Se o arquivo nao existir, cria com cabecalho e BOM UTF-8 (para abrir
    corretamente no Excel e Power BI).

    Retorna o numero de linhas efetivamente salvas (apos remover duplicatas
    internas nos novos dados).
    """
    df = (
        pd.DataFrame(novos, columns=COLUNAS_CSV)
        .drop_duplicates(subset=CHAVE_DEDUP)      # remove duplicatas nos novos dados
        .sort_values(["data", "unidade", "produto_variedade"])
        .reset_index(drop=True)
    )

    arquivo_existe = os.path.exists(arquivo)
    if arquivo_existe:
        # Append: sem cabecalho, sem BOM (BOM ja esta no inicio do arquivo)
        with open(arquivo, "a", encoding="utf-8", newline="") as f:
            df.to_csv(f, header=False, index=False, sep=";")
    else:
        # Novo arquivo: com cabecalho e BOM UTF-8
        df.to_csv(arquivo, index=False, encoding="utf-8-sig", sep=";")

    return len(df)


# ============================================================
# VALIDACAO — VERIFICA SE OS ULTIMOS DIAS TEM DADOS COMPLETOS
# ============================================================

def validar_ultimos_dias(n: int = 3) -> None:
    """
    Verifica os ultimos N dias com dados no CSV e mostra um resumo.
    Considera um dia 'INCOMPLETO' se tiver menos de 50 registros
    (um dia normal tem ~250 produtos).

    Tambem lista as unidades encontradas — util para detectar se uma
    nova unidade CEASA foi adicionada ao site.
    """
    print(f"\n{'='*60}")
    print(f"VALIDACAO - ultimos {n} dias com dados")
    print(f"{'='*60}")

    # Carrega apenas as colunas necessarias dos dois anos mais recentes
    ano_atual = date.today().year
    frames = []
    for ano in (ano_atual, ano_atual - 1):
        arq = arquivo_do_ano(ano)
        if os.path.exists(arq):
            try:
                frames.append(pd.read_csv(
                    arq, sep=";", encoding="utf-8-sig",
                    usecols=["data", "unidade", "produto_variedade"],
                ))
            except Exception as e:
                print(f"  Erro ao ler {arq}: {e}")

    if not frames:
        print("Nenhum CSV encontrado.")
        return

    df = pd.concat(frames, ignore_index=True)
    ultimas_datas = sorted(df["data"].unique(), reverse=True)[:n]

    if not ultimas_datas:
        print("CSV vazio.")
        return

    resumo = (
        df[df["data"].isin(ultimas_datas)]
        .groupby("data")
        .agg(
            registros=("produto_variedade", "count"),
            produtos=("produto_variedade", "nunique"),
            unidades=("unidade", "nunique"),
            lista_unidades=("unidade", lambda x: sorted(x.unique().tolist())),
        )
    )

    ok = True
    for d in ultimas_datas:
        r = resumo.loc[d]
        completo = r["registros"] >= 50
        if not completo:
            ok = False
        status = "OK" if completo else "INCOMPLETO"
        print(
            f"  [{d}]  {status} - "
            f"{r['registros']} registros, "
            f"{r['produtos']} produtos | "
            f"unidades: {r['lista_unidades']}"
        )

    print()
    if ok:
        print(f"Resultado: todos os {n} ultimos dias OK.")
    else:
        print("Resultado: ATENCAO - algum dia esta ausente ou incompleto.")


# ============================================================
# EXTRACAO DE UM ANO COMPLETO (INCREMENTAL OU BACKFILL)
# ============================================================

def extrair_ano(ano: int, session: requests.Session) -> None:
    """
    Extrai todos os dados de cotacao do CEASA para o ano informado.

    Para o ano corrente: verifica apenas o mes atual e o anterior
    (meses mais antigos ja foram processados e estao no CSV).

    Para anos passados (backfill): percorre todos os 12 meses.

    Pula automaticamente datas que ja existem no CSV.
    """
    hoje = date.today()
    arquivo_saida = arquivo_do_ano(ano)
    datas_existentes = load_datas_existentes(arquivo_saida)

    if datas_existentes:
        print(f"CSV ceasa_{ano}.csv: {len(datas_existentes)} datas ja presentes.")

    print(f"\nDescoberta de paginas para {ano}...")
    todas_paginas = descobrir_paginas_meses(ano, session)
    if not todas_paginas:
        print(f"Nenhuma pagina encontrada para {ano}.")
        return

    # Para o ano corrente, filtra apenas meses recentes
    # (evita fazer requests desnecessarios para meses antigos ja completos)
    if ano == hoje.year:
        mes_min = max(1, hoje.month - 1)
        paginas = [p for p in todas_paginas if _mes_do_path(p) >= mes_min]
        print(f"Ano corrente: verificando meses >= {mes_min:02d} ({len(paginas)} de {len(todas_paginas)})")
    else:
        paginas = todas_paginas  # backfill: percorre o ano inteiro

    all_rows: list[dict] = []
    erros: list[str] = []

    for month_path in paginas:
        print(f"\n{'='*60}")
        print(f"Mes: {BASE_URL + month_path}")

        try:
            pdf_links = get_pdf_links(session, month_path)
        except Exception as e:
            msg = f"  ERRO ao buscar links: {e}"
            print(msg)
            erros.append(msg)
            continue

        # Filtra PDFs do ano correto e nao processados ainda
        pdf_links = [l for l in pdf_links if l["data"] and l["data"].year == ano]
        novos = [l for l in pdf_links if str(l["data"]) not in datas_existentes]
        pulados = len(pdf_links) - len(novos)

        print(f"  {len(pdf_links)} PDFs | {pulados} ja existem | {len(novos)} novos")

        for link in novos:
            label = link["data"]
            print(f"  [{label}] baixando...", end="", flush=True)
            try:
                resp = session.get(link["url"], timeout=60)
                resp.raise_for_status()
                rows = extract_from_pdf(resp.content, link["data"])
                all_rows.extend(rows)
                # Marca como existente para nao reprocessar no mesmo run
                datas_existentes.add(str(label))
                print(f" {len(rows)} registros")
                time.sleep(0.5)  # pausa educada para nao sobrecarregar o servidor
            except Exception as e:
                msg = f" ERRO: {e}"
                print(msg)
                erros.append(f"{label}: {e}")

    print(f"\n{'='*60}")

    if not all_rows:
        print(f"Nenhum dado novo para {ano}.")
    else:
        n_salvos = salvar_novos_registros(arquivo_saida, all_rows)
        novas_datas = len({str(r["data"]) for r in all_rows})
        print(f"Salvo: {n_salvos} registros em {novas_datas} novas datas -> {os.path.basename(arquivo_saida)}")

    if erros:
        print(f"\nErros ({len(erros)}):")
        for e in erros:
            print(f"  - {e}")


# ============================================================
# PONTO DE ENTRADA
# ============================================================

def main() -> None:
    args = sys.argv[1:]

    # Modo de apenas validacao: nao baixa nada, so verifica o CSV
    if "--validar" in args:
        validar_ultimos_dias(3)
        return

    # Determina o ano alvo (padrao: ano atual)
    # Para backfill: python extrair_ceasa.py --ano 2025
    ano_alvo = date.today().year
    for i, arg in enumerate(args):
        if arg == "--ano" and i + 1 < len(args):
            ano_alvo = int(args[i + 1])
        elif arg.startswith("--ano="):
            ano_alvo = int(arg.split("=")[1])

    # Usa Session para reutilizar conexoes TCP (mais rapido que criar uma por request)
    with requests.Session() as session:
        session.headers.update(HEADERS_HTTP)
        extrair_ano(ano_alvo, session)

    validar_ultimos_dias(3)


if __name__ == "__main__":
    main()
