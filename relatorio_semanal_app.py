"""
Dashboard semanal de fundos BWAG
- Admin (senha): faz upload de PDFs e publica os dados
- Viewer (todos): vê o dashboard com os dados salvos
"""
import base64
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from src.readers.btg_carteira_reader import ler_carteira_btg

# ── Paleta BWAG ──────────────────────────────────────────────────────────────
NAVY     = "#1C0845"
ROYAL    = "#2A1A8C"
ELECTRIC = "#4A3BE0"
PERIW    = "#7B6FF0"
LAVA     = "#BFB8F5"
CINZA_BG = "#F4F4F6"
CINZA_TX = "#6B6B7B"
PRETO    = "#0A0420"
BWAG_COLORS = [NAVY, ROYAL, ELECTRIC, PERIW, LAVA, "#9F96F3", "#D4D0F8"]

GITHUB_DATA_PATH = "data/reports/latest_data.json"

# ── Logo (base64 para embed inline) ──────────────────────────────────────────
def _logo_b64() -> str:
    p = Path(__file__).parent / "assets" / "logo_bwag_dark.png"
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    return ""

_LOGO = _logo_b64()

st.set_page_config(
    page_title="Relatório Semanal — BWAG",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {{ font-family: 'Inter', sans-serif !important; }}

/* ── Layout ── */
.main .block-container {{
    padding-top: 0 !important;
    padding-bottom: 2rem;
    max-width: 1400px;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {NAVY} 0%, {ROYAL} 100%) !important;
}}
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] small {{
    color: {LAVA} !important;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    color: #ffffff !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: rgba(191,184,245,0.25) !important;
}}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {{
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(191,184,245,0.4) !important;
    color: white !important;
    border-radius: 6px;
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] {{
    background: rgba(255,255,255,0.07);
    border: 1px dashed rgba(191,184,245,0.4);
    border-radius: 8px;
    padding: 0.5rem;
}}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tab"] {{
    font-weight: 500;
    color: {CINZA_TX};
    padding: 0.5rem 1.2rem;
    border-radius: 6px 6px 0 0;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: {ELECTRIC} !important;
    border-bottom: 3px solid {ELECTRIC} !important;
    font-weight: 600;
}}

/* ── Metrics ── */
[data-testid="stMetricLabel"] {{
    color: {CINZA_TX} !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
[data-testid="stMetricValue"] {{
    color: {NAVY} !important;
    font-weight: 700 !important;
}}

/* ── Buttons ── */
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {ROYAL}, {ELECTRIC}) !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    padding: 0.4rem 1.2rem !important;
}}
.stButton > button[kind="secondary"] {{
    background: transparent !important;
    border: 1.5px solid {ELECTRIC} !important;
    color: {ELECTRIC} !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
}}

/* ── Expanders ── */
[data-testid="stExpander"] {{
    border: 1px solid {LAVA} !important;
    border-radius: 10px !important;
    background: white !important;
}}
[data-testid="stExpander"] summary span {{
    color: {NAVY} !important;
    font-weight: 600;
}}

/* ── Headings ── */
h1, h2 {{ color: {NAVY} !important; }}
h3 {{ color: {ROYAL} !important; }}

/* ── Selectbox / labels ── */
[data-testid="stSelectbox"] label,
[data-testid="stRadio"] label {{
    color: {NAVY} !important;
    font-weight: 600 !important;
}}

/* ── Divider ── */
hr {{ border-color: {LAVA}44 !important; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_pct(v, dec=2):
    try:
        if v is None or pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{v * 100:.{dec}f}%"

def _nome_fundo(fname: str) -> str:
    nome = re.sub(r'\.pdf$', '', fname, flags=re.IGNORECASE).strip()
    # Formato acompfi_NOME_Cota_Normal/Gerencial_YYYY_MM_DD
    m = re.match(r'^acompfi_(.+?)_Cota_(?:Normal|Gerencial)_\d{4}[_-]\d{2}[_-]\d{2}', nome, re.IGNORECASE)
    if m:
        return m.group(1).replace('_', ' ').strip()
    # Formato Bradesco_DDMMYYYY_NNNNN → nome vem do PDF, retorna placeholder
    if re.match(r'^Bradesco_\d+', nome, re.IGNORECASE):
        return nome  # será sobrescrito pelo nome interno do PDF
    # Formatos BTG antigos
    nome = re.sub(r'^AcompFI_', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'[_ ]\d{8}.*$', '', nome)
    nome = re.sub(r'[_ ]\d{2}[./]\d{2}[./]\d{4}.*$', '', nome)
    nome = re.sub(r'[_ ]\d{2}[./]\d{2}[./]\d{2}.*$', '', nome)
    nome = re.sub(r'[\s\-_]+$', '', nome)
    return nome.strip()

def _data_do_arquivo(fname: str) -> str:
    """Extrai data do nome do arquivo. Mais confiável que o conteúdo do PDF."""
    # Formato YYYY_MM_DD  ex: _2026_06_05  (acompfi_XXXX_Cota_Normal_2026_06_05)
    m = re.search(r'[_-](\d{4})[_-](\d{2})[_-](\d{2})(?:\.pdf|$)', fname, re.IGNORECASE)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    # Formato YYYYMMDD  ex: _20260515.pdf
    m = re.search(r'[_ -](\d{8})(?:\s|\.|$|\()', fname)
    if m:
        d = m.group(1)
        return f"{d[6:8]}/{d[4:6]}/{d[:4]}"
    # Formato DD.MM.YYYY ou DD/MM/YYYY  ex: - 30.04.2026.pdf
    m = re.search(r'[_ -](\d{2})[./](\d{2})[./](\d{4})(?:\s|\.|$|\()', fname)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return ""

def _parse_data(data_str: str):
    try:
        return datetime.strptime(data_str, "%d/%m/%Y")
    except Exception:
        return datetime.min


# ── GitHub storage ────────────────────────────────────────────────────────────
def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

def merge_dados(existentes: list, novos: list) -> list:
    """Mescla novos uploads com o histórico existente. Mesmo fundo+data → substitui."""
    merged = {(d.get("_nome", ""), d.get("data_base", "")): d for d in existentes}
    adicionados, atualizados = 0, 0
    for d in novos:
        key = (d.get("_nome", ""), d.get("data_base", ""))
        if key in merged:
            atualizados += 1
        else:
            adicionados += 1
        merged[key] = d
    return list(merged.values()), adicionados, atualizados

def github_save(dados: list, token: str, repo: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/contents/{GITHUB_DATA_PATH}"
    # Busca SHA se já existe
    r = requests.get(url, headers=_gh_headers(token), timeout=10)
    sha = r.json().get("sha") if r.status_code == 200 else None

    # Serializa — datetime vira string via default=str
    content = json.dumps(dados, ensure_ascii=False, indent=2, default=str)
    payload = {
        "message": f"update: relatorio semanal {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=_gh_headers(token), json=payload, timeout=15)
    return r.status_code in (200, 201)

@st.cache_data(ttl=300, show_spinner=False)
def _limpar_zeros(d: dict) -> dict:
    """Converte m12/m24 = 0.0 para None (placeholder de dado inexistente)."""
    for secao in ("perf_total", "pct_bench"):
        perf = d.get(secao) or {}
        for k in ("m12", "m24"):
            if perf.get(k) == 0.0:
                perf[k] = None
    for f in d.get("fundos", []):
        if f.get("m24") == 0.0:
            f["m24"] = None
        if f.get("m12") == 0.0:
            f["m12"] = None
    return d


def github_load(token: str, repo: str):
    url = f"https://api.github.com/repos/{repo}/contents/{GITHUB_DATA_PATH}"
    r = requests.get(url, headers=_gh_headers(token), timeout=10)
    if r.status_code != 200:
        return None, None
    meta = r.json()
    content = base64.b64decode(meta["content"]).decode()
    dados = json.loads(content)
    for d in dados:
        d["_dt"] = _parse_data(d.get("data_base", ""))
        _limpar_zeros(d)
    return dados, meta.get("sha")


# ── Loaders de PDF ────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_btg(raw: bytes, fname: str):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        import pdfplumber as _plumber
        with _plumber.open(path) as _pdf:
            data_raw_p1   = _pdf.pages[0].extract_text() or ""
            data_tabelas_p1 = _pdf.pages[0].extract_tables() or []
        data = ler_carteira_btg(path)
        data["_filename"]    = fname
        # Tenta extrair nome do fundo de dentro do PDF
        _nome_pdf = None
        if re.match(r'^acompfi_', fname, re.IGNORECASE):
            # BTG Performance Diário: linha 2 da pág 1 é o nome do fundo
            linhas = [l.strip() for l in data_raw_p1.split('\n') if l.strip()]
            if len(linhas) >= 2:
                _nome_pdf = linhas[1]
        elif re.match(r'^Bradesco_', fname, re.IGNORECASE):
            # Bradesco: "Cliente : NOME DO FUNDO"
            m_cli = re.search(r'Cliente\s*:\s*(.+)', data_raw_p1)
            if m_cli:
                _nome_pdf = m_cli.group(1).strip()
        data["_nome"] = _nome_pdf or _nome_fundo(fname)
        data["_raw_p1"]      = data_raw_p1
        data["_tabelas_p1"]  = data_tabelas_p1
        # Data do arquivo é mais confiável que a data interna do PDF
        data_arq = _data_do_arquivo(fname)
        if data_arq:
            data["data_base"] = data_arq
        data["_dt"]       = _parse_data(data.get("data_base", ""))
        _limpar_zeros(data)
        return data
    except Exception as e:
        st.sidebar.error(f"Erro ao ler {fname}: {e}")
        return None
    finally:
        os.unlink(path)

def agrupar(carteiras: list) -> dict:
    grupos = {}
    for c in carteiras:
        grupos.setdefault(c["_nome"], []).append(c)
    for n in grupos:
        grupos[n].sort(key=lambda c: c["_dt"])
    return grupos


# ── Secrets ───────────────────────────────────────────────────────────────────
ADMIN_PWD    = st.secrets.get("ADMIN_PASSWORD", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "")


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _sb_logo = f'<img src="data:image/png;base64,{_LOGO}" style="height:36px;filter:brightness(0) invert(1);margin-bottom:4px;">' if _LOGO else '<span style="color:white;font-size:1.3rem;font-weight:800;">BWAG.</span>'
    st.markdown(f"""
    <div style="padding:0.8rem 0 0.4rem 0;">
        {_sb_logo}
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    senha = st.text_input("Senha admin", type="password", key="senha", placeholder="••••••••")
    is_admin = (senha == ADMIN_PWD and ADMIN_PWD != "")

    if is_admin:
        st.success("✓ Modo admin ativo")
        st.markdown("---")
        st.markdown(f'<p style="color:white;font-weight:600;margin-bottom:4px;">Carregar PDFs</p>', unsafe_allow_html=True)
        st.caption("Pode misturar fundos e datas")
        f_pdfs = st.file_uploader(
            "PDFs", type=["pdf"], accept_multiple_files=True,
            key="pdfs", label_visibility="collapsed",
        )
    else:
        f_pdfs = []
        if senha and senha != ADMIN_PWD:
            st.error("Senha incorreta")

    st.markdown("---")
    st.markdown(f'<p style="color:{LAVA};font-size:0.72rem;text-align:center;opacity:0.7;">Automações BWAG — v2.0</p>', unsafe_allow_html=True)


# ── Carregar dados ────────────────────────────────────────────────────────────
if is_admin and f_pdfs:
    # Admin com arquivos carregados → usa os uploads
    carteiras_raw = [
        c for f in f_pdfs
        if (c := load_btg(f.getvalue(), f.name)) is not None
    ]
    fonte = "upload"
    # Debug temporário — mostra o que foi detectado por arquivo
    with st.sidebar.expander("🔍 Debug arquivos", expanded=False):
        for f in f_pdfs:
            data_arq = _data_do_arquivo(f.name)
            nome_arq = _nome_fundo(f.name)
            c = next((x for x in carteiras_raw if x.get("_filename") == f.name), {})
            st.code(
                f"Arquivo : {f.name}\n"
                f"Nome    : {nome_arq}\n"
                f"Data    : {data_arq or '(não encontrada)'}\n"
                f"Patrim. : {c.get('patrimonio', 'N/A')}\n"
                f"Ret.Mês : {c.get('perf_total', {}).get('mes', 'N/A')}\n"
                f"Posições: {len(c.get('fundos', []))}"
            )
            if c.get("patrimonio", 1) == 0.0:
                st.text("--- Texto pág 1 (debug) ---")
                st.code(c.get("_raw_p1", "")[:2000])
                st.text("--- Tabelas pág 1 (debug) ---")
                st.code(str(c.get("_tabelas_p1", []))[:2000])
else:
    # Todos os outros → carrega do GitHub
    dados_salvos, _ = github_load(GITHUB_TOKEN, GITHUB_REPO)
    carteiras_raw   = dados_salvos or []
    fonte           = "github"

grupos        = agrupar(carteiras_raw)
mais_recentes = {nome: datas[-1] for nome, datas in grupos.items()}
fundos_comp   = [n for n, d in grupos.items() if len(d) >= 2]


# ── Header ────────────────────────────────────────────────────────────────────
_logo_html = f'<img src="data:image/png;base64,{_LOGO}" style="height:42px;filter:brightness(0) invert(1);vertical-align:middle;">' if _LOGO else '<span style="font-size:1.4rem;font-weight:800;color:white;letter-spacing:2px;">BWAG.</span>'
st.markdown(f"""
<div style="
    background: linear-gradient(135deg, {NAVY} 0%, {ROYAL} 55%, {ELECTRIC} 100%);
    padding: 1.1rem 2rem;
    margin: -2rem -4rem 1.5rem -4rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    box-shadow: 0 2px 12px rgba(28,8,69,0.3);
">
    {_logo_html}
    <div style="width:1px;height:40px;background:rgba(191,184,245,0.4);"></div>
    <div>
        <div style="color:white;font-size:1.3rem;font-weight:700;letter-spacing:0.3px;line-height:1.2;">Relatório Semanal de Fundos</div>
    </div>
</div>
""", unsafe_allow_html=True)

if not carteiras_raw:
    if is_admin:
        st.info("👈 Carregue os PDFs na barra lateral para começar.")
    else:
        st.info("Aguardando publicação dos dados pelo administrador.")
    st.stop()

# Botão de publicar (admin)
if is_admin and fonte == "upload":
    col_pub, col_sub, col_info = st.columns([2, 2, 3])
    with col_pub:
        if st.button("💾 Salvar e publicar", type="primary"):
            with st.spinner("Salvando no GitHub..."):
                dados_existentes, _ = github_load(GITHUB_TOKEN, GITHUB_REPO)
                dados_merged, adicionados, atualizados = merge_dados(dados_existentes or [], carteiras_raw)
                ok = github_save(dados_merged, GITHUB_TOKEN, GITHUB_REPO)
            if ok:
                partes = []
                if adicionados: partes.append(f"{adicionados} novo(s)")
                if atualizados: partes.append(f"{atualizados} atualizado(s)")
                detalhe = f" ({', '.join(partes)})" if partes else ""
                st.success(f"Publicado{detalhe}! Histórico total: {len(dados_merged)} relatório(s).")
            else:
                st.error("Erro ao salvar. Verifique o token do GitHub.")
    with col_sub:
        if st.button("🗑️ Substituir tudo", help="Apaga o histórico e salva APENAS os PDFs carregados agora"):
            with st.spinner("Substituindo..."):
                ok = github_save(carteiras_raw, GITHUB_TOKEN, GITHUB_REPO)
            if ok:
                st.success(f"Histórico substituído. {len(carteiras_raw)} relatório(s) salvos.")
            else:
                st.error("Erro ao salvar.")

# Info de atualização
datas_base = sorted(set(c.get("data_base","") for c in carteiras_raw if c.get("data_base")))
st.caption(f"Dados de: **{' · '.join(datas_base)}**")
st.divider()

# Resumo
col_r1, col_r2, col_r3 = st.columns(3)
col_r1.metric("Fundos", len(grupos))
col_r2.metric("PDFs",   len(carteiras_raw))
col_r3.metric("Com comparativo", len(fundos_comp))

if len(fundos_comp) == 0 and len(carteiras_raw) > 1:
    with st.expander("🔎 Fundos detectados", expanded=True):
        for nome, datas in grupos.items():
            dts = " · ".join(c.get("data_base","?") for c in datas)
            st.write(f"**{nome}** — {dts}")

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_geral, tab_top, tab_detalhe, tab_comp = st.tabs([
    "🏦 Visão Geral",
    "🏆 Top / Bottom",
    "📋 Detalhes da Carteira",
    "🔍 Comparativo Semanal",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — VISÃO GERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_geral:
    rows = []
    for nome, c in mais_recentes.items():
        p = c.get("perf_total", {})
        rows.append({
            "Fundo": nome,
            "PL":    c.get("patrimonio", 0),
            "Data":  c.get("data_base", ""),
            "Mês":   p.get("mes"),
            "Ano":   p.get("ano"),
            "12M":   p.get("m12"),
            "24M":   p.get("m24"),
        })
    df = pd.DataFrame(rows).sort_values("PL", ascending=False)
    aum_total = df["PL"].sum()

    c1, c2 = st.columns(2)
    c1.metric("AUM Total", f"R$ {aum_total / 1e6:.1f}M")
    c2.metric("Data(s) base", " / ".join(sorted(df["Data"].unique())))
    st.markdown("---")

    col_bar, col_tbl = st.columns([3, 2])
    with col_bar:
        df_bar = df.copy()
        df_bar["PL (R$MM)"] = df_bar["PL"] / 1e6
        fig = px.bar(
            df_bar.sort_values("PL (R$MM)"),
            x="PL (R$MM)", y="Fundo", orientation="h",
            title="Patrimônio por Fundo (R$ MM)",
            color="PL (R$MM)", color_continuous_scale=[LAVA, NAVY],
            text_auto=".0f",
        )
        fig.update_traces(texttemplate="R$ %{x:.0f}MM", textposition="outside")
        fig.update_layout(
            showlegend=False, coloraxis_showscale=False,
            height=max(360, len(df) * 50),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis_title="", xaxis_title="R$ Milhões",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_tbl:
        df_show = df[["Fundo","PL","Data","Mês","Ano","12M","24M"]].copy()
        df_show["PL"]  = df_show["PL"].apply(lambda x: f"R$ {x/1e6:.1f}M")
        for col in ["Mês","Ano","12M","24M"]:
            df_show[col] = df_show[col].apply(fmt_pct)
        st.dataframe(df_show, use_container_width=True, hide_index=True, height=420)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TOP / BOTTOM
# ══════════════════════════════════════════════════════════════════════════════
with tab_top:
    periodo = st.radio("Período", ["Mês","Ano","12M","24M"], horizontal=True, key="p_top")
    pk = {"Mês":"mes","Ano":"ano","12M":"m12","24M":"m24"}[periodo]

    if len(mais_recentes) > 1:
        st.subheader(f"Ranking de Fundos — {periodo}")
        rows_f = [
            {"Fundo": nome, "Ret%": (c.get("perf_total",{}).get(pk) or 0)*100,
             "Retorno": c.get("perf_total",{}).get(pk)}
            for nome, c in mais_recentes.items()
            if c.get("perf_total",{}).get(pk) is not None
        ]
        df_f = pd.DataFrame(rows_f).sort_values("Retorno", ascending=True)
        df_f["cor"] = df_f["Ret%"].apply(lambda x: "#2e7d32" if x >= 0 else "#c62828")
        altura = max(300, len(df_f) * 42)
        fig_rank = go.Figure(go.Bar(
            x=df_f["Ret%"], y=df_f["Fundo"], orientation="h",
            marker_color=df_f["cor"],
            text=[f"{v:.2f}%" for v in df_f["Ret%"]], textposition="outside",
        ))
        fig_rank.update_layout(
            showlegend=False, height=altura,
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title="", yaxis_title="",
            margin=dict(l=0, r=60, t=10, b=10),
        )
        st.plotly_chart(fig_rank, use_container_width=True)
        st.markdown("---")

    st.subheader(f"Top / Bottom Posições por Fundo — {periodo}")
    for nome, c in mais_recentes.items():
        posicoes = c.get("fundos", [])
        if not posicoes:
            continue
        df_pos = pd.DataFrame(posicoes).dropna(subset=[pk]).sort_values(pk, ascending=False)
        if df_pos.empty:
            continue
        with st.expander(f"**{nome}** — {c.get('data_base','')}  |  PL: R$ {c.get('patrimonio',0)/1e6:.1f}M", expanded=True):
            col_t2, col_b2 = st.columns(2)
            def _bar_chart(df_sub, ascending):
                df_sub = df_sub.copy()
                df_sub["ret%"] = df_sub[pk] * 100
                df_sub = df_sub.sort_values("ret%", ascending=ascending)
                cores = ["#2e7d32" if v >= 0 else "#c62828" for v in df_sub["ret%"]]
                # Range com padding para labels não serem cortados
                vmin = min(df_sub["ret%"].min(), 0)
                vmax = max(df_sub["ret%"].max(), 0)
                pad = max((vmax - vmin) * 0.25, 0.5)
                fig = go.Figure(go.Bar(
                    x=df_sub["ret%"], y=df_sub["nome"], orientation="h",
                    marker_color=cores,
                    text=[f"{v:.2f}%" for v in df_sub["ret%"]], textposition="outside",
                    cliponaxis=False,
                ))
                fig.update_layout(showlegend=False, height=260,
                                  plot_bgcolor="white", paper_bgcolor="white",
                                  xaxis=dict(range=[vmin - pad, vmax + pad]),
                                  xaxis_title="", yaxis_title="",
                                  margin=dict(l=0, r=10, t=5, b=5))
                return fig

            with col_t2:
                st.markdown("🏆 **Top 5**")
                st.plotly_chart(_bar_chart(df_pos.head(5), ascending=True), use_container_width=True)
            with col_b2:
                st.markdown("⚠️ **Bottom 5**")
                st.plotly_chart(_bar_chart(df_pos.tail(5), ascending=False), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DETALHES
# ══════════════════════════════════════════════════════════════════════════════
with tab_detalhe:
    opcoes_det = [(c["_nome"], c.get("data_base",""), c) for datas in grupos.values() for c in datas]
    labels_det = [f"{n} — {d}" for n, d, _ in opcoes_det]
    sel = st.selectbox("Selecionar fundo / data", range(len(labels_det)), format_func=lambda i: labels_det[i])
    cart  = opcoes_det[sel][2]
    perf  = cart.get("perf_total", {})
    bench = cart.get("pct_bench",  {})

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Data Base",   cart.get("data_base","—"))
    c2.metric("Patrimônio",  f"R$ {cart.get('patrimonio',0)/1e6:.2f}M")
    c3.metric("Retorno Mês", fmt_pct(perf.get("mes")), delta=f"bench {fmt_pct(bench.get('mes'))}")
    c4.metric("Retorno Ano", fmt_pct(perf.get("ano")), delta=f"bench {fmt_pct(bench.get('ano'))}")
    c5.metric("12M",         fmt_pct(perf.get("m12")))
    st.markdown("---")

    posicoes = cart.get("fundos", [])
    if not posicoes:
        st.warning("Nenhuma posição encontrada.")
    else:
        df_p = pd.DataFrame(posicoes)
        col_pie, col_tbl = st.columns([2, 3])
        with col_pie:
            fig_pie = px.pie(df_p.head(15), values="pl", names="nome",
                             title="Distribuição %PL (Top 15)",
                             color_discrete_sequence=BWAG_COLORS, hole=0.35)
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, height=420)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_tbl:
            df_show = df_p.copy()
            for col in ["mes","ano","m12","m24"]:
                if col in df_show.columns:
                    df_show[col] = df_show[col].apply(fmt_pct)
            df_show["financeiro"] = df_show["financeiro"].apply(lambda x: f"R$ {x:,.0f}")
            df_show["pl"]         = df_show["pl"].apply(lambda x: f"{x:.2f}%")
            df_show = df_show.rename(columns={"nome":"Ativo","pl":"%PL","financeiro":"Financeiro",
                                               "mes":"Mês","ano":"Ano","m12":"12M","m24":"24M"})
            st.dataframe(df_show, use_container_width=True, hide_index=True, height=400)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — COMPARATIVO SEMANAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_comp:
    if not fundos_comp:
        st.info("Carregue dois PDFs do mesmo fundo (datas diferentes) para ver o comparativo automático.")
    else:
        fundo_sel = st.selectbox("Selecionar fundo", fundos_comp, key="sel_comp") if len(fundos_comp) > 1 else fundos_comp[0]
        datas_disp = grupos[fundo_sel]
        labels_datas = [c.get("data_base", f"#{i}") for i, c in enumerate(datas_disp)]

        col_da, col_db = st.columns(2)
        with col_da:
            idx_a = st.selectbox("Data A (base)", range(len(labels_datas)),
                                 format_func=lambda i: labels_datas[i], index=0, key="sel_da")
        with col_db:
            idx_b = st.selectbox("Data B (comparação)", range(len(labels_datas)),
                                 format_func=lambda i: labels_datas[i], index=len(labels_datas)-1, key="sel_db")
        da, db = datas_disp[idx_a], datas_disp[idx_b]
        pa, pb   = da.get("perf_total",{}), db.get("perf_total",{})
        pl_a, pl_b = da.get("patrimonio",0), db.get("patrimonio",0)
        delta_pl   = pl_b - pl_a

        st.subheader(fundo_sel)
        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("Data A", da.get("data_base","—"))
        c2.metric("Data B", db.get("data_base","—"))
        c3.metric("PL (data B)", f"R$ {pl_b/1e6:.2f}M",
                  delta=f"{delta_pl:+,.0f} ({delta_pl/pl_a*100:+.2f}%)" if pl_a else None)
        c4.metric("Retorno Mês", fmt_pct(pb.get("mes")),
                  delta=fmt_pct((pb.get("mes") or 0)-(pa.get("mes") or 0))+f" vs {da.get('data_base','A')}")
        c5.metric("Retorno Ano", fmt_pct(pb.get("ano")),
                  delta=fmt_pct((pb.get("ano") or 0)-(pa.get("ano") or 0))+f" vs {da.get('data_base','A')}")
        c6.metric("12M (data B)", fmt_pct(pb.get("m12")))
        st.markdown("---")

        ativos_a = {f["nome"]: f for f in da.get("fundos",[])}
        ativos_b = {f["nome"]: f for f in db.get("fundos",[])}
        todos    = sorted(set(ativos_a)|set(ativos_b))
        rows_pos = []
        for nome in todos:
            fa, fb = ativos_a.get(nome,{}), ativos_b.get(nome,{})
            ra, rb = fa.get("mes"), fb.get("mes")
            rows_pos.append({
                "Ativo":     nome,
                "%PL A":     fa.get("pl",0.0), "%PL B": fb.get("pl",0.0),
                "Δ %PL":     fb.get("pl",0.0)-fa.get("pl",0.0),
                "Ret.Mês A": ra, "Ret.Mês B": rb,
                "Δ Ret.Mês": (rb-ra) if (ra is not None and rb is not None) else None,
                "Fin. B":    fb.get("financeiro", fa.get("financeiro",0)),
            })
        df_pos = pd.DataFrame(rows_pos).sort_values("%PL B", ascending=False)

        col_bar2, col_ret2 = st.columns(2)
        with col_bar2:
            df_b2 = df_pos[df_pos["Δ %PL"]!=0].copy()
            df_b2["cor"] = df_b2["Δ %PL"].apply(lambda x: "#2e7d32" if x>=0 else "#c62828")
            fig_pl = go.Figure(go.Bar(x=df_b2["Ativo"], y=df_b2["Δ %PL"], marker_color=df_b2["cor"],
                                      text=[f"{v:+.2f}%" for v in df_b2["Δ %PL"]], textposition="outside"))
            fig_pl.update_layout(title=f"Variação de %PL ({da['data_base']} → {db['data_base']})",
                                 plot_bgcolor="white", paper_bgcolor="white", height=380,
                                 yaxis_title="Δ %PL (%)", showlegend=False, xaxis_tickangle=-30)
            st.plotly_chart(fig_pl, use_container_width=True)
        with col_ret2:
            df_r2 = df_pos.dropna(subset=["Δ Ret.Mês"]).copy()
            df_r2["cor"] = df_r2["Δ Ret.Mês"].apply(lambda x: "#2e7d32" if x>=0 else "#c62828")
            fig_ret = go.Figure(go.Bar(x=df_r2["Ativo"], y=df_r2["Δ Ret.Mês"]*100, marker_color=df_r2["cor"],
                                       text=[f"{v*100:+.2f}%" for v in df_r2["Δ Ret.Mês"]], textposition="outside"))
            fig_ret.update_layout(title="Variação de Retorno Mês por Ativo",
                                  plot_bgcolor="white", paper_bgcolor="white", height=380,
                                  yaxis_title="Δ Ret.Mês (%)", showlegend=False, xaxis_tickangle=-30)
            st.plotly_chart(fig_ret, use_container_width=True)

        st.subheader("Tabela Detalhada")
        data_a_label = da.get("data_base", "A")
        data_b_label = db.get("data_base", "B")
        df_tbl = df_pos.copy()
        df_tbl["%PL A"]     = df_tbl["%PL A"].apply(lambda x: f"{x:.2f}%")
        df_tbl["%PL B"]     = df_tbl["%PL B"].apply(lambda x: f"{x:.2f}%")
        df_tbl["Δ %PL"]     = df_tbl["Δ %PL"].apply(lambda x: f"{x:+.2f}%")
        df_tbl["Ret.Mês A"] = df_tbl["Ret.Mês A"].apply(fmt_pct)
        df_tbl["Ret.Mês B"] = df_tbl["Ret.Mês B"].apply(fmt_pct)
        df_tbl["Δ Ret.Mês"] = df_tbl["Δ Ret.Mês"].apply(lambda x: f"{x*100:+.2f}%" if x is not None else "—")
        df_tbl["Fin. B"]    = df_tbl["Fin. B"].apply(lambda x: f"R$ {x:,.0f}")
        df_tbl = df_tbl.rename(columns={
            "%PL A":     f"%PL {data_a_label}",
            "%PL B":     f"%PL {data_b_label}",
            "Ret.Mês A": f"Ret.Mês {data_a_label}",
            "Ret.Mês B": f"Ret.Mês {data_b_label}",
            "Fin. B":    f"Fin. {data_b_label}",
        })
        st.dataframe(df_tbl, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Destaques da Semana")
        df_dest = df_pos.dropna(subset=["Ret.Mês B"]).sort_values("Ret.Mês B", ascending=False)
        col_hi, col_lo = st.columns(2)
        with col_hi:
            st.markdown("**Maiores avanços**")
            for _, row in df_dest.head(3).iterrows():
                st.success(f"**{row['Ativo']}** — {fmt_pct(row['Ret.Mês B'])}")
        with col_lo:
            st.markdown("**Maiores quedas**")
            for _, row in df_dest.tail(3).iloc[::-1].iterrows():
                st.error(f"**{row['Ativo']}** — {fmt_pct(row['Ret.Mês B'])}")
