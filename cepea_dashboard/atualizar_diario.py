"""
Atualização DIÁRIA e leve dos indicadores CEPEA — sem passar pelo formulário
"Consultas ao Banco de Dados" (esse ficou atrás de verificação Cloudflare
em algum momento depois de 15/06/2026 e não dá mais pra automatizar).

Em vez disso, visita a página pública de cada indicador
(cepea.org.br/br/indicador/{slug}.aspx) — que NÃO tem essa proteção — e lê
a tabelinha "Valor R$" com os últimos dias úteis. Só acrescenta ao
histórico as datas que ainda não existem em dados/cepea_data.js; não
apaga nada.

Por que isso é seguro (não é "furar" a proteção):
  - São páginas públicas de exibição, iguais às que qualquer visitante vê.
  - A tabela mostra só ~15-35 dias — não dá pra reconstruir o histórico
    completo por aqui, só pra manter o dado em dia dia a dia.
  - Se algum dia isso também for bloqueado, o script simplesmente falha
    naquele produto e mantém o valor anterior (não trava o resto).

Uso:
    python atualizar_diario.py                # todos os produtos
    python atualizar_diario.py --produto=soja  # só um produto

Para rodar automaticamente todo dia, ver agendar_atualizacao.ps1.
"""

from playwright.sync_api import sync_playwright
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Reaproveita a lista de produtos já cadastrada em atualizar.py
from atualizar import PRODUTOS

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PRODUTO_UNICO = None
for a in sys.argv[1:]:
    if a.startswith('--produto='):
        PRODUTO_UNICO = a.split('=', 1)[1]

OUT_JS = Path('dados/cepea_data.js')


def parse_data_br(s):
    try:
        return datetime.strptime(s.strip(), '%d/%m/%Y').strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_preco_br(s):
    try:
        return float(s.strip().replace('.', '').replace(',', '.'))
    except Exception:
        return None


# Datas no site aparecem como "18/09/2026", "18-09-2026" ou faixas de
# semana "14 - 18/09/2026" — sempre pegamos a última data da faixa.
_RE_DATA = re.compile(r'(\d{2})[/-](\d{2})[/-](\d{4})\s*$')
_RE_MES  = re.compile(r'^([a-zç]{3})[/\s](\d{2,4})$', re.IGNORECASE)


def _extrai_data(cell):
    m = _RE_DATA.search(cell)
    if m:
        d, mth, y = m.groups()
        try:
            return datetime.strptime(f'{d}/{mth}/{y}', '%d/%m/%Y').strftime('%Y-%m-%d')
        except Exception:
            return None
    return None  # não trata "mai/26" (mensal) — produtos só-mensais ficam de fora por ora


def ler_tabela_indicador(page, prod):
    """Abre a página pública do indicador e devolve [{'data':..,'preco':..}, ...].

    A tabela tem formatos diferentes por produto:
      - direto:      [data, preço, var%, ...]                (ex: boi, soja, etanol)
      - com região:  [data, região/série, preço, var%, ...]   (ex: feijão, ovos, tilápia)
    Quando há região, usa prod['serie'] (texto parcial) pra escolher a linha
    certa; se serie=None, pega a primeira região de cada data (mesmo
    critério de "primeira disponível" do atualizar.py original).
    """
    page.goto(f'https://www.cepea.org.br/br/indicador/{prod["slug"]}.aspx',
              wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(1800)

    if 'challenge-platform' in page.content() and 'imagenet-indicador1' not in page.content():
        raise RuntimeError('página bloqueada por verificação de segurança')

    linhas = page.evaluate("""() => {
        const tbl = document.getElementById('imagenet-indicador1');
        if (!tbl) return null;
        const out = [];
        for (const tr of tbl.querySelectorAll('tr')) {
            const tds = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
            const cells = tds.filter(t => t.length > 0);
            if (cells.length >= 2) out.push(cells);
        }
        return out;
    }""")
    if not linhas:
        raise RuntimeError("tabela 'imagenet-indicador1' não encontrada")

    serie = (prod.get('serie') or '').lower()
    historico = {}
    for cells in linhas:
        data_iso = _extrai_data(cells[0])
        if not data_iso:
            continue

        resto = cells[1:]
        # Primeira célula após a data: preço (número) ou rótulo de região/série?
        if resto and parse_preco_br(resto[0]) is not None and '/' not in resto[0]:
            preco_str = resto[0]
        elif len(resto) >= 2:
            label = resto[0]
            if serie and serie not in label.lower():
                continue  # não é a série que queremos
            if not serie and data_iso in historico:
                continue  # já pegamos a "primeira disponível" desta data
            preco_str = resto[1]
        else:
            continue

        preco = parse_preco_br(preco_str)
        if preco and preco > 0:
            historico[data_iso] = {'data': data_iso, 'preco': round(preco, 4)}

    if not historico:
        raise RuntimeError('nenhuma linha de preço reconhecida na tabela')
    return list(historico.values())


def main():
    produtos = PRODUTOS
    if PRODUTO_UNICO:
        produtos = [p for p in PRODUTOS if p['id'] == PRODUTO_UNICO]
        if not produtos:
            print(f'Produto não encontrado: {PRODUTO_UNICO}')
            return

    if not OUT_JS.exists():
        print(f'Arquivo {OUT_JS} não existe — rode atualizar.py primeiro pra gerar o histórico base.')
        return

    txt = OUT_JS.read_text(encoding='utf-8')
    m = re.search(r'window\.CEPEA_DATA\s*=\s*(\{.*\})\s*;', txt, re.DOTALL)
    payload = json.loads(m.group(1))
    por_id = {p['id']: p for p in payload['produtos']}

    print(f'Atualização diária CEPEA — {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    print(f'Produtos: {len(produtos)}\n')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            ),
            locale='pt-BR',
        )
        page = ctx.new_page()

        novos_total = 0
        erros = 0
        for prod in produtos:
            pid = prod['id']
            print(f'[{pid}] {prod["nome"]}...', end=' ')
            try:
                recentes = ler_tabela_indicador(page, prod)
                atual = por_id.get(pid)
                hist_existente = {h['data']: h for h in (atual.get('historico', []) if atual else [])}

                novos = [h for h in recentes if h['data'] not in hist_existente]
                for h in novos:
                    hist_existente[h['data']] = h

                historico = sorted(hist_existente.values(), key=lambda x: x['data'])
                preco_atual = historico[-1]['preco']
                preco_ant = historico[-2]['preco'] if len(historico) > 1 else None
                variacao = round(preco_atual - preco_ant, 4) if preco_ant else None
                variacao_pct = round(variacao / preco_ant * 100, 4) if (variacao and preco_ant) else None

                por_id[pid] = {
                    'id': pid, 'nome': prod['nome'], 'unidade': prod['unidade'],
                    'praca': prod['praca'], 'cor': prod['cor'],
                    'preco': preco_atual, 'preco_ant': preco_ant,
                    'variacao': variacao, 'variacao_pct': variacao_pct,
                    'data_ref': historico[-1]['data'], 'historico': historico, 'ok': True,
                }
                novos_total += len(novos)
                print(f'{len(novos)} dia(s) novo(s) · último: {historico[-1]["data"]}')
            except Exception as e:
                erros += 1
                # Mantém o último preço conhecido, mas registra a falha: sem
                # isso o produto seguia marcado ok=True e o dashboard não
                # tinha como distinguir dado fresco de série parada.
                anterior = por_id.get(pid)
                if anterior:
                    anterior['ok'] = True  # ainda exibível — o aviso vem de coleta_erro
                    anterior['coleta_erro'] = str(e)
                    anterior['coleta_erro_em'] = datetime.now().strftime('%Y-%m-%d')
                print(f'ERRO ({e}) — mantido valor anterior')
            page.wait_for_timeout(600)

        browser.close()

    # Mantém produtos que não estavam na lista filtrada (--produto=)
    payload['produtos'] = [por_id[p['id']] for p in PRODUTOS if p['id'] in por_id]

    # Só carimba data nova se ALGO foi realmente coletado. Antes o timestamp e
    # o data_fim eram reescritos em toda execução — numa rodada 100% bloqueada
    # isso gerava diff, commit e push, e o painel passava a anunciar "atualizado
    # hoje" com preço de semanas atrás. O arquivo só muda se o dado mudou.
    if novos_total > 0:
        payload['timestamp'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        payload['data_fim'] = datetime.now().strftime('%d/%m/%Y')
    else:
        print('Nenhum dia novo — timestamp e data_fim preservados.')

    OUT_JS.write_text(
        '/* Gerado por atualizar.py / atualizar_diario.py — não editar manualmente */\n'
        'window.CEPEA_DATA = ' + json.dumps(payload, ensure_ascii=False, indent=2) + ';\n',
        encoding='utf-8'
    )
    print(f'\n{"="*50}')
    print(f'{novos_total} dia(s) novo(s) no total · {erros} produto(s) com erro')
    print(f'Salvo em {OUT_JS}')

    # Sai com erro quando a coleta falhou em massa (ex: o CEPEA bloqueando o IP
    # do runner, que derruba 17 de 18 de uma vez). Sem isso a execução terminava
    # com código 0 e o agendamento ficava verde por semanas sem coletar nada.
    if erros > len(produtos) / 2:
        print(f'FALHA: {erros} de {len(produtos)} produtos falharam — coleta considerada quebrada.')
        sys.exit(1)


if __name__ == '__main__':
    main()
