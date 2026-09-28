"""Gera cepea_data.js com dados fictícios para visualizar o dashboard."""
import json, random, math
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

def gerar_serie(preco_base, volatilidade, n_dias=120):
    hist = []
    preco = preco_base
    d = date(2025, 1, 2)
    fim = date.today()
    while d <= fim:
        if d.weekday() < 5:  # dias úteis
            preco *= 1 + random.gauss(0, volatilidade)
            preco = max(preco * 0.5, preco)
            hist.append({'data': d.isoformat(), 'preco': round(preco, 2)})
        d += timedelta(days=1)
    return hist

PRODUTOS = [
    # Preços base próximos dos valores reais CEPEA (junho/2026)
    {'id':'acucar',  'nome':'Açúcar',   'unidade':'R$/sc 50kg','praca':'São Paulo/SP', 'cor':'#AB47BC', 'base':92.5, 'vol':0.006},
    {'id':'algodao', 'nome':'Algodão',  'unidade':'R$/arroba', 'praca':'São Paulo/SP', 'cor':'#78909C', 'base':118,  'vol':0.007},
    {'id':'arroz',   'nome':'Arroz',    'unidade':'R$/sc 50kg','praca':'RS/SC',        'cor':'#E8D44D', 'base':86,   'vol':0.006},
    {'id':'bezerro', 'nome':'Bezerro',  'unidade':'R$/cab.',   'praca':'Mato Grosso',  'cor':'#D2691E', 'base':2150, 'vol':0.005},
    {'id':'boi',     'nome':'Boi Gordo','unidade':'R$/arroba', 'praca':'São Paulo/SP', 'cor':'#E06060', 'base':330,  'vol':0.005},
    {'id':'cafe',    'nome':'Café',     'unidade':'R$/sc 60kg','praca':'Cerrado/MG',   'cor':'#8D6E63', 'base':1780, 'vol':0.010},
    {'id':'etanol',  'nome':'Etanol',   'unidade':'R$/litro',  'praca':'Interior SP',  'cor':'#5B8FC4', 'base':3.52, 'vol':0.008},
    {'id':'feijao',  'nome':'Feijão',   'unidade':'R$/sc 60kg','praca':'São Paulo/SP', 'cor':'#8B4513', 'base':315,  'vol':0.010},
    {'id':'frango',  'nome':'Frango',   'unidade':'R$/kg',     'praca':'Paraná/PR',    'cor':'#FF8C00', 'base':6.95, 'vol':0.006},
    {'id':'leite',   'nome':'Leite',    'unidade':'R$/litro',  'praca':'Brasil',        'cor':'#B0C4DE', 'base':2.42, 'vol':0.005},
    {'id':'mandioca','nome':'Mandioca', 'unidade':'R$/t',      'praca':'Paraná/PR',    'cor':'#DAA520', 'base':480,  'vol':0.007},
    {'id':'milho',   'nome':'Milho',    'unidade':'R$/sc 60kg','praca':'Campinas/SP',  'cor':'#D4A830', 'base':79,   'vol':0.008},
    {'id':'ovinos',  'nome':'Ovinos',   'unidade':'R$/kg',     'praca':'São Paulo/SP', 'cor':'#A9A9A9', 'base':17.2, 'vol':0.006},
    {'id':'ovos',    'nome':'Ovos',     'unidade':'R$/dz',     'praca':'São Paulo/SP', 'cor':'#C8B400', 'base':15.1, 'vol':0.007},
    {'id':'soja',    'nome':'Soja',     'unidade':'R$/sc 60kg','praca':'Paranaguá/PR', 'cor':'#4CAF50', 'base':144,  'vol':0.009},
    {'id':'suino',   'nome':'Suíno',    'unidade':'R$/kg',     'praca':'Paraná/PR',    'cor':'#FF8FAB', 'base':8.10, 'vol':0.006},
    {'id':'tilapia', 'nome':'Tilápia',  'unidade':'R$/kg',     'praca':'São Paulo/SP', 'cor':'#40E0D0', 'base':8.80, 'vol':0.005},
    {'id':'trigo',   'nome':'Trigo',    'unidade':'R$/sc 60kg','praca':'Paraná/PR',    'cor':'#FFA726', 'base':93,   'vol':0.007},
]

produtos_out = []
for p in PRODUTOS:
    hist = gerar_serie(p['base'], p['vol'])
    preco = hist[-1]['preco']
    ant   = hist[-2]['preco'] if len(hist) > 1 else preco
    var   = round(preco - ant, 4)
    varp  = round(var / ant * 100, 4) if ant else 0
    produtos_out.append({
        'id': p['id'], 'nome': p['nome'],
        'unidade': p['unidade'], 'praca': p['praca'], 'cor': p['cor'],
        'descricao': f'CEPEA/ESALQ · {p["nome"]} · {p["praca"]}',
        'preco': preco, 'preco_ant': ant,
        'variacao': var, 'variacao_pct': varp,
        'data_ref': hist[-1]['data'],
        'historico': hist, 'ok': True,
    })

payload = {
    'timestamp': date.today().isoformat() + 'T08:00:00',
    'fonte': 'CEPEA/ESALQ-USP (DADOS FICTÍCIOS — rode atualizar.py para dados reais)',
    'data_inicio': '02/01/2025',
    'data_fim': date.today().strftime('%d/%m/%Y'),
    'produtos': produtos_out,
}

out = Path('dados/cepea_data.js')
out.write_text(
    '/* MOCK — rode atualizar.py para dados reais */\nwindow.CEPEA_DATA = '
    + json.dumps(payload, ensure_ascii=False, indent=2) + ';\n',
    encoding='utf-8'
)
print(f'Gerado: {out}  ({len(produtos_out)} produtos)')
