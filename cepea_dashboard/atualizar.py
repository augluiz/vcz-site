"""
Baixa histórico de preços do CEPEA/ESALQ-USP via formulário de banco de dados.
Usa Playwright para preencher o formulário e baixar o Excel de cada série.

Instalação (primeira vez):
    pip install playwright openpyxl
    playwright install chromium

Uso:
    python atualizar.py                         # abre browser visível
    python atualizar.py --headless              # sem janela
    python atualizar.py --inicio=01/01/2023     # outra data inicial
    python atualizar.py --produto=soja          # só um produto (pelo id)
"""

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import openpyxl
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Parâmetros ────────────────────────────────────────────────────────────────
DATA_INICIO   = '01/01/2025'
DATA_FIM      = datetime.today().strftime('%d/%m/%Y')
HEADLESS      = '--headless' in sys.argv
PRODUTO_UNICO = None

for a in sys.argv[1:]:
    if a.startswith('--inicio='):
        DATA_INICIO = a.split('=', 1)[1]
    if a.startswith('--produto='):
        PRODUTO_UNICO = a.split('=', 1)[1]

URL_CONSULTAS = 'https://cepea.org.br/br/consultas-ao-banco-de-dados-do-site.aspx'
DIR_XLSX      = Path('dados/xlsx')
OUT_JS        = Path('dados/cepea_data.js')

# ── Produtos ──────────────────────────────────────────────────────────────────
# cepea : texto exato na lista da esquerda do CEPEA
# serie : trecho que identifica a série preferida no painel do meio
#         None = pega a primeira disponível
PRODUTOS = [
    # slug: parte da URL da página de indicador (cepea.org.br/br/indicador/{slug}.aspx)
    # serie: texto parcial da série preferida no painel central (None = primeira)
    {'id': 'acucar',   'nome': 'Açúcar',    'slug': 'acucar',    'serie': 'Cristal Branco',  'unidade': 'R$/sc 50kg', 'praca': 'São Paulo/SP',  'cor': '#AB47BC'},
    {'id': 'algodao',  'nome': 'Algodão',   'slug': 'algodao',   'serie': None,              'unidade': 'R$/arroba',  'praca': 'São Paulo/SP',  'cor': '#78909C'},
    {'id': 'arroz',    'nome': 'Arroz',     'slug': 'arroz',     'serie': None,              'unidade': 'R$/sc 50kg', 'praca': 'RS/SC',         'cor': '#E8D44D'},
    {'id': 'bezerro',  'nome': 'Bezerro',   'slug': 'bezerro',   'serie': None,              'unidade': 'R$/cab.',    'praca': 'Mato Grosso',   'cor': '#D2691E'},
    {'id': 'boi',      'nome': 'Boi Gordo', 'slug': 'boi-gordo', 'serie': None,              'unidade': 'R$/arroba',  'praca': 'São Paulo/SP',  'cor': '#E06060'},
    {'id': 'cafe',     'nome': 'Café',      'slug': 'cafe',      'serie': 'Arábica',         'unidade': 'R$/sc 60kg', 'praca': 'Cerrado/MG',    'cor': '#8D6E63'},
    {'id': 'etanol',   'nome': 'Etanol',    'slug': 'etanol',    'serie': 'Hidratado',       'unidade': 'R$/litro',   'praca': 'Interior SP',   'cor': '#5B8FC4'},
    {'id': 'feijao',   'nome': 'Feijão',    'slug': 'feijao',    'serie': 'Distrito Federal', 'unidade': 'R$/sc 60kg', 'praca': 'Distrito Federal', 'cor': '#8B4513'},
    {'id': 'frango',   'nome': 'Frango',    'slug': 'frango',    'serie': None,              'unidade': 'R$/kg',      'praca': 'Paraná/PR',     'cor': '#FF8C00'},
    {'id': 'leite',    'nome': 'Leite',     'slug': 'leite',     'serie': None,              'unidade': 'R$/litro',   'praca': 'Brasil',        'cor': '#B0C4DE'},
    {'id': 'mandioca', 'nome': 'Mandioca',  'slug': 'mandioca',  'serie': 'EOP',             'unidade': 'R$/t',       'praca': 'Entrada Oeste - PR', 'cor': '#DAA520'},
    {'id': 'milho',    'nome': 'Milho',     'slug': 'milho',     'serie': None,              'unidade': 'R$/sc 60kg', 'praca': 'Campinas/SP',   'cor': '#D4A830'},
    {'id': 'ovinos',   'nome': 'Ovinos',    'slug': 'ovinos',    'serie': None,              'unidade': 'R$/kg',      'praca': 'São Paulo/SP',  'cor': '#A9A9A9'},
    {'id': 'ovos',     'nome': 'Ovos',      'slug': 'ovos',      'serie': 'Grande SP',       'unidade': 'R$/cx 30dz', 'praca': 'Grande SP/SP',  'cor': '#FFF3CD'},
    {'id': 'soja',     'nome': 'Soja',      'slug': 'soja',      'serie': 'Paranaguá',       'unidade': 'R$/sc 60kg', 'praca': 'Paranaguá/PR',  'cor': '#4CAF50'},
    {'id': 'suino',    'nome': 'Suíno',     'slug': 'suino',     'serie': None,              'unidade': 'R$/kg',      'praca': 'Paraná/PR',     'cor': '#FFB6C1'},
    {'id': 'tilapia',  'nome': 'Tilápia',   'slug': 'tilapia',   'serie': None,              'unidade': 'R$/kg',      'praca': 'São Paulo/SP',  'cor': '#40E0D0'},
    {'id': 'trigo',    'nome': 'Trigo',     'slug': 'trigo',     'serie': None,              'unidade': 'R$/sc 60kg', 'praca': 'Paraná/PR',     'cor': '#FFA726'},
]

# ── Parse de data ─────────────────────────────────────────────────────────────
def parse_data(val):
    if isinstance(val, (datetime, date)):
        d = val if isinstance(val, datetime) else datetime.combine(val, datetime.min.time())
        return d.strftime('%Y-%m-%d')
    s = str(val).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except Exception:
            pass
    return None


# ── Parse do Excel do CEPEA ───────────────────────────────────────────────────
_XLS_SIG = b'\xd0\xcf\x11\xe0'  # OLE compound document (Excel 97-2003 .xls)

def _rows_from_file(path):
    """Lê .xls (xlrd) ou .xlsx (openpyxl) e retorna lista de tuplas."""
    with open(str(path), 'rb') as f:
        sig = f.read(4)
    if sig == _XLS_SIG:
        import xlrd, io as _io, olefile as _ole
        # Extrai stream BIFF diretamente via olefile (bypassa validação FAT do xlrd)
        ole = _ole.OleFileIO(str(path))
        stream_name = 'Workbook' if ole.exists('Workbook') else 'Book'
        biff = ole.openstream(stream_name).read()
        ole.close()
        wb = xlrd.open_workbook(file_contents=biff, logfile=_io.StringIO())
        ws = wb.sheet_by_index(0)
        rows = []
        for r in range(ws.nrows):
            row = []
            for c in range(ws.ncols):
                cell = ws.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate_as_datetime(cell.value, wb.datemode))
                elif cell.ctype in (xlrd.XL_CELL_TEXT,):
                    row.append(cell.value)
                elif cell.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_BOOLEAN):
                    row.append(cell.value)
                else:
                    row.append(None)
            rows.append(tuple(row))
        return rows
    else:
        wb = openpyxl.load_workbook(str(path), data_only=True)
        return list(wb.active.iter_rows(values_only=True))


def parse_excel(path):
    rows = _rows_from_file(path)

    data_col = preco_col = None
    header_idx = None

    for i, row in enumerate(rows):
        # Normaliza para busca
        row_n = [str(c).strip().lower() if c is not None else '' for c in row]

        # Procura coluna de data pelo cabeçalho
        for j, cell in enumerate(row_n):
            if cell == 'data':
                data_col = j
                header_idx = i
                break

        if data_col is not None:
            # Procura coluna de preço R$ na mesma linha
            for j, cell in enumerate(row_n):
                if 'r$' in cell or 'à vista' in cell or ('valor' in cell and 'r' in cell):
                    preco_col = j
                    break
            if preco_col is None:
                # Fallback: segunda coluna numérica após a de data
                for j in range(data_col + 1, len(row_n)):
                    if row_n[j] and row_n[j] not in ('', 'none'):
                        preco_col = j
                        break
            break

    if header_idx is None or data_col is None or preco_col is None:
        raise ValueError(f'Colunas de data/preço não encontradas em {path.name}')

    historico = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(data_col, preco_col):
            continue
        raw_data  = row[data_col]
        raw_preco = row[preco_col]
        if raw_data is None or raw_preco is None:
            continue

        data_str = parse_data(raw_data)
        if not data_str:
            continue

        try:
            if isinstance(raw_preco, (int, float)):
                preco = float(raw_preco)
            else:
                preco = float(str(raw_preco).replace('.', '').replace(',', '.').strip())
        except Exception:
            continue

        if preco > 0:
            historico.append({'data': data_str, 'preco': round(preco, 4)})

    return sorted(historico, key=lambda x: x['data'])


# ── Playwright — helpers JavaScript ──────────────────────────────────────────

def _js_click_text(page, texto, exact=True, exclude_href=None, case_insensitive=False):
    """Clica via JS no elemento com determinado texto, verificando visibilidade real."""
    t = texto.lower() if case_insensitive else texto
    if case_insensitive:
        match_fn = f"el.textContent.trim().toLowerCase() === {json.dumps(t)}" if exact \
                   else f"el.textContent.trim().toLowerCase().includes({json.dumps(t)})"
    else:
        match_fn = f"el.textContent.trim() === {json.dumps(texto)}" if exact \
                   else f"el.textContent.trim().includes({json.dumps(texto)})"
    href_cond = f" && !(el.href || '').includes({json.dumps(exclude_href)})" if exclude_href else ''
    return page.evaluate(f"""() => {{
        function visivel(el) {{
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        }}
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if ({match_fn}{href_cond} && visivel(el)) {{
                el.click();
                return el.outerHTML.substring(0, 120);
            }}
        }}
        return null;
    }}""")


def _js_set_date(page, input_id, date_str):
    """Define data em input readonly do pickadate.js via JavaScript."""
    d, m, y = date_str.split('/')
    page.evaluate(f"""() => {{
        const el = document.getElementById({json.dumps(input_id)});
        if (!el) return;
        if (window.jQuery) {{
            try {{
                const picker = jQuery(el).pickadate('picker');
                if (picker) {{
                    picker.set('select', new Date({int(y)}, {int(m) - 1}, {int(d)}));
                    return;
                }}
            }} catch(e) {{}}
        }}
        el.removeAttribute('readonly');
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, {json.dumps(date_str)});
        ['input', 'change'].forEach(ev =>
            el.dispatchEvent(new Event(ev, {{bubbles: true}})));
    }}""")


# ── Parse da tabela HTML retornada pelo CEPEA (fallback sem download link) ────
def _html_to_xlsx(html, out_path):
    """Parseia a tabela HTML da página ?tabel= e salva como xlsx."""
    import re as _re
    rows_html = _re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, _re.DOTALL | _re.IGNORECASE)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Data', 'Valor R$'])
    for row_h in rows_html:
        cells = _re.findall(r'<td\b[^>]*>(.*?)</td>', row_h, _re.DOTALL | _re.IGNORECASE)
        if len(cells) >= 2:
            cells = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            ws.append(cells[:2])
    wb.save(str(out_path))
    return out_path


# ── Playwright — automação do formulário ──────────────────────────────────────
def _ir_para_consultas_com_produto(page, prod):
    """
    Navega para URL_CONSULTAS e seleciona o produto via radio button (id=prod['id']).
    Os radios têm IDs exatos: acucar, algodao, arroz, bezerro, boi, cafe, etanol,
    feijao, frango, leite, mandioca, milho, soja, suino, tilapia, trigo.
    """
    print(f"    → consultas: {prod['id']}")
    page.goto(URL_CONSULTAS, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(2000)

    # Clica no radio do produto (id exato) ou no label associado
    res = page.evaluate(f"""() => {{
        const radio = document.getElementById({json.dumps(prod['id'])});
        if (!radio) return null;
        const lbl = document.querySelector('label[for={json.dumps(prod["id"])}]');
        if (lbl) lbl.click();
        else {{
            radio.click();
            radio.checked = true;
            radio.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return 'radio#' + radio.id + ' checked=' + radio.checked;
    }}""")
    if not res:
        raise RuntimeError(f"Radio '{prod['id']}' não encontrado no formulário CEPEA")
    print(f"    → {res}")
    page.wait_for_timeout(2000)  # aguarda AJAX de séries carregar


def _selecionar_primeira_serie(page):
    """Clica na primeira série disponível no painel central (imagenet)."""
    return page.evaluate("""() => {
        function vis(el) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden';
        }
        // 1. Primeira label associada a radio subtipo-*
        for (const l of document.querySelectorAll('label[for^="subtipo-"]')) {
            if (vis(l)) { l.click(); return 'label:' + l.textContent.trim().substring(0, 60); }
        }
        // 2. Ancestral clicável do radio subtipo-0
        const r0 = document.getElementById('subtipo-0');
        if (r0) {
            let el = r0.parentElement;
            for (let i = 0; i < 6; i++) {
                if (!el) break;
                if (['A','LI','BUTTON','SPAN'].includes(el.tagName) && vis(el)) {
                    el.click();
                    return el.tagName + ':' + el.textContent.trim().substring(0, 60);
                }
                el = el.parentElement;
            }
            // 3. Clica o radio diretamente + dispara eventos
            r0.click();
            r0.checked = true;
            ['change','click'].forEach(ev => r0.dispatchEvent(new Event(ev, {bubbles: true})));
            return 'radio:subtipo-0';
        }
        return null;
    }""")


def baixar_xlsx(page, prod, dir_xlsx):
    """Navega à página do indicador, acessa SÉRIE DE PREÇOS e baixa o Excel."""
    nome_arquivo = dir_xlsx / f"{prod['id']}.xlsx"

    # ── 1. Navega para consultas com produto selecionado ──
    _ir_para_consultas_com_produto(page, prod)

    # ── 2. Seleciona a série no painel central ──
    serie_match = prod.get('serie')
    print(f"    → Série: {serie_match or '(primeira disponível)'}")
    if serie_match:
        els = page.get_by_text(serie_match, exact=False).all()
        clicked = any(el.click() or True for el in els if el.is_visible())
        if not clicked:
            _js_click_text(page, serie_match, exact=False)
    else:
        result = _selecionar_primeira_serie(page)
        print(f"    → Série auto: {result}")
    page.wait_for_timeout(1000)

    # ── 3. Periodicidade = Diário (via JS) ──
    page.evaluate("""() => {
        for (const l of document.querySelectorAll('label')) {
            if (l.textContent.trim() === 'Diário') { l.click(); return; }
        }
        for (const r of document.querySelectorAll('input[type="radio"]')) {
            const id = (r.value || r.id || r.name || '').toLowerCase();
            if (id.startsWith('d') || id.includes('diar')) {
                r.checked = true;
                r.dispatchEvent(new Event('change', {bubbles: true}));
                return;
            }
        }
    }""")
    page.wait_for_timeout(400)

    # ── 4. Preenche o período via JS (pickadate.js bloqueia .fill()) ──
    print(f'    → Período: {DATA_INICIO} – {DATA_FIM}')
    _js_set_date(page, 'periodo-de',  DATA_INICIO)
    page.wait_for_timeout(300)
    _js_set_date(page, 'periodo-ate', DATA_FIM)
    page.wait_for_timeout(500)

    # ── 5. Clica "Gerar Excel" e captura URL da requisição AJAX ──
    tabel_urls = []
    def _on_req(r):
        if 'tabel' in r.url.lower():
            tabel_urls.append(r.url)
    page.on('request', _on_req)

    print('    → Clicando Gerar Excel...')
    page.locator('#adicionar').click(timeout=10000)
    page.wait_for_timeout(5000)
    page.remove_listener('request', _on_req)

    if not tabel_urls:
        raise RuntimeError('AJAX de tabela não capturado — série não selecionada ou formulário incompleto')

    tabel_url = tabel_urls[0]
    print(f'    → URL AJAX: {tabel_url[:100]}')

    # ── 6. GET na URL → JSON com {"arquivo": "url_do_xls"} ──
    json_data = page.evaluate(f"""async () => {{
        try {{
            const r = await fetch({json.dumps(tabel_url)});
            return await r.json();
        }} catch(e) {{ return {{error: String(e)}}; }}
    }}""")
    print(f'    → JSON: {json_data}')

    arquivo_url = (json_data or {}).get('arquivo')
    if not arquivo_url:
        raise RuntimeError(f'JSON sem arquivo: {json_data}')

    # ── 7. Baixa o arquivo XLS ──
    print(f'    → Download: {arquivo_url}')
    try:
        with page.expect_download(timeout=45000) as dl:
            try:
                page.goto(arquivo_url, wait_until='domcontentloaded', timeout=20000)
            except Exception:
                pass  # "Download is starting" é esperado
    except PWTimeout:
        raise TimeoutError('Download não iniciou em 45s')
    dl.value.save_as(str(nome_arquivo))
    print(f'    ✓ {nome_arquivo.name}')
    return nome_arquivo


# ── Processamento de um produto ───────────────────────────────────────────────
def processar_produto(page, prod, dir_xlsx):
    last_err = None
    for tentativa in range(3):
        try:
            xlsx = baixar_xlsx(page, prod, dir_xlsx)
            historico = parse_excel(xlsx)
            if not historico:
                raise ValueError('Excel baixado mas nenhum dado extraído')
            preco_atual  = historico[-1]['preco']
            preco_ant    = historico[-2]['preco'] if len(historico) > 1 else None
            variacao     = round(preco_atual - preco_ant, 4) if preco_ant else None
            variacao_pct = round(variacao / preco_ant * 100, 4) if (variacao and preco_ant) else None
            return {
                'id':           prod['id'],
                'nome':         prod['nome'],
                'unidade':      prod['unidade'],
                'praca':        prod['praca'],
                'cor':          prod['cor'],
                'preco':        preco_atual,
                'preco_ant':    preco_ant,
                'variacao':     variacao,
                'variacao_pct': variacao_pct,
                'data_ref':     historico[-1]['data'],
                'historico':    historico,
                'ok':           True,
            }
        except Exception as e:
            last_err = e
            if tentativa < 2:
                print(f'  ! Tentativa {tentativa + 1} falhou: {e}')
                print('  → Aguardando 3s antes de nova tentativa...')
                try:
                    page.wait_for_timeout(3000)
                    page.title()  # verifica se o browser ainda está vivo
                except Exception:
                    pass
    raise RuntimeError(f'Download falhou após 3 tentativas: {last_err}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    DIR_XLSX.mkdir(parents=True, exist_ok=True)
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)

    produtos = PRODUTOS
    if PRODUTO_UNICO:
        produtos = [p for p in PRODUTOS if p['id'] == PRODUTO_UNICO]
        if not produtos:
            print(f'Produto não encontrado: {PRODUTO_UNICO}')
            print('IDs disponíveis:', ', '.join(p['id'] for p in PRODUTOS))
            return

    # Lê dados existentes para preservar produtos que não serão atualizados
    payload_existente = {}
    if OUT_JS.exists():
        try:
            txt = OUT_JS.read_text(encoding='utf-8')
            m = re.search(r'window\.CEPEA_DATA\s*=\s*(\{.*\})\s*;', txt, re.DOTALL)
            if m:
                dados = json.loads(m.group(1))
                for p in dados.get('produtos', []):
                    payload_existente[p['id']] = p
        except Exception:
            pass

    payload = {
        'timestamp':  datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'fonte':      'CEPEA/ESALQ-USP',
        'data_inicio': DATA_INICIO,
        'data_fim':    DATA_FIM,
        'produtos':   [],
    }

    print(f'Período: {DATA_INICIO} → {DATA_FIM}')
    print(f'Modo: {"headless" if HEADLESS else "browser visível"}')
    print(f'Produtos: {len(produtos)}\n')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=HEADLESS,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        ctx = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1366, 'height': 768},
            locale='pt-BR',
            accept_downloads=True,
        )
        # Remove sinais de automação detectáveis
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US','en']});
            window.chrome = { runtime: {} };
        """)
        page = ctx.new_page()

        for prod in produtos:
            print(f'\n[{prod["id"]}] {prod["nome"]}')
            try:
                # Reabre página se necessário (bot detection fecha a janela)
                try:
                    page.title()
                except Exception:
                    print('  ! Página fechada — reabrindo...')
                    page = ctx.new_page()

                dado = processar_produto(page, prod, DIR_XLSX)
                payload['produtos'].append(dado)
                sinal = '+' if (dado['variacao'] or 0) > 0 else ''
                var   = f'{sinal}{dado["variacao_pct"]:.2f}%' if dado['variacao_pct'] else '—'
                print(f'  R$ {dado["preco"]} {dado["unidade"]}  {var}  ({len(dado["historico"])} dias)')
            except Exception as e:
                print(f'  ERRO: {e}')
                if prod['id'] in payload_existente:
                    payload['produtos'].append(payload_existente[prod['id']])
                    print('  → Mantido dado anterior.')
                else:
                    payload['produtos'].append({
                        'id': prod['id'], 'nome': prod['nome'],
                        'unidade': prod['unidade'], 'praca': prod['praca'],
                        'cor': prod['cor'], 'ok': False, 'erro': str(e),
                    })

            try:
                page.wait_for_timeout(1000)
            except Exception:
                pass

        browser.close()

    # Se rodou produto único, mescla com os demais existentes
    if PRODUTO_UNICO and payload_existente:
        ids_atualizados = {p['id'] for p in payload['produtos']}
        for pid, dado in payload_existente.items():
            if pid not in ids_atualizados:
                payload['produtos'].append(dado)
        # Reordena para manter ordem original
        ordem = [p['id'] for p in PRODUTOS]
        payload['produtos'].sort(key=lambda x: ordem.index(x['id']) if x['id'] in ordem else 999)

    # Salva JS
    OUT_JS.write_text(
        '/* Gerado por atualizar.py — não editar manualmente */\n'
        'window.CEPEA_DATA = '
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ';\n',
        encoding='utf-8'
    )

    ok  = sum(1 for p in payload['produtos'] if p.get('ok'))
    err = len(payload['produtos']) - ok
    print(f'\n{"="*50}')
    print(f'Salvo em {OUT_JS}  ({ok} OK · {err} erro(s))')
    print(f'Abra o dashboard: python -m http.server 8080  →  http://localhost:8080/cepea_dashboard/')


if __name__ == '__main__':
    main()
