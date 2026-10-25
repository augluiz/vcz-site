"""
Atualiza os dados de futuros agrícolas para o dashboard.
Fonte: Yahoo Finance (via requests - sem CORS)
Salva em: dados/commodities_data.js (carregado via <script src> no HTML)

Uso:
    python atualizar.py
    python atualizar.py --range 6mo   # muda o período do histórico
"""
import requests
import json
import time
import sys
import os
from datetime import datetime

# Garante UTF-8 no console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Configuração ───────────────────────────────────────────────────────────
RANGE = '3mo'      # período do histórico: 1mo 3mo 6mo 1y
INTERVAL = '1d'    # intervalo: 1d (diário)

COMMODITIES = [
    {
        'id': 'boi',
        'nome': 'Boi Gordo',
        'symbol': 'LE=F',
        'unidade_int': 'USD/cwt',
        'unidade_br':  'R$/@ (arroba)',
        'cor': '#E06060',
        'conv_br_nota': 'Referência: Live Cattle CME (aprox. R$/arroba)',
        'descricao': 'Live Cattle — CME (referência para Boi Gordo B3)',
    },
    {
        'id': 'milho',
        'nome': 'Milho',
        'symbol': 'ZC=F',
        'unidade_int': 'USc/bu',
        'unidade_br':  'R$/sc (60kg)',
        'cor': '#D4A830',
        'conv_br_nota': 'Referência: Corn CBOT (aprox. R$/saca 60kg)',
        'descricao': 'Corn — CBOT/CME (referência para Milho B3)',
    },
    {
        'id': 'soja',
        'nome': 'Soja',
        'symbol': 'ZS=F',
        'unidade_int': 'USc/bu',
        'unidade_br':  'R$/sc (60kg)',
        'cor': '#4CAF50',
        'conv_br_nota': 'Referência: Soybeans CBOT (aprox. R$/saca 60kg)',
        'descricao': 'Soybeans — CBOT/CME (referência para Soja B3)',
    },
    {
        'id': 'cafe',
        'nome': 'Café Arábica',
        'symbol': 'KC=F',
        'unidade_int': 'USc/lb',
        'unidade_br':  'R$/sc (60kg)',
        'cor': '#8D6E63',
        'conv_br_nota': 'Referência: Coffee C ICE (aprox. R$/saca 60kg)',
        'descricao': 'Coffee C — ICE (referência para Café Arábica B3)',
    },
    {
        'id': 'acucar',
        'nome': 'Açúcar Cristal',
        'symbol': 'SB=F',
        'unidade_int': 'USc/lb',
        'unidade_br':  'R$/sc (50kg)',
        'cor': '#AB47BC',
        'conv_br_nota': 'Referência: Sugar #11 ICE (aprox. R$/saca 50kg)',
        'descricao': 'Sugar No. 11 — ICE (referência para Açúcar B3)',
    },
    {
        'id': 'cacau',
        'nome': 'Cacau',
        'symbol': 'CC=F',
        'unidade_int': 'USD/t',
        'unidade_br':  'R$/@ (arroba)',
        'cor': '#6D4C41',
        'conv_br_nota': 'Referência: Cocoa ICE (aprox. R$/arroba 15kg)',
        'descricao': 'Cocoa — ICE (referência global para cacau)',
    },
    {
        'id': 'algodao',
        'nome': 'Algodão',
        'symbol': 'CT=F',
        'unidade_int': 'USc/lb',
        'unidade_br':  'R$/@ (arroba)',
        'cor': '#78909C',
        'conv_br_nota': 'Referência: Cotton No.2 ICE (aprox. R$/arroba)',
        'descricao': 'Cotton No. 2 — ICE (referência para Algodão B3)',
    },
    {
        'id': 'trigo',
        'nome': 'Trigo',
        'symbol': 'ZW=F',
        'unidade_int': 'USc/bu',
        'unidade_br':  'R$/sc (60kg)',
        'cor': '#FFA726',
        'conv_br_nota': 'Referência: Wheat CBOT (aprox. R$/saca 60kg)',
        'descricao': 'Wheat (SRW) — CBOT/CME (referência para Trigo)',
    },
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

# Fatores de conversão aproximados para BRL
# LE=F: USD/cwt → R$/arroba (1 cwt ≈ 45.36 kg ≈ 3.024 arrobas de 15kg)
# ZC=F e ZS=F: USc/bu → R$/saca 60kg (1 bu milho ≈ 25.4 kg; 1 bu soja ≈ 27.2 kg)
#   ZC: (p/100) USD/bu × 60/25.4 sc/bu → R$/sc = (p/100) × (60/25.4) × usd_brl
#   ZS: (p/100) USD/bu × 60/27.2 sc/bu → R$/sc = (p/100) × (60/27.2) × usd_brl
# KC=F: USc/lb → R$/saca 60kg (1 lb = 0.4536 kg; 60/0.4536 ≈ 132.3 lb/saca)
#   (p/100) × 132.3 × usd_brl
# SB=F: USc/lb → R$/saca 50kg (50/0.4536 ≈ 110.2 lb/saca)
#   (p/100) × 110.2 × usd_brl

CONV = {
    'boi':     lambda p, r: round(p / 3.024 * r, 2),             # USD/cwt → R$/arroba (1cwt=3.024@)
    'milho':   lambda p, r: round((p/100) * (60/25.40) * r, 2),  # USc/bu → R$/sc60 (1bu=25.40kg)
    'soja':    lambda p, r: round((p/100) * (60/27.22) * r, 2),  # USc/bu → R$/sc60 (1bu=27.22kg)
    'cafe':    lambda p, r: round((p/100) * 132.28 * r, 2),      # USc/lb → R$/sc60 (60/0.4536lb)
    'acucar':  lambda p, r: round((p/100) * 110.23 * r, 2),      # USc/lb → R$/sc50 (50/0.4536lb)
    'cacau':   lambda p, r: round(p * 15 / 1000 * r, 2),         # USD/t  → R$/arroba (1t=66.67@)
    'algodao': lambda p, r: round((p/100) * (15/0.4536) * r, 2), # USc/lb → R$/arroba (15/0.4536lb)
    'trigo':   lambda p, r: round((p/100) * (60/27.22) * r, 2),  # USc/bu → R$/sc60 (1bu=27.22kg)
}

# ── Funções ────────────────────────────────────────────────────────────────

def get_usd_brl():
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/USDBRL=X?range=1d&interval=1d'
    r = requests.get(url, headers=HEADERS, timeout=15)
    d = r.json()
    price = d['chart']['result'][0]['meta']['regularMarketPrice']
    return round(price, 4)


def get_commodity(symbol, comm_range, interval):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?range={comm_range}&interval={interval}')
    r = requests.get(url, headers=HEADERS, timeout=15)
    d = r.json()
    result = d['chart']['result'][0]
    meta = result['meta']
    timestamps = result.get('timestamp', [])
    quote = result['indicators']['quote'][0]

    hist = []
    for i, ts in enumerate(timestamps):
        c = quote.get('close', [])[i] if i < len(quote.get('close', [])) else None
        if c is None:
            continue
        def safe(lst, idx):
            v = lst[idx] if idx < len(lst) else None
            return round(v, 4) if v is not None else None
        hist.append({
            'data': datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d'),
            'fechamento': round(c, 4),
            'abertura':   safe(quote.get('open', []), i),
            'maximo':     safe(quote.get('high', []), i),
            'minimo':     safe(quote.get('low', []), i),
            'volume':     quote.get('volume', [])[i] if i < len(quote.get('volume', [])) else None,
        })

    prev = meta.get('chartPreviousClose') or meta.get('previousClose')
    cur = meta.get('regularMarketPrice')
    change = round(cur - prev, 4) if (cur is not None and prev is not None) else None
    change_pct = round(change / prev * 100, 4) if (change is not None and prev) else None

    return {
        'symbol':          meta.get('symbol', symbol),
        'preco':           round(cur, 4) if cur is not None else None,
        'variacao':        change,
        'variacao_pct':    change_pct,
        'abertura':        round(meta.get('regularMarketOpen', 0), 4) if meta.get('regularMarketOpen') else None,
        'maximo_dia':      round(meta.get('regularMarketDayHigh', 0), 4) if meta.get('regularMarketDayHigh') else None,
        'minimo_dia':      round(meta.get('regularMarketDayLow', 0), 4) if meta.get('regularMarketDayLow') else None,
        'fechamento_ant':  round(prev, 4) if prev else None,
        'volume':          meta.get('regularMarketVolume'),
        'semanas52_max':   meta.get('fiftyTwoWeekHigh'),
        'semanas52_min':   meta.get('fiftyTwoWeekLow'),
        'historico':       hist,
    }


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    comm_range = RANGE
    for arg in sys.argv[1:]:
        if arg.startswith('--range'):
            parts = arg.split('=')
            if len(parts) == 2:
                comm_range = parts[1]

    os.makedirs('dados', exist_ok=True)

    print('Buscando USD/BRL...')
    try:
        usd_brl = get_usd_brl()
        print(f'  USD/BRL: {usd_brl}')
    except Exception as e:
        print(f'  Erro ao buscar USD/BRL: {e}. Usando 5.20 como fallback.')
        usd_brl = 5.20

    payload = {
        'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'range': comm_range,
        'usd_brl': usd_brl,
        'commodities': [],
    }

    for c in COMMODITIES:
        print(f'Buscando {c["nome"]} ({c["symbol"]}, range={comm_range})...')
        try:
            data = get_commodity(c['symbol'], comm_range, INTERVAL)

            # Converte para BRL se houver preço
            preco_br = None
            hist_com_brl = []
            if data['preco'] is not None:
                try:
                    preco_br = CONV[c['id']](data['preco'], usd_brl)
                except Exception:
                    pass

            conv = CONV[c['id']]
            for h in data['historico']:
                entry = dict(h)
                for field in ('fechamento', 'abertura', 'maximo', 'minimo'):
                    v = h.get(field)
                    try:
                        entry[field + '_brl'] = conv(v, usd_brl) if v is not None else None
                    except Exception:
                        entry[field + '_brl'] = None
                hist_com_brl.append(entry)

            payload['commodities'].append({
                'id':           c['id'],
                'nome':         c['nome'],
                'symbol':       data['symbol'],
                'cor':          c['cor'],
                'unidade_int':  c['unidade_int'],
                'unidade_br':   c['unidade_br'],
                'conv_nota':    c['conv_br_nota'],
                'descricao':    c['descricao'],
                'preco':        data['preco'],
                'preco_brl':    preco_br,
                'variacao':     data['variacao'],
                'variacao_pct': data['variacao_pct'],
                'abertura':     data['abertura'],
                'maximo_dia':   data['maximo_dia'],
                'minimo_dia':   data['minimo_dia'],
                'fechamento_ant': data['fechamento_ant'],
                'volume':       data['volume'],
                'semanas52_max': data['semanas52_max'],
                'semanas52_min': data['semanas52_min'],
                'historico':    hist_com_brl,
                'ok': True,
            })
            print(f'  Preco: {data["preco"]} {c["unidade_int"]}  ~= R$ {preco_br} ({c["unidade_br"]})')
        except Exception as e:
            print(f'  ERRO: {e}')
            payload['commodities'].append({
                'id': c['id'], 'nome': c['nome'], 'symbol': c['symbol'],
                'cor': c['cor'], 'ok': False, 'erro': str(e),
                'unidade_int': c['unidade_int'], 'unidade_br': c['unidade_br'],
                'descricao': c['descricao'],
            })
        time.sleep(1.2)

    out_path = os.path.join('dados', 'commodities_data.js')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('/* Gerado por atualizar.py — não editar manualmente */\n')
        f.write('window.COMMODITIES_DATA = ')
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write(';\n')

    print(f'\nSalvo em {out_path}')
    print(f'USD/BRL usado: {usd_brl}')
    print('Abra o dashboard em: http://localhost:8080/brapi_dashboard/')
    print('Para servir localmente: python -m http.server 8080 (na pasta vcz-site)')


if __name__ == '__main__':
    main()
