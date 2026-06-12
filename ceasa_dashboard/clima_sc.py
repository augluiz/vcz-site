"""
clima_sc.py — Coleta de dados meteorologicos diarios para Santa Catarina

Combina dados historicos observados com previsao do tempo, incluindo
fatores relevantes para producao agricola (geada, neve, granizo, sol, etc.)
e fenomenos astronomicos (fase da lua, nascer/por do sol).

Fonte: Open-Meteo (open-meteo.com) — gratuito, sem cadastro, sem API key.
       Historico disponivel desde 1940. Previsao ate 16 dias a frente.

Arquivos gerados em dados/:
  clima_sc_historico.csv   — dados observados dia a dia (append-only, nunca sobrescreve)
  clima_sc_previsao.csv    — previsao dos proximos 16 dias (sobrescrito a cada execucao)
  previsoes_historico.csv  — arquivo de previsoes passadas para analise de acuracia

Como usar a analise de acuracia:
  A cada execucao, o script salva em previsoes_historico.csv o que foi
  previsto para os proximos 7 dias. Apos 7 dias, cruze com clima_sc_historico.csv
  (data_alvo = data) para ver se a previsao acertou.

Cidades monitoradas (zonas agricolas de SC):
  - Sao Jose          — litoral, Grande Florianopolis, onde fica o CEASA
  - Lages             — Serra Catarinense, regiao de maca, propensa a geada/neve
  - Chapeco           — Oeste Catarinense, graos, suinocultura, avicultura

Uso:
  python clima_sc.py           # atualiza historico + previsao
  python clima_sc.py --validar # verifica cobertura recente sem baixar dados

Dependencias (instalar uma vez):
  pip install requests pandas
"""

import math    # para calculo de fase da lua (funcao cosseno)
import os
import sys
from datetime import date, timedelta

import pandas as pd
import requests

# ============================================================
# CONFIGURACOES GLOBAIS
# ============================================================

DIR_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

# Cidades de SC que representam as principais zonas agriclimaticas
# lat/lon sao as coordenadas geograficas usadas pela API do Open-Meteo
CIDADES = [
    {"nome": "Sao Jose",  "lat": -27.6138, "lon": -48.6358, "regiao": "Grande Florianopolis"},
    {"nome": "Lages",     "lat": -27.8181, "lon": -50.3261, "regiao": "Serra Catarinense"},
    {"nome": "Chapeco",   "lat": -27.1008, "lon": -52.6161, "regiao": "Oeste Catarinense"},
]
# Nota: nomes sem acentos para evitar problemas de encoding em diferentes sistemas

# Primeiro ano de dados historicos a coletar
ANO_INICIO = 2025

# Variaveis meteorologicas solicitadas a API (formato exigido pelo Open-Meteo)
# Documentacao completa: https://open-meteo.com/en/docs
VARIAVEIS_API = ",".join([
    "temperature_2m_max",           # temperatura maxima do dia (C)
    "temperature_2m_min",           # temperatura minima do dia (C)
    "temperature_2m_mean",          # temperatura media do dia (C)
    "apparent_temperature_max",     # sensacao termica maxima (C)
    "apparent_temperature_min",     # sensacao termica minima (C)
    "precipitation_sum",            # precipitacao total: chuva + neve (mm)
    "rain_sum",                     # chuva (mm, sem neve)
    "snowfall_sum",                 # neve (cm)
    "precipitation_hours",          # horas com precipitacao no dia
    "sunshine_duration",            # duracao do sol (segundos — convertido para horas no CSV)
    "shortwave_radiation_sum",      # radiacao solar total (MJ/m2)
    "wind_speed_10m_max",           # velocidade maxima do vento a 10m (km/h)
    "wind_gusts_10m_max",           # rajada maxima de vento (km/h)
    "wind_direction_10m_dominant",  # direcao predominante do vento (graus, 0=Norte)
    "et0_fao_evapotranspiration",   # evapotranspiracao de referencia FAO (mm) — importante para irrigacao
    "weather_code",                 # codigo WMO: identifica o fenomeno (chuva, neve, tempestade, etc.)
    "sunrise",                      # horario do nascer do sol (HH:MM)
    "sunset",                       # horario do por do sol (HH:MM)
])

# Colunas do CSV de historico e previsao (sem colunas extras de controle)
COLUNAS_HISTORICO = [
    "data", "cidade", "regiao", "lat", "lon",
    "temp_min", "temp_max", "temp_media",
    "sensacao_min", "sensacao_max",
    "precipitacao_mm", "chuva_mm", "neve_cm", "horas_precipitacao",
    "horas_sol", "radiacao_solar_mj",
    "vento_max_kmh", "rajada_max_kmh", "direcao_vento_graus",
    "evapotranspiracao_mm",
    "codigo_tempo",
    "geada",        # 1 se temp_min <= 0C, 0 caso contrario
    "neve",         # 1 se nevou, 0 caso contrario
    "granizo",      # 1 se codigo WMO indica granizo (96 ou 99)
    "tempestade",   # 1 se codigo WMO indica tempestade (95-99)
    "chuva_intensa", # 1 se precipitacao >= 20mm no dia
    "nascer_sol", "por_sol",
    "fase_lua", "iluminacao_lua_pct",
]

# Colunas extras adicionadas no CSV de previsao
COLUNAS_PREVISAO = COLUNAS_HISTORICO + [
    "dias_a_frente",  # quantos dias a frente da data de execucao
    "data_execucao",  # quando esta previsao foi gerada
]

# Variaveis salvas no arquivo de acuracia de previsao
VARS_ACURACIA = [
    "temp_min", "temp_max", "temp_media",
    "precipitacao_mm", "neve_cm", "neve", "granizo", "tempestade", "geada",
]

COLUNAS_ACURACIA = (
    ["data_geracao", "data_alvo", "cidade", "dias_a_frente"]
    + [f"{v}_prev" for v in VARS_ACURACIA]  # sufixo _prev indica que e previsao
)

# Caminhos dos arquivos de saida
ARQ_HISTORICO = os.path.join(DIR_DADOS, "clima_sc_historico.csv")
ARQ_PREVISAO  = os.path.join(DIR_DADOS, "clima_sc_previsao.csv")
ARQ_ACURACIA  = os.path.join(DIR_DADOS, "previsoes_historico.csv")

# Codigos WMO que indicam eventos meteorologicos especificos
# Referencia: https://open-meteo.com/en/docs (secao Weather Interpretation Codes)
_WMO_GRANIZO    = {96, 99}                        # tempestade com granizo
_WMO_TEMPESTADE = {95, 96, 97, 99}               # qualquer tipo de tempestade
_WMO_NEVE       = set(range(71, 78)) | {85, 86}  # queda de neve ou granizo de neve


# ============================================================
# FASE DA LUA — CALCULO ALGORITMICO
#
# Usa o ciclo sinodico da lua (29,53 dias) para calcular a fase
# a partir de uma data de referencia conhecida (lua nova de 2000-01-06).
# Nao precisa de nenhuma biblioteca extra — pura matematica.
# ============================================================

def _julian_day(d: date) -> float:
    """
    Converte uma data para Dia Juliano (JD), sistema numerico astronomico
    que conta dias a partir de 1 de janeiro de 4713 a.C.
    Necessario para o calculo da fase da lua.
    """
    y, m, day = d.year, d.month, d.day
    if m <= 2:
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + B - 1524.5


def fase_lua_info(d: date) -> tuple[str, float]:
    """
    Calcula a fase da lua para uma data e retorna:
      - nome da fase (ex: 'Lua Cheia', 'Quarto Crescente')
      - porcentagem de iluminacao (0=lua nova, 100=lua cheia)

    O calculo usa o ciclo sinodico (29,53 dias):
      0%  -> Lua Nova (sem iluminacao visivel)
      25% -> Quarto Crescente
      50% -> Lua Cheia (iluminacao maxima)
      75% -> Quarto Minguante
    """
    # Posicao no ciclo atual (0.0 a 1.0)
    dias_no_ciclo = (_julian_day(d) - 2451549.5) % 29.53058867
    fase = dias_no_ciclo / 29.53058867

    # Iluminacao visual da lua (funcao cosseno do angulo de fase)
    iluminacao = round((1 - math.cos(2 * math.pi * fase)) / 2 * 100, 1)

    # Classificacao em 8 fases baseada na posicao no ciclo
    if fase < 0.0625 or fase >= 0.9375:
        nome = "Lua Nova"
    elif fase < 0.1875:
        nome = "Crescente"
    elif fase < 0.3125:
        nome = "Quarto Crescente"
    elif fase < 0.4375:
        nome = "Gibosa Crescente"
    elif fase < 0.5625:
        nome = "Lua Cheia"
    elif fase < 0.6875:
        nome = "Gibosa Minguante"
    elif fase < 0.8125:
        nome = "Quarto Minguante"
    else:
        nome = "Minguante"

    return nome, iluminacao


# ============================================================
# CHAMADAS A API OPEN-METEO
#
# Open-Meteo oferece dois endpoints:
#   archive-api: dados historicos observados (ERA5 reanalysis)
#   api:         previsao dos proximos dias
#
# Ambos retornam JSON com estrutura:
#   {"daily": {"time": [...], "temperature_2m_max": [...], ...}}
# ============================================================

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "CEASA-Dashboard/1.0"})

# Parametros comuns a todos os requests
_BASE_PARAMS = {
    "daily":           VARIAVEIS_API,
    "timezone":        "America/Sao_Paulo",  # retorna horarios no fuso de Brasilia
    "wind_speed_unit": "kmh",                # velocidade em km/h (padrao e m/s)
}


def _get_meteo(endpoint: str, lat: float, lon: float, extra: dict) -> dict:
    """Faz um GET para o Open-Meteo com os parametros combinados."""
    resp = _SESSION.get(
        endpoint,
        params={"latitude": lat, "longitude": lon, **_BASE_PARAMS, **extra},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_historico_api(lat: float, lon: float, inicio: date, fim: date) -> dict:
    """Busca dados historicos observados para um periodo especifico."""
    return _get_meteo(
        "https://archive-api.open-meteo.com/v1/archive",
        lat, lon,
        {"start_date": str(inicio), "end_date": str(fim)},
    )


def fetch_previsao_api(lat: float, lon: float, dias: int = 16) -> dict:
    """Busca a previsao do tempo para os proximos N dias (maximo 16)."""
    return _get_meteo(
        "https://api.open-meteo.com/v1/forecast",
        lat, lon,
        {"forecast_days": dias},
    )


# ============================================================
# CONVERSAO DA RESPOSTA DA API PARA LINHAS DO CSV
# ============================================================

def _hora(val) -> str | None:
    """
    Extrai apenas o horario HH:MM de uma string ISO como '2026-06-07T06:23'.
    O Open-Meteo retorna sunrise/sunset neste formato.
    """
    if val and "T" in str(val):
        return str(val).split("T")[1][:5]
    return val


def api_para_linhas(data_json: dict, cidade: str, regiao: str, lat: float, lon: float) -> list[dict]:
    """
    Converte a resposta JSON do Open-Meteo em uma lista de dicts,
    onde cada dict representa um dia e esta pronto para ir ao CSV.

    Calcula campos derivados:
      - geada: temperatura minima <= 0C
      - neve: snowfall > 0
      - granizo/tempestade: baseado no codigo WMO
      - chuva_intensa: precipitacao >= 20mm
      - horas_sol: converte segundos para horas
      - fase_lua: calculada localmente (sem API)
    """
    daily = data_json.get("daily", {})
    datas = daily.get("time", [])
    n     = len(datas)
    rows  = []

    def _val(campo, i):
        """Atalho para acessar um valor da resposta, retorna None se ausente."""
        return daily.get(campo, [None] * n)[i]

    for i, data_str in enumerate(datas):
        d        = date.fromisoformat(data_str)
        wmo      = int(_val("weather_code", i) or 0)
        temp_min = _val("temperature_2m_min", i)
        neve_cm  = _val("snowfall_sum", i) or 0
        precip   = _val("precipitation_sum", i) or 0
        fase, ilum = fase_lua_info(d)

        rows.append({
            "data":               data_str,
            "cidade":             cidade,
            "regiao":             regiao,
            "lat":                lat,
            "lon":                lon,
            "temp_min":           temp_min,
            "temp_max":           _val("temperature_2m_max", i),
            "temp_media":         _val("temperature_2m_mean", i),
            "sensacao_min":       _val("apparent_temperature_min", i),
            "sensacao_max":       _val("apparent_temperature_max", i),
            "precipitacao_mm":    precip,
            "chuva_mm":           _val("rain_sum", i) or 0,
            "neve_cm":            neve_cm,
            "horas_precipitacao": _val("precipitation_hours", i) or 0,
            "horas_sol":          round((_val("sunshine_duration", i) or 0) / 3600, 2),
            "radiacao_solar_mj":  _val("shortwave_radiation_sum", i),
            "vento_max_kmh":      _val("wind_speed_10m_max", i),
            "rajada_max_kmh":     _val("wind_gusts_10m_max", i),
            "direcao_vento_graus": _val("wind_direction_10m_dominant", i),
            "evapotranspiracao_mm": _val("et0_fao_evapotranspiration", i),
            "codigo_tempo":       wmo,
            "geada":              1 if (temp_min is not None and temp_min <= 0) else 0,
            "neve":               1 if neve_cm > 0 else 0,
            "granizo":            1 if wmo in _WMO_GRANIZO else 0,
            "tempestade":         1 if wmo in _WMO_TEMPESTADE else 0,
            "chuva_intensa":      1 if precip >= 20 else 0,
            "nascer_sol":         _hora(_val("sunrise", i)),
            "por_sol":            _hora(_val("sunset", i)),
            "fase_lua":           fase,
            "iluminacao_lua_pct": ilum,
        })

    return rows


# ============================================================
# PERSISTENCIA — LEITURA E ESCRITA DOS CSVs
# ============================================================

def _datas_existentes(arquivo: str, cidade: str) -> set[str]:
    """
    Le apenas as colunas 'data' e 'cidade' do CSV e retorna um set
    com as datas ja presentes para a cidade informada.
    Evita re-baixar dados que ja existem.
    """
    if not os.path.exists(arquivo):
        return set()
    try:
        df = pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", usecols=["data", "cidade"])
        return set(df.loc[df["cidade"] == cidade, "data"].unique())
    except Exception:
        return set()


def _append_df(arquivo: str, df: pd.DataFrame) -> None:
    """
    Adiciona um DataFrame ao final de um CSV (modo append).
    Se o arquivo nao existir, cria com cabecalho e BOM UTF-8
    (necessario para abrir corretamente no Excel/Power BI).
    """
    if os.path.exists(arquivo):
        with open(arquivo, "a", encoding="utf-8", newline="") as f:
            df.to_csv(f, header=False, index=False, sep=";")
    else:
        df.to_csv(arquivo, index=False, encoding="utf-8-sig", sep=";")


def _pares_existentes_acuracia(cidade: str) -> set[tuple]:
    """
    Retorna os pares (data_geracao, data_alvo) ja salvos no arquivo de acuracia
    para evitar duplicatas ao rodar o script mais de uma vez no mesmo dia.
    """
    if not os.path.exists(ARQ_ACURACIA):
        return set()
    try:
        df = pd.read_csv(ARQ_ACURACIA, sep=";", encoding="utf-8-sig",
                         usecols=["data_geracao", "data_alvo", "cidade"])
        sub = df[df["cidade"] == cidade]
        return set(zip(sub["data_geracao"], sub["data_alvo"]))
    except Exception:
        return set()


# ============================================================
# LOGICA PRINCIPAL DE ATUALIZACAO
# ============================================================

def atualizar() -> None:
    """
    Fluxo principal de atualizacao:
    1. Para cada cidade, verifica quais dias historicos estao faltando no CSV
    2. Baixa os dias faltantes do Open-Meteo (historico)
    3. Baixa a previsao dos proximos 16 dias
    4. Salva historico (append) e previsao (substituicao completa)
    5. Arquiva previsao dos proximos 7 dias para analise de acuracia futura
    """
    hoje     = date.today()
    ontem    = hoje - timedelta(days=1)
    inicio   = date(ANO_INICIO, 1, 1)
    exec_str = str(hoje)

    print(f"Atualizando dados climaticos - {hoje}")
    print(f"Cidades: {[c['nome'] for c in CIDADES]}\n")

    todas_previsao: list[dict] = []   # acumula previsao de todas as cidades
    todas_acuracia: list[dict] = []   # acumula registros de acuracia

    for cidade in CIDADES:
        nome   = cidade["nome"]
        lat    = cidade["lat"]
        lon    = cidade["lon"]
        regiao = cidade["regiao"]
        print(f"--- {nome} ({regiao}) ---")

        # --- HISTORICO ---
        # Gera o conjunto de todas as datas esperadas (do inicio ate ontem)
        datas_hist = _datas_existentes(ARQ_HISTORICO, nome)
        todas_datas = {
            str(inicio + timedelta(days=i))
            for i in range((ontem - inicio).days + 1)
        }
        faltando = sorted(todas_datas - datas_hist)  # datas que ainda nao estao no CSV

        if faltando:
            d_ini = date.fromisoformat(faltando[0])
            d_fim = date.fromisoformat(faltando[-1])
            print(f"  Historico: {len(faltando)} dias faltando ({d_ini} -> {d_fim})")
            try:
                rows = api_para_linhas(
                    fetch_historico_api(lat, lon, d_ini, d_fim),
                    nome, regiao, lat, lon,
                )
                # Filtra para garantir que so salvamos os dias realmente faltando
                novos = [r for r in rows if r["data"] in set(faltando)]
                if novos:
                    _append_df(ARQ_HISTORICO, pd.DataFrame(novos, columns=COLUNAS_HISTORICO))
                    print(f"  Salvo: {len(novos)} novos registros historicos")
            except Exception as e:
                print(f"  ERRO historico: {e}")
        else:
            print(f"  Historico: atualizado ({len(datas_hist)} dias)")

        # --- PREVISAO ---
        # A previsao e sempre baixada novamente e substitui a anterior
        try:
            rows_prev = api_para_linhas(
                fetch_previsao_api(lat, lon, dias=16),
                nome, regiao, lat, lon,
            )
            pares_existentes = _pares_existentes_acuracia(nome)

            for r in rows_prev:
                d_alvo = date.fromisoformat(r["data"])
                dias_a_frente = (d_alvo - hoje).days
                r["dias_a_frente"] = dias_a_frente
                r["data_execucao"] = exec_str
                todas_previsao.append(r)

                # Arquiva previsao dos proximos 7 dias para comparar com o real depois
                if 1 <= dias_a_frente <= 7:
                    chave = (exec_str, r["data"])
                    if chave not in pares_existentes:
                        todas_acuracia.append({
                            "data_geracao":  exec_str,
                            "data_alvo":     r["data"],
                            "cidade":        nome,
                            "dias_a_frente": dias_a_frente,
                            **{f"{v}_prev": r[v] for v in VARS_ACURACIA},
                        })

            print(f"  Previsao: {len(rows_prev)} dias ({rows_prev[0]['data']} -> {rows_prev[-1]['data']})")

        except Exception as e:
            print(f"  ERRO previsao: {e}")

    # Substitui o arquivo de previsao inteiro (e pequeno, apenas 48 linhas)
    if todas_previsao:
        df_prev = (
            pd.DataFrame(todas_previsao, columns=COLUNAS_PREVISAO)
            .sort_values(["cidade", "data"])
            .reset_index(drop=True)
        )
        df_prev.to_csv(ARQ_PREVISAO, index=False, encoding="utf-8-sig", sep=";")
        print(f"\nPrevisao: {len(todas_previsao)} linhas -> {os.path.basename(ARQ_PREVISAO)}")

    # Append no arquivo de acuracia (nunca sobrescreve — cresce ao longo do tempo)
    if todas_acuracia:
        _append_df(ARQ_ACURACIA, pd.DataFrame(todas_acuracia, columns=COLUNAS_ACURACIA))
        print(f"Acuracia: +{len(todas_acuracia)} linhas -> {os.path.basename(ARQ_ACURACIA)}")


# ============================================================
# VALIDACAO — VERIFICA COBERTURA DOS DADOS
# ============================================================

def validar() -> None:
    """Mostra um resumo da cobertura de cada arquivo de clima."""
    print("\n" + "=" * 60)
    print("VALIDACAO - cobertura climatica")
    print("=" * 60)

    for arq, label in [
        (ARQ_HISTORICO, "Historico"),
        (ARQ_PREVISAO,  "Previsao "),
        (ARQ_ACURACIA,  "Acuracia "),
    ]:
        if not os.path.exists(arq):
            print(f"  {label}: arquivo nao encontrado")
            continue

        # Carrega so as colunas de data e cidade (leitura minima)
        df = pd.read_csv(arq, sep=";", encoding="utf-8-sig",
                         usecols=lambda c: c in ("data", "data_alvo", "cidade"))
        col_data = "data" if "data" in df.columns else "data_alvo"

        for cidade in df["cidade"].unique():
            datas = sorted(df.loc[df["cidade"] == cidade, col_data].unique())
            print(f"  {label} | {cidade:12s}: {len(datas):4d} dias  ({datas[0]} -> {datas[-1]})")


# ============================================================
# PONTO DE ENTRADA
# ============================================================

def main() -> None:
    os.makedirs(DIR_DADOS, exist_ok=True)
    if "--validar" in sys.argv:
        validar()
    else:
        atualizar()
        validar()


if __name__ == "__main__":
    main()
