"""Testa a nova extracao com 1 PDF antes de rodar tudo."""
import io, requests, pdfplumber, sys
sys.path.insert(0, ".")
from extrair_ceasa import extract_from_pdf
from datetime import date

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.ceasa.sc.gov.br"}
URL = "https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos/2026-1/05-maio-18/3433-14-05-2026/file"

r = requests.get(URL, headers=HEADERS, timeout=30)
rows = extract_from_pdf(r.content, date(2026, 5, 14))

print(f"Registros extraidos: {len(rows)}")
print(f"Produtos unicos: {len(set(r['produto_variedade'] for r in rows))}")
print()
print(f"{'Produto/Variedade':<30} {'Classif':<12} {'Tipo':<10} {'Origem':<10} {'Emb':<8} {'Qtd':>5} {'Min':>8} {'Com':>8} {'Max':>8} {'R$/kg':>6}")
print("-" * 110)
for r in rows[:25]:
    print(
        f"{r['produto_variedade']:<30} "
        f"{r['classificacao']:<12} "
        f"{r['tipo']:<10} "
        f"{r['origem']:<10} "
        f"{r['embalagem']:<8} "
        f"{r['conv_kg']:>5} "
        f"{r['preco_minimo']:>8.2f} "
        f"{r['preco_comum']:>8.2f} "
        f"{r['preco_maximo']:>8.2f} "
        f"{r['preco_comum_kg']:>6.2f}"
    )
