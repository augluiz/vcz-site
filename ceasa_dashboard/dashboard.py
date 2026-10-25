"""
Dashboard CEASA/SC — Cotações de Preços 2026
Execute com: streamlit run dashboard.py
"""

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

CSV_PATH = "dados/ceasa_2026.csv"

st.set_page_config(
    page_title="CEASA/SC — Cotações",
    page_icon="🥦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Carga de dados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", parse_dates=["data"])
    df["data"] = pd.to_datetime(df["data"])
    df["mes"] = df["data"].dt.to_period("M").astype(str)
    return df


try:
    df = load_data()
except FileNotFoundError:
    st.error(f"Arquivo `{CSV_PATH}` não encontrado. Execute `extrair_ceasa.py` primeiro.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — Filtros
# ---------------------------------------------------------------------------

st.sidebar.title("Filtros")

unidades = sorted(df["unidade"].dropna().unique())
sel_unidades = st.sidebar.multiselect("Unidade CEASA", unidades, default=unidades)

datas = sorted(df["data"].dt.date.unique())
data_min, data_max = datas[0], datas[-1]
sel_periodo = st.sidebar.date_input(
    "Período",
    value=(data_min, data_max),
    min_value=data_min,
    max_value=data_max,
)

produtos = sorted(df["descricao"].dropna().unique())
sel_produtos = st.sidebar.multiselect(
    "Produto (para gráfico de evolução)",
    produtos,
    default=produtos[:5] if len(produtos) >= 5 else produtos,
)

# ---------------------------------------------------------------------------
# Aplicar filtros
# ---------------------------------------------------------------------------

mask = df["unidade"].isin(sel_unidades)
if len(sel_periodo) == 2:
    mask &= df["data"].dt.date.between(sel_periodo[0], sel_periodo[1])
df_fil = df[mask]

# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------

st.title("🥦 CEASA/SC — Cotações de Preços 2026")
st.caption(f"Dados extraídos de ceasa.sc.gov.br · {len(df_fil):,} registros exibidos")

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
col1.metric("Registros", f"{len(df_fil):,}")
col2.metric("Produtos únicos", f"{df_fil['descricao'].nunique():,}")
col3.metric("Dias com cotação", f"{df_fil['data'].nunique():,}")
col4.metric("Unidades", f"{df_fil['unidade'].nunique():,}")

st.divider()

# ---------------------------------------------------------------------------
# Evolução de preço — produtos selecionados
# ---------------------------------------------------------------------------

st.subheader("📈 Evolução do Preço Comum/Kg")

if sel_produtos:
    df_evolucao = (
        df_fil[df_fil["descricao"].isin(sel_produtos)]
        .groupby(["data", "descricao"], as_index=False)["preco_comum_kg"]
        .mean()
    )

    if df_evolucao.empty:
        st.info("Sem dados para os produtos e filtros selecionados.")
    else:
        fig_evolucao = px.line(
            df_evolucao,
            x="data",
            y="preco_comum_kg",
            color="descricao",
            labels={
                "data": "Data",
                "preco_comum_kg": "Preço Médio (R$/kg)",
                "descricao": "Produto",
            },
            template="plotly_white",
        )
        fig_evolucao.update_layout(legend_title_text="Produto", height=420)
        st.plotly_chart(fig_evolucao, use_container_width=True)
else:
    st.info("Selecione ao menos um produto no filtro lateral.")

# ---------------------------------------------------------------------------
# Tabela de cotações do dia mais recente
# ---------------------------------------------------------------------------

st.subheader("📋 Cotações do Dia Mais Recente")

ultimo_dia = df_fil["data"].max()
df_hoje = df_fil[df_fil["data"] == ultimo_dia].copy()

if not df_hoje.empty:
    st.caption(f"Data: **{ultimo_dia.strftime('%d/%m/%Y')}**")

    tab_unidades = st.tabs(sorted(df_hoje["unidade"].unique()))
    for tab, unid in zip(tab_unidades, sorted(df_hoje["unidade"].unique())):
        with tab:
            df_tab = (
                df_hoje[df_hoje["unidade"] == unid][[
                    "descricao", "tipo", "origem", "embalagem",
                    "qtd_embalagem", "preco_minimo", "preco_comum",
                    "preco_maximo", "preco_comum_kg",
                ]]
                .rename(columns={
                    "descricao":      "Produto",
                    "tipo":           "Tipo",
                    "origem":         "Origem",
                    "embalagem":      "Embalagem",
                    "qtd_embalagem":  "Qtd",
                    "preco_minimo":   "Mínimo (R$)",
                    "preco_comum":    "Comum (R$)",
                    "preco_maximo":   "Máximo (R$)",
                    "preco_comum_kg": "R$/kg",
                })
                .reset_index(drop=True)
            )
            st.dataframe(df_tab, use_container_width=True, height=500)

st.divider()

# ---------------------------------------------------------------------------
# Ranking de preços — média do período
# ---------------------------------------------------------------------------

col_rank1, col_rank2 = st.columns(2)

with col_rank1:
    st.subheader("🏆 Mais Caros (R$/kg)")
    df_rank = (
        df_fil.groupby("descricao", as_index=False)["preco_comum_kg"]
        .mean()
        .sort_values("preco_comum_kg", ascending=False)
        .head(15)
    )
    fig_rank = px.bar(
        df_rank,
        x="preco_comum_kg",
        y="descricao",
        orientation="h",
        labels={"preco_comum_kg": "Preço Médio (R$/kg)", "descricao": ""},
        template="plotly_white",
        color="preco_comum_kg",
        color_continuous_scale="Reds",
    )
    fig_rank.update_layout(coloraxis_showscale=False, height=450)
    st.plotly_chart(fig_rank, use_container_width=True)

with col_rank2:
    st.subheader("💚 Mais Baratos (R$/kg)")
    df_rank2 = (
        df_fil[df_fil["preco_comum_kg"] > 0]
        .groupby("descricao", as_index=False)["preco_comum_kg"]
        .mean()
        .sort_values("preco_comum_kg")
        .head(15)
    )
    fig_rank2 = px.bar(
        df_rank2,
        x="preco_comum_kg",
        y="descricao",
        orientation="h",
        labels={"preco_comum_kg": "Preço Médio (R$/kg)", "descricao": ""},
        template="plotly_white",
        color="preco_comum_kg",
        color_continuous_scale="Greens",
    )
    fig_rank2.update_layout(coloraxis_showscale=False, height=450)
    st.plotly_chart(fig_rank2, use_container_width=True)

# ---------------------------------------------------------------------------
# Variação de preço — mês a mês
# ---------------------------------------------------------------------------

st.subheader("📊 Variação Mensal Média (R$/kg)")

df_mensal = (
    df_fil.groupby(["mes", "unidade"], as_index=False)["preco_comum_kg"]
    .mean()
    .rename(columns={"preco_comum_kg": "preco_medio_kg"})
)

if not df_mensal.empty:
    fig_mensal = px.bar(
        df_mensal,
        x="mes",
        y="preco_medio_kg",
        color="unidade",
        barmode="group",
        labels={
            "mes": "Mês",
            "preco_medio_kg": "Preço Médio (R$/kg)",
            "unidade": "Unidade",
        },
        template="plotly_white",
    )
    fig_mensal.update_layout(height=380)
    st.plotly_chart(fig_mensal, use_container_width=True)

# ---------------------------------------------------------------------------
# Download do CSV filtrado
# ---------------------------------------------------------------------------

st.divider()
st.subheader("⬇️ Exportar dados")

csv_export = df_fil.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    label="Baixar CSV filtrado",
    data=csv_export,
    file_name="ceasa_filtrado.csv",
    mime="text/csv",
)
