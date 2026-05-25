"""
Dashboard interativo semanal de fundos - BWAG
"""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from src.readers.btg_carteira_reader import ler_carteira_btg
from src.readers.quantum_performance_reader import ler_performance
from src.readers.quantum_reader import ler_quantum

# ── Brand colors ─────────────────────────────────────────────────────────────
NAVY     = "#1C0845"
ROYAL    = "#2A1A8C"
ELECTRIC = "#4A3BE0"
PERI     = "#7B6FF0"
LAVA     = "#BFB8F5"

st.set_page_config(
    page_title="Relatório Semanal — BWAG",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
  .block-container {{ padding-top: 1.5rem; }}
  h1 {{ color: {NAVY}; }}
  h2, h3 {{ color: {ROYAL}; }}
  [data-testid="stMetricValue"] {{ color: {NAVY}; font-weight: bold; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_pct(v, dec=2):
    if v is None:
        return "—"
    return f"{v * 100:.{dec}f}%"


def _sort_key_pct(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.str.replace("%", "").str.replace("—", "nan"),
        errors="coerce",
    )


# ── Loaders (cached by file content) ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_aum(raw: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        return ler_quantum(path)
    finally:
        os.unlink(path)


@st.cache_data(show_spinner=False)
def load_perf(raw: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        return ler_performance(path)
    finally:
        os.unlink(path)


@st.cache_data(show_spinner=False)
def load_btg(raw: bytes, fname: str) -> dict | None:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        data = ler_carteira_btg(path)
        data["_filename"] = fname
        return data
    except Exception as e:
        st.sidebar.error(f"Erro ao ler {fname}: {e}")
        return None
    finally:
        os.unlink(path)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    logo_path = "templates/logo_bwag_dark.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=150)
    else:
        st.markdown(f"## **BWAG**")
    st.markdown("---")

    st.subheader("🏦 Quantum — AUM")
    f_aum = st.file_uploader("Excel de patrimônio", type=["xlsx"], key="aum")

    st.subheader("📈 Quantum — Performance")
    f_perf_a = st.file_uploader("Rentabilidade — data A", type=["xlsx"], key="perf_a")
    f_perf_b = st.file_uploader("Rentabilidade — data B (comparativo)", type=["xlsx"], key="perf_b")

    st.subheader("📋 Carteiras BTG (PDF)")
    f_btgs = st.file_uploader(
        "PDFs das carteiras",
        type=["pdf"],
        accept_multiple_files=True,
        key="btgs",
    )

    st.subheader("🔍 Comparativo de Carteira BTG")
    f_cmp_a = st.file_uploader("Carteira — data A", type=["pdf"], key="cmp_a")
    f_cmp_b = st.file_uploader("Carteira — data B", type=["pdf"], key="cmp_b")

    st.markdown("---")
    st.caption("BWAG Automações — v1.0")


# ── Load data ─────────────────────────────────────────────────────────────────
dados_aum    = load_aum(f_aum.getvalue())       if f_aum    else None
dados_perf_a = load_perf(f_perf_a.getvalue())   if f_perf_a else None
dados_perf_b = load_perf(f_perf_b.getvalue())   if f_perf_b else None
carteiras    = [c for f in (f_btgs or []) if (c := load_btg(f.getvalue(), f.name)) is not None]
cmp_btg_a    = load_btg(f_cmp_a.getvalue(), f_cmp_a.name) if f_cmp_a else None
cmp_btg_b    = load_btg(f_cmp_b.getvalue(), f_cmp_b.name) if f_cmp_b else None


# ── Page header ───────────────────────────────────────────────────────────────
st.title("📊 Relatório Semanal de Fundos")
if dados_aum:
    st.caption(f"Data base: **{dados_aum['data_base']}**")
st.divider()

if not any([dados_aum, dados_perf_a, carteiras]):
    st.info("👈 Carregue os arquivos na barra lateral para iniciar o relatório.")
    st.stop()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_geral, tab_perf, tab_cart, tab_comp = st.tabs([
    "🏦 Visão Geral",
    "🏆 Performance",
    "📋 Carteiras",
    "🔍 Comparativo",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — VISÃO GERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_geral:
    if not dados_aum:
        st.info("Carregue o Excel de AUM (Quantum) para visualizar o patrimônio dos fundos.")
    else:
        fundos = dados_aum["fundos"]
        aum    = dados_aum["aum_total"]

        c1, c2, c3 = st.columns(3)
        c1.metric("AUM Total", f"R$ {aum / 1e9:.2f}B")
        c2.metric("Nº de Fundos", len(fundos))
        c3.metric("Data Base", dados_aum["data_base"])

        st.markdown("---")

        df = pd.DataFrame(fundos)
        df["R$ MM"]       = df["valor"] / 1e6
        df["% do Total"]  = df["valor"] / aum * 100

        col_chart, col_tbl = st.columns([3, 2])

        with col_chart:
            fig = px.bar(
                df.sort_values("R$ MM"),
                x="R$ MM", y="nome_curto", orientation="h",
                title="Patrimônio por Fundo (R$ MM)",
                color="R$ MM",
                color_continuous_scale=[LAVA, NAVY],
                text_auto=".0f",
            )
            fig.update_traces(texttemplate="R$ %{x:.0f}MM", textposition="outside")
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=max(380, len(df) * 42),
                plot_bgcolor="white", paper_bgcolor="white",
                yaxis_title="", xaxis_title="R$ Milhões",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_tbl:
            df_show = (
                df[["nome_curto", "R$ MM", "% do Total"]]
                .rename(columns={"nome_curto": "Fundo"})
                .sort_values("R$ MM", ascending=False)
            )
            df_show["R$ MM"]      = df_show["R$ MM"].apply(lambda x: f"R$ {x:,.0f}MM")
            df_show["% do Total"] = df_show["% do Total"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(df_show, use_container_width=True, hide_index=True, height=420)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_perf:
    if not dados_perf_a:
        st.info("Carregue o Excel de Performance (Quantum) para ver os retornos.")
    else:
        col_radio, col_bench = st.columns([2, 2])
        with col_radio:
            periodo = st.radio(
                "Período de referência",
                ["Mês", "Ano", "12M", "24M"],
                horizontal=True,
                key="periodo_perf",
            )
        pk = {"Mês": "mes", "Ano": "ano", "12M": "m12", "24M": "m24"}[periodo]

        benchmarks = dados_perf_a.get("benchmarks", {})
        cdi  = benchmarks.get("CDI",       {}).get(pk)
        ibov = benchmarks.get("Ibovespa",  {}).get(pk)
        ipca = benchmarks.get("IPCA",      {}).get(pk)

        with col_bench:
            bc1, bc2, bc3 = st.columns(3)
            bc1.metric("CDI",       fmt_pct(cdi))
            bc2.metric("Ibovespa",  fmt_pct(ibov))
            bc3.metric("IPCA",      fmt_pct(ipca))

        st.markdown("---")

        rows = [
            {
                "Fundo":    nome,
                "Retorno":  vals.get(pk),
                "Retorno%": (vals.get(pk) or 0) * 100,
            }
            for nome, vals in dados_perf_a["fundos"].items()
            if vals.get(pk) is not None
        ]
        df_perf = pd.DataFrame(rows).sort_values("Retorno", ascending=False)

        # ── Top 5 / Bottom 5 ────────────────────────────────────────────────
        st.subheader(f"Destaques — {periodo}")
        col_top, col_bot = st.columns(2)

        with col_top:
            st.markdown("#### 🏆 Top 5")
            top5 = df_perf.head(5).iloc[::-1]
            fig_top = px.bar(
                top5, x="Retorno%", y="Fundo", orientation="h",
                color="Retorno%",
                color_continuous_scale=["#a5d6a7", "#1b5e20"],
                text_auto=".2f",
            )
            fig_top.update_traces(texttemplate="%{x:.2f}%", textposition="outside")
            fig_top.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=300, plot_bgcolor="white", paper_bgcolor="white",
                xaxis_title="", yaxis_title="",
                margin=dict(l=0, r=50, t=10, b=10),
            )
            st.plotly_chart(fig_top, use_container_width=True)

        with col_bot:
            st.markdown("#### ⚠️ Bottom 5")
            bot5 = df_perf.tail(5)
            fig_bot = px.bar(
                bot5, x="Retorno%", y="Fundo", orientation="h",
                color="Retorno%",
                color_continuous_scale=["#b71c1c", "#ef9a9a"],
                text_auto=".2f",
            )
            fig_bot.update_traces(texttemplate="%{x:.2f}%", textposition="outside")
            fig_bot.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=300, plot_bgcolor="white", paper_bgcolor="white",
                xaxis_title="", yaxis_title="",
                margin=dict(l=0, r=50, t=10, b=10),
            )
            st.plotly_chart(fig_bot, use_container_width=True)

        # ── Tabela completa ──────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Tabela Completa de Rentabilidade")

        all_rows = [
            {
                "Fundo": nome,
                "Mês":   fmt_pct(vals.get("mes")),
                "Ano":   fmt_pct(vals.get("ano")),
                "12M":   fmt_pct(vals.get("m12")),
                "24M":   fmt_pct(vals.get("m24")),
            }
            for nome, vals in dados_perf_a["fundos"].items()
        ]
        df_full = pd.DataFrame(all_rows).sort_values(
            "Mês", key=_sort_key_pct, ascending=False
        )
        st.dataframe(df_full, use_container_width=True, hide_index=True)

        if any([cdi, ibov, ipca]):
            st.caption(
                f"Benchmarks ({periodo}) — CDI: {fmt_pct(cdi)} | "
                f"Ibovespa: {fmt_pct(ibov)} | IPCA: {fmt_pct(ipca)}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CARTEIRAS BTG
# ══════════════════════════════════════════════════════════════════════════════
with tab_cart:
    if not carteiras:
        st.info("Carregue os PDFs BTG das carteiras para ver as posições.")
    else:
        opcoes = [
            f"{c.get('_filename', f'Carteira {i+1}')} — {c.get('data_base', '')}"
            for i, c in enumerate(carteiras)
        ]
        sel_idx = st.selectbox(
            "Selecionar carteira",
            range(len(opcoes)),
            format_func=lambda i: opcoes[i],
        )
        cart  = carteiras[sel_idx]
        perf  = cart.get("perf_total", {})
        bench = cart.get("pct_bench",  {})

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Data Base",     cart.get("data_base", "—"))
        c2.metric("Patrimônio",    f"R$ {cart.get('patrimonio', 0) / 1e6:.1f}M")
        c3.metric("Retorno Mês",   fmt_pct(perf.get("mes")),
                  delta=f"bench {fmt_pct(bench.get('mes'))}")
        c4.metric("Retorno Ano",   fmt_pct(perf.get("ano")),
                  delta=f"bench {fmt_pct(bench.get('ano'))}")
        c5.metric("12M",           fmt_pct(perf.get("m12")))

        st.markdown("---")

        fundos_cart = cart.get("fundos", [])
        if not fundos_cart:
            st.warning("Nenhum fundo encontrado neste PDF.")
        else:
            df_cart = pd.DataFrame(fundos_cart)

            col_pie, col_tbl = st.columns([2, 3])

            with col_pie:
                fig_pie = px.pie(
                    df_cart.head(15),
                    values="pl", names="nome",
                    title="Distribuição %PL (Top 15)",
                    color_discrete_sequence=px.colors.sequential.Purples_r,
                    hole=0.35,
                )
                fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                fig_pie.update_layout(showlegend=False, height=420)
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_tbl:
                df_show = df_cart.copy()
                for col in ["mes", "ano", "m12", "m24"]:
                    if col in df_show.columns:
                        df_show[col] = df_show[col].apply(fmt_pct)
                df_show["financeiro"] = df_show["financeiro"].apply(
                    lambda x: f"R$ {x:,.0f}"
                )
                df_show["pl"] = df_show["pl"].apply(lambda x: f"{x:.2f}%")
                df_show = df_show.rename(columns={
                    "nome": "Fundo", "pl": "%PL", "financeiro": "Financeiro",
                    "mes": "Mês", "ano": "Ano", "m12": "12M", "m24": "24M",
                })
                st.dataframe(df_show, use_container_width=True, hide_index=True, height=400)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — COMPARATIVO
# ══════════════════════════════════════════════════════════════════════════════
with tab_comp:
    sub_quantum, sub_btg = st.tabs([
        "📈 Comparativo Quantum (Excel)",
        "📋 Comparativo Carteira BTG (PDF)",
    ])

    # ── Sub-tab: Comparativo Quantum ─────────────────────────────────────────
    with sub_quantum:
        if dados_perf_a and dados_perf_b:
            label_a = f_perf_a.name if f_perf_a else "Data A"
            label_b = f_perf_b.name if f_perf_b else "Data B"

            periodo_comp = st.radio(
                "Período", ["Mês", "Ano", "12M", "24M"],
                horizontal=True, key="periodo_comp",
            )
            pk_c = {"Mês": "mes", "Ano": "ano", "12M": "m12", "24M": "m24"}[periodo_comp]

            fundos_a = dados_perf_a["fundos"]
            fundos_b = dados_perf_b["fundos"]
            todos    = sorted(set(fundos_a) | set(fundos_b))

            rows_c = []
            for nome in todos:
                va = fundos_a.get(nome, {}).get(pk_c)
                vb = fundos_b.get(nome, {}).get(pk_c)
                delta = (vb - va) if (va is not None and vb is not None) else None
                rows_c.append({
                    "Fundo":    nome,
                    label_a:   fmt_pct(va),
                    label_b:   fmt_pct(vb),
                    "Variação": fmt_pct(delta),
                    "_delta":   delta if delta is not None else 0.0,
                })

            df_cmp = pd.DataFrame(rows_c).sort_values("_delta", ascending=False)
            df_plot = df_cmp[df_cmp["_delta"] != 0.0].copy()
            df_plot["cor"] = df_plot["_delta"].apply(
                lambda x: "#2e7d32" if x >= 0 else "#c62828"
            )
            fig_delta = go.Figure(go.Bar(
                x=df_plot["Fundo"],
                y=df_plot["_delta"] * 100,
                marker_color=df_plot["cor"],
                text=[f"{v * 100:+.2f}%" for v in df_plot["_delta"]],
                textposition="outside",
            ))
            fig_delta.update_layout(
                title=f"Variação do Retorno ({periodo_comp}): {label_a} → {label_b}",
                xaxis_tickangle=-35,
                plot_bgcolor="white", paper_bgcolor="white",
                height=420, yaxis_title="Variação (p.p.)",
                showlegend=False,
            )
            st.plotly_chart(fig_delta, use_container_width=True)
            st.dataframe(df_cmp.drop(columns=["_delta"]), use_container_width=True, hide_index=True)

        elif dados_perf_a:
            st.subheader("Mapa de Calor — Rentabilidades por Período")
            st.caption("Para comparar duas datas, carregue também a 'Rentabilidade — data B' na barra lateral.")
            rows_h = {
                nome: {
                    "Mês": (vals.get("mes") or 0) * 100,
                    "Ano": (vals.get("ano") or 0) * 100,
                    "12M": (vals.get("m12") or 0) * 100,
                    "24M": (vals.get("m24") or 0) * 100,
                }
                for nome, vals in dados_perf_a["fundos"].items()
            }
            df_heat = pd.DataFrame(rows_h).T.round(2)
            fig_heat = px.imshow(
                df_heat,
                color_continuous_scale=[[0, "#c62828"], [0.5, "#ffffff"], [1, "#1b5e20"]],
                color_continuous_midpoint=0,
                text_auto=".2f",
                aspect="auto",
                title="Rentabilidades por Período (%)",
            )
            fig_heat.update_layout(height=max(420, len(df_heat) * 34))
            st.plotly_chart(fig_heat, use_container_width=True)

        else:
            st.info("Carregue pelo menos um Excel de Performance (Quantum) para ver este comparativo.")

    # ── Sub-tab: Comparativo Carteira BTG ────────────────────────────────────
    with sub_btg:
        if not cmp_btg_a or not cmp_btg_b:
            st.info(
                "👈 Carregue os dois PDFs BTG da mesma carteira na barra lateral "
                "(seção **Comparativo de Carteira BTG**) para ver a análise semanal."
            )
        else:
            da = cmp_btg_a
            db = cmp_btg_b
            pa = da.get("perf_total", {})
            pb = db.get("perf_total", {})
            pl_a = da.get("patrimonio", 0)
            pl_b = db.get("patrimonio", 0)
            delta_pl = pl_b - pl_a

            nome_fundo = da.get("_filename", "").replace(".pdf", "").replace("AcompFI_", "")

            st.subheader(nome_fundo)

            # ── Métricas de cabeçalho ────────────────────────────────────────
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Data A", da.get("data_base", "—"))
            c2.metric("Data B", db.get("data_base", "—"))
            c3.metric(
                "PL (data B)",
                f"R$ {pl_b / 1e6:.2f}M",
                delta=f"R$ {delta_pl:+,.0f} ({delta_pl / pl_a * 100:+.2f}%)" if pl_a else None,
            )
            c4.metric(
                "Retorno Mês",
                fmt_pct(pb.get("mes")),
                delta=fmt_pct((pb.get("mes") or 0) - (pa.get("mes") or 0)) + " vs data A",
            )
            c5.metric(
                "Retorno Ano",
                fmt_pct(pb.get("ano")),
                delta=fmt_pct((pb.get("ano") or 0) - (pa.get("ano") or 0)) + " vs data A",
            )
            c6.metric("12M (data B)", fmt_pct(pb.get("m12")))

            st.markdown("---")

            # ── Comparativo de posições ──────────────────────────────────────
            ativos_a = {f["nome"]: f for f in da.get("fundos", [])}
            ativos_b = {f["nome"]: f for f in db.get("fundos", [])}
            todos_ativos = sorted(set(ativos_a) | set(ativos_b))

            rows_pos = []
            for nome in todos_ativos:
                fa = ativos_a.get(nome, {})
                fb = ativos_b.get(nome, {})
                pl_fa  = fa.get("pl",  0.0)
                pl_fb  = fb.get("pl",  0.0)
                ret_a  = fa.get("mes")
                ret_b  = fb.get("mes")
                rows_pos.append({
                    "Ativo":        nome,
                    "%PL A":        pl_fa,
                    "%PL B":        pl_fb,
                    "Δ %PL":        pl_fb - pl_fa,
                    "Ret.Mês A":    ret_a,
                    "Ret.Mês B":    ret_b,
                    "Δ Ret.Mês":    (ret_b - ret_a) if (ret_a is not None and ret_b is not None) else None,
                    "Fin. B (R$)":  fb.get("financeiro", fa.get("financeiro", 0)),
                })
            df_pos = pd.DataFrame(rows_pos).sort_values("%PL B", ascending=False)

            # ── Gráfico: variação de %PL por ativo ──────────────────────────
            col_bar, col_ret = st.columns(2)

            with col_bar:
                df_bar = df_pos[df_pos["Δ %PL"] != 0].copy()
                df_bar["cor"] = df_bar["Δ %PL"].apply(
                    lambda x: "#2e7d32" if x >= 0 else "#c62828"
                )
                fig_pl = go.Figure(go.Bar(
                    x=df_bar["Ativo"],
                    y=df_bar["Δ %PL"],
                    marker_color=df_bar["cor"],
                    text=[f"{v:+.2f}p.p." for v in df_bar["Δ %PL"]],
                    textposition="outside",
                ))
                fig_pl.update_layout(
                    title=f"Variação de %PL por Ativo ({da['data_base']} → {db['data_base']})",
                    plot_bgcolor="white", paper_bgcolor="white",
                    height=360, yaxis_title="Δ %PL (p.p.)",
                    showlegend=False,
                    xaxis_tickangle=-30,
                )
                st.plotly_chart(fig_pl, use_container_width=True)

            with col_ret:
                df_ret = df_pos.dropna(subset=["Δ Ret.Mês"]).copy()
                df_ret["cor"] = df_ret["Δ Ret.Mês"].apply(
                    lambda x: "#2e7d32" if x >= 0 else "#c62828"
                )
                fig_ret = go.Figure(go.Bar(
                    x=df_ret["Ativo"],
                    y=df_ret["Δ Ret.Mês"] * 100,
                    marker_color=df_ret["cor"],
                    text=[f"{v * 100:+.2f}%" for v in df_ret["Δ Ret.Mês"]],
                    textposition="outside",
                ))
                fig_ret.update_layout(
                    title=f"Variação de Retorno Mês por Ativo",
                    plot_bgcolor="white", paper_bgcolor="white",
                    height=360, yaxis_title="Δ Ret.Mês (p.p.)",
                    showlegend=False,
                    xaxis_tickangle=-30,
                )
                st.plotly_chart(fig_ret, use_container_width=True)

            # ── Tabela detalhada ─────────────────────────────────────────────
            st.subheader("Tabela Detalhada de Posições")
            df_tbl = df_pos.copy()
            df_tbl["%PL A"]       = df_tbl["%PL A"].apply(lambda x: f"{x:.2f}%")
            df_tbl["%PL B"]       = df_tbl["%PL B"].apply(lambda x: f"{x:.2f}%")
            df_tbl["Δ %PL"]       = df_tbl["Δ %PL"].apply(lambda x: f"{x:+.2f}p.p.")
            df_tbl["Ret.Mês A"]   = df_tbl["Ret.Mês A"].apply(fmt_pct)
            df_tbl["Ret.Mês B"]   = df_tbl["Ret.Mês B"].apply(fmt_pct)
            df_tbl["Δ Ret.Mês"]   = df_tbl["Δ Ret.Mês"].apply(
                lambda x: f"{x * 100:+.2f}p.p." if x is not None else "—"
            )
            df_tbl["Fin. B (R$)"] = df_tbl["Fin. B (R$)"].apply(lambda x: f"R$ {x:,.0f}")
            st.dataframe(df_tbl, use_container_width=True, hide_index=True)

            # ── Destaques ────────────────────────────────────────────────────
            st.markdown("---")
            st.subheader("Destaques da Semana")
            df_dest = df_pos.dropna(subset=["Δ Ret.Mês"]).sort_values("Δ Ret.Mês", ascending=False)

            col_hi, col_lo = st.columns(2)
            with col_hi:
                st.markdown("**Maiores avanços (Ret. Mês)**")
                for _, row in df_dest.head(3).iterrows():
                    delta_ret = row["Δ Ret.Mês"] * 100
                    st.success(
                        f"**{row['Ativo']}** — {fmt_pct(row['Ret.Mês B'])} "
                        f"({delta_ret:+.2f}p.p. vs data A)"
                    )
            with col_lo:
                st.markdown("**Maiores quedas (Ret. Mês)**")
                for _, row in df_dest.tail(3).iloc[::-1].iterrows():
                    delta_ret = row["Δ Ret.Mês"] * 100
                    st.error(
                        f"**{row['Ativo']}** — {fmt_pct(row['Ret.Mês B'])} "
                        f"({delta_ret:+.2f}p.p. vs data A)"
                    )
