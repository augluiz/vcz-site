"""
Baixa CSVs do MDIC e carrega no Supabase PostgreSQL.
Usado pelo GitHub Actions (atualizar_comex.yml) e pode ser rodado localmente.

Uso local:
  pip install httpx pandas psycopg2-binary python-dotenv
  python scripts/carregar_comex.py                  # todos os anos (carga inicial)
  python scripts/carregar_comex.py --anos 2025 2026 # anos específicos
  python scripts/carregar_comex.py --refs-only       # só tabelas de referência
  python scripts/carregar_comex.py --force           # força re-download

.env (crie na raiz do vcz-site):
  SUPABASE_DB_URL=postgresql://postgres:SENHA@db.wtfgvfizrxxxmidiodib.supabase.co:5432/postgres
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # no GitHub Actions as variáveis vêm de env secrets

DB_URL = os.environ.get("SUPABASE_DB_URL")
if not DB_URL:
    print("ERRO: variável SUPABASE_DB_URL não definida.")
    sys.exit(1)

BASE_NCM  = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm"
BASE_REFS = "https://balanca.economia.gov.br/balanca/bd/tabelas"
CACHE_DIR = Path(__file__).parent.parent / ".comex_cache"
ANOS_DEFAULT = list(range(2020, 2027))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.gov.br/mdic/",
}

COLS_FATO = {
    "CO_ANO": "ano", "CO_MES": "mes", "CO_NCM": "ncm",
    "CO_PAIS": "pais_cod", "SG_UF_NCM": "uf",
    "KG_LIQUIDO": "kg_liquido", "VL_FOB": "valor_fob",
}


def baixar(url: str, dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        mb = dest.stat().st_size / 1_048_576
        print(f"    cache: {dest.name} ({mb:.1f} MB)")
        return True
    print(f"    baixando {url.split('/')[-1]}...", end=" ", flush=True)
    try:
        with httpx.Client(timeout=600.0, headers=HEADERS, follow_redirects=True, verify=False) as c:
            with c.stream("GET", url) as r:
                if r.status_code == 404:
                    print("não encontrado")
                    return False
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(65536):
                        f.write(chunk)
        mb = dest.stat().st_size / 1_048_576
        print(f"OK ({mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"ERRO: {e}")
        if dest.exists():
            dest.unlink()
        return False


def carregar_referencias(conn, force: bool = False):
    print("\n── Tabelas de referência ──")
    CACHE_DIR.mkdir(exist_ok=True)

    # Países
    dest = CACHE_DIR / "PAIS.csv"
    if baixar(f"{BASE_REFS}/PAIS.csv", dest, force):
        df = pd.read_csv(dest, sep=";", dtype=str, encoding="latin-1")
        df = df.rename(columns={"CO_PAIS": "cod", "NO_PAIS": "nome_pt",
                                  "NO_PAIS_ING": "nome_ing", "CO_PAIS_ISOA3": "iso3"})
        df["cod"] = pd.to_numeric(df["cod"], errors="coerce")
        df = df.dropna(subset=["cod"])
        df["cod"] = df["cod"].astype(int)
        rows = df[["cod", "nome_pt", "nome_ing", "iso3"]].values.tolist()
        with conn.cursor() as cur:
            execute_values(cur,
                "INSERT INTO comex_pais (cod, nome_pt, nome_ing, iso3) VALUES %s "
                "ON CONFLICT (cod) DO UPDATE SET nome_pt=EXCLUDED.nome_pt, "
                "nome_ing=EXCLUDED.nome_ing, iso3=EXCLUDED.iso3",
                rows)
        conn.commit()
        print(f"    comex_pais: {len(rows)} países")

    # NCM
    dest = CACHE_DIR / "NCM.csv"
    if baixar(f"{BASE_REFS}/NCM.csv", dest, force):
        df = pd.read_csv(dest, sep=";", dtype=str, encoding="latin-1")
        df = df.rename(columns={"CO_NCM": "cod", "NO_NCM_POR": "descricao",
                                  "CO_SH4": "sh4", "CO_SH2": "sh2", "CO_NCM_SEC": "secao"})
        df["cod"] = df["cod"].str.strip().str.zfill(8)
        df["descricao"] = df.get("descricao", pd.Series(dtype=str)).fillna("").str[:500]
        for col in ["sh4", "sh2", "secao"]:
            if col not in df.columns:
                df[col] = None
        rows = df[["cod", "descricao", "sh4", "sh2", "secao"]].values.tolist()
        with conn.cursor() as cur:
            execute_values(cur,
                "INSERT INTO comex_ncm (cod, descricao, sh4, sh2, secao) VALUES %s "
                "ON CONFLICT (cod) DO UPDATE SET descricao=EXCLUDED.descricao",
                rows, page_size=2000)
        conn.commit()
        print(f"    comex_ncm: {len(rows)} NCMs")

    # UF
    dest = CACHE_DIR / "UF.csv"
    if baixar(f"{BASE_REFS}/UF.csv", dest, force):
        df = pd.read_csv(dest, sep=";", dtype=str, encoding="latin-1")
        df = df.rename(columns={"SG_UF": "sigla", "NO_UF": "nome", "NO_REGIAO": "regiao"})
        df["nome"]   = df["nome"].str[:50]
        df["regiao"] = df["regiao"].str[:50]
        rows = df[["sigla", "nome", "regiao"]].dropna().values.tolist()
        with conn.cursor() as cur:
            execute_values(cur,
                "INSERT INTO comex_uf (sigla, nome, regiao) VALUES %s "
                "ON CONFLICT (sigla) DO UPDATE SET nome=EXCLUDED.nome, regiao=EXCLUDED.regiao",
                rows)
        conn.commit()
        print(f"    comex_uf: {len(rows)} UFs")

    # Via
    dest = CACHE_DIR / "VIA.csv"
    if baixar(f"{BASE_REFS}/VIA.csv", dest, force):
        df = pd.read_csv(dest, sep=";", dtype=str, encoding="latin-1")
        df = df.rename(columns={"CO_VIA": "cod", "NO_VIA": "descricao"})
        df["cod"] = pd.to_numeric(df["cod"], errors="coerce")
        df = df.dropna(subset=["cod"])
        df["cod"] = df["cod"].astype(int)
        rows = df[["cod", "descricao"]].values.tolist()
        with conn.cursor() as cur:
            execute_values(cur,
                "INSERT INTO comex_via (cod, descricao) VALUES %s "
                "ON CONFLICT (cod) DO UPDATE SET descricao=EXCLUDED.descricao",
                rows)
        conn.commit()
        print(f"    comex_via: {len(rows)} vias")


def carregar_ano(conn, fluxo: str, ano: int, force: bool = False):
    prefixo = "IMP" if fluxo == "I" else "EXP"
    dest = CACHE_DIR / f"{prefixo}_{ano}.csv"
    url  = f"{BASE_NCM}/{prefixo}_{ano}.csv"

    if not baixar(url, dest, force):
        return

    print(f"    processando {prefixo}_{ano}.csv...", end=" ", flush=True)
    t0 = time.time()

    df = pd.read_csv(dest, sep=";", dtype=str,
                     usecols=list(COLS_FATO.keys()), encoding="latin-1")
    df = df.rename(columns=COLS_FATO)
    df["fluxo"]      = fluxo
    df["ano"]        = pd.to_numeric(df["ano"],      errors="coerce")
    df["mes"]        = pd.to_numeric(df["mes"],      errors="coerce")
    df["pais_cod"]   = pd.to_numeric(df["pais_cod"], errors="coerce")
    df["kg_liquido"] = pd.to_numeric(df["kg_liquido"], errors="coerce").fillna(0)
    df["valor_fob"]  = pd.to_numeric(df["valor_fob"],  errors="coerce").fillna(0)
    df["ncm"]        = df["ncm"].str.strip().str.zfill(8)
    df["uf"]         = df["uf"].fillna("").str.strip().str[:2]
    df = df.dropna(subset=["ano", "mes", "pais_cod"])

    # Agrega descartando VIA (economiza ~20-30% de linhas)
    df = (df.groupby(["fluxo", "ano", "mes", "ncm", "pais_cod", "uf"], as_index=False)
            .agg(kg_liquido=("kg_liquido", "sum"), valor_fob=("valor_fob", "sum")))

    rows = df[["fluxo", "ano", "mes", "ncm", "pais_cod", "uf",
               "kg_liquido", "valor_fob"]].values.tolist()

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO comex_fato
                 (fluxo, ano, mes, ncm, pais_cod, uf, kg_liquido, valor_fob)
               VALUES %s
               ON CONFLICT (fluxo, ano, mes, ncm, pais_cod, uf)
               DO UPDATE SET
                 kg_liquido = EXCLUDED.kg_liquido,
                 valor_fob  = EXCLUDED.valor_fob""",
            rows,
            page_size=5000,
        )
    conn.commit()
    print(f"{len(rows):,} registros inseridos/atualizados em {time.time()-t0:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anos", nargs="+", type=int, default=ANOS_DEFAULT)
    parser.add_argument("--refs-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    CACHE_DIR.mkdir(exist_ok=True)

    print("Conectando ao Supabase...")
    conn = psycopg2.connect(DB_URL)
    print("Conectado.")

    carregar_referencias(conn, args.force)

    if not args.refs_only:
        print(f"\n── Dados fato — anos: {args.anos} ──")
        for ano in args.anos:
            print(f"\n  Ano {ano}:")
            for fluxo in ["I", "E"]:
                carregar_ano(conn, fluxo, ano, args.force)

    conn.close()
    print("\nConcluído.")


if __name__ == "__main__":
    main()
