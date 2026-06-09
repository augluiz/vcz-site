# VCZ Consultoria — Site Institucional

## O que é este projeto
Site estático em HTML/CSS/JS puro, hospedado no **GitHub Pages** em `vczconsultoria.com.br`.
Deploy automático a cada `git push origin master`. Sem build step, sem frameworks, sem dependências além do Google Fonts.

## Estrutura de arquivos
```
index.html              → Página principal (PT-BR) — página-mãe
servicos.html           → Página de serviços detalhados
insights/index.html     → Listagem de artigos e estudos
insights/*.html         → Artigos individuais
en/index.html           → Versão em inglês
es/index.html           → Versão em espanhol
en/privacy.html         → Privacy Policy (EN)
es/privacidad.html      → Política de Privacidad (ES)
privacidade.html        → Política de Privacidade (PT)
termos.html             → Termos de Uso
sitemap.xml             → Mapa do site para o Google
robots.txt              → Permissões de rastreamento
CNAME                   → vczconsultoria.com.br
VCZ_Consultoria_Portfolio.pdf → Portfolio para download
```

## Design System
- **Paleta:** `--navy: #0D1B2A` · `--navy2: #162B40` · `--gold: #C8922A` · `--gold-light: #E2AC4C` · `--gold-aged: #B7A073` · `--warm-white: #F0EDED` · `--cream: #F5F0E8` · `--fog: #D4DDED` · `--steel: #9AAABB` · `--graphite: #2E2E2E`
- **Fontes:** Cormorant Garamond (títulos, serifado) · DM Sans (corpo) · DM Mono (labels, CTAs, monospace)
- **Padrão de seção:** `section-label` (DM Mono, gold, uppercase) → `section-title` (Cormorant Garamond, warm-white) → conteúdo

## Seções da index.html (ordem)
1. NAV — fixa no topo, hambúrguer mobile, seletor de idioma
2. HERO — título + CTA
3. SOBRE — texto + cards 2×2 dos produtos
4. ENTREGAS — grid 5 colunas de entregáveis analíticos
5. FRENTE — bio do Augusto Luiz + botão portfolio
6. CONTATO — formulário Formspree + info de contato
7. FOOTER

## Formulário de contato
Usa **Formspree** (`formspree.io/f/mojzjllq`) → e-mail chega em `vcz.grupo@gmail.com`.
Para trocar destino: criar novo form em formspree.io e atualizar o ID no `handleSubmit`.

## Política de idiomas
`index.html` é a **página-mãe PT-BR**. Toda nova funcionalidade deve ser validada aqui primeiro, depois replicada para `en/index.html` e `es/index.html`.

## Posts para redes sociais
- `post-story.html` → Story 1080×1920px
- `post-linkedin.html` → Post quadrado 1080×1080px
- `gerar_story.py` / `gerar_linkedin.py` → Playwright (chromium headless) gera os PNGs
- Para gerar: rodar `python -m http.server 8080` e em outro terminal `python gerar_story.py`

## Assets de logo
- `logo-ouro.svg` — logo VCZ + CONSULTORIA (nav e footer)
- `logo-mark.svg` — só o símbolo (marca d'água no hero)
- `logo-creme.svg`, `logo-full-ouro.svg`, `logo-ouro-cream.svg`, `logo-solo-ouro.svg` — variações

## Padrão de animação
Elementos com classe `reveal` ficam invisíveis e recebem `visible` via `IntersectionObserver` (fade-up). Hero usa `@keyframes fadeUp` com delays escalonados.
