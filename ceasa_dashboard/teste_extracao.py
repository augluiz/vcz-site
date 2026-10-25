"""
Diagnóstico: testa extração de tabelas de 1 PDF da CEASA/SC.
Rode este script primeiro para confirmar que pdfplumber funciona.

Instale as dependências antes:
    pip install requests pdfplumber pandas
"""

import requests
import pdfplumber
import io

URL_TESTE = "https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos/2026-1/05-maio-18/3433-14-05-2026/file"

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos/2026-1/05-maio-18",
    }
    print("Baixando PDF...")
    response = requests.get(URL_TESTE, headers=headers, timeout=30)
    response.raise_for_status()
    print(f"  Tamanho: {len(response.content) / 1024:.1f} KB")

    print("\nAbrindo com pdfplumber...")
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        print(f"  Páginas: {len(pdf.pages)}")

        for i, page in enumerate(pdf.pages):
            print(f"\n--- Página {i + 1} ---")

            # Tenta extrair texto simples
            texto = page.extract_text()
            if texto:
                print("  Texto encontrado (primeiras 500 chars):")
                print(texto[:500])
            else:
                print("  SEM TEXTO (pode ser PDF baseado em imagem)")

            # Tenta extrair tabelas
            tabelas = page.extract_tables()
            if tabelas:
                print(f"  Tabelas encontradas: {len(tabelas)}")
                for j, tabela in enumerate(tabelas):
                    print(f"  Tabela {j + 1} — {len(tabela)} linhas x {len(tabela[0])} colunas")
                    print("  Primeiras 5 linhas:")
                    for linha in tabela[:5]:
                        print(f"    {linha}")
            else:
                print("  SEM TABELAS detectadas pelo pdfplumber")

            # Limita a 3 páginas no diagnóstico
            if i >= 2:
                print("\n  (mostrando apenas as 3 primeiras páginas)")
                break

if __name__ == "__main__":
    main()
