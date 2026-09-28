from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto('http://localhost:8080/cepea_dashboard/', wait_until='networkidle', timeout=15000)
    page.wait_for_timeout(2000)
    page.evaluate("selectProd('milho')")
    page.wait_for_timeout(1800)

    # Check for JS errors
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.wait_for_timeout(500)

    # Screenshot focused on the main content area (below nav, below cards)
    page.evaluate("window.scrollTo(0, 200)")
    page.wait_for_timeout(300)
    page.screenshot(path='_screenshot.png', clip={'x': 0, 'y': 170, 'width': 1440, 'height': 700})
    print('Erros JS:', errors)
    browser.close()
    print('Screenshot salvo')
