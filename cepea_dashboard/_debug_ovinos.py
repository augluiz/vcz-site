from playwright.sync_api import sync_playwright
import json

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, args=['--disable-blink-features=AutomationControlled'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        locale='pt-BR'
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}};
    """)
    page = ctx.new_page()

    for slug in ['ovinos', 'ovos']:
        page.goto(f'https://www.cepea.org.br/br/indicador/{slug}.aspx', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(2000)

        links = page.evaluate("""() => Array.from(document.querySelectorAll('a')).filter(a =>
            a.href && (a.href.includes('consultas') || a.href.includes('tabel') ||
                       a.textContent.includes('SÉRIE') || a.textContent.includes('PREÇO') ||
                       a.textContent.includes('DADOS') || a.textContent.includes('banco'))
        ).map(a => ({text: a.textContent.trim().substring(0,80), href: a.href.substring(0,120)}))""")

        print(f'{slug} links: {json.dumps(links[:8], ensure_ascii=False)}')

        # Check page radios / inputs
        inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input[id^="subtipo"]')).map(r =>
            ({id: r.id, val: r.value, checked: r.checked}))""")
        print(f'  subtipo radios: {inputs[:5]}')

        # Check visible price text
        text = page.evaluate("""() => {
            const ps = document.querySelectorAll('p,td,span,div');
            for (const p of ps) {
                const t = p.textContent.trim();
                if (/R\\$\\s*\\d/.test(t) && t.length < 80) return t;
            }
            return null;
        }""")
        print(f'  preco visivel: {text}')

    browser.close()
