"""
Dashboard de Posição dos Clientes — BWAG
- Admin (senha): faz upload de PDFs SmartBrain e publica os dados
- Viewer (todos): vê o dashboard com os dados salvos no GitHub
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
from src.readers.relatorio_consolidado_reader import ler_relatorio_consolidado

# ── Paleta BWAG ──────────────────────────────────────────────────────────────
NAVY     = "#1C0845"
ROYAL    = "#2A1A8C"
ELECTRIC = "#4A3BE0"
PERIW    = "#7B6FF0"
LAVA     = "#BFB8F5"
CINZA_BG = "#F4F4F6"
CINZA_TX = "#6B6B7B"
PRETO    = "#0A0420"
BWAG_COLORS = [NAVY, ROYAL, ELECTRIC, PERIW, LAVA, "#9F96F3", "#D4D0F8",
               "#6B5CE7", "#A89FF5", "#C4BEFC"]

GITHUB_DATA_PATH = "data/posicao_clientes/latest_data.json"

VERDE   = "#2e7d32"
VERMELHO = "#c62828"


# ── Logo ─────────────────────────────────────────────────────────────────────
def _logo_b64() -> str:
    p = Path(__file__).parent / "assets" / "logo_bwag_dark.png"
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    return ""

_LOGO = _logo_b64()

st.set_page_config(
    page_title="Posição dos Clientes — BWAG",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif !important; }}

.main .block-container {{
    padding-top: 0 !important;
    padding-bottom: 2rem;
    max-width: 1400px;
}}

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
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {{
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(191,184,245,0.4) !important;
    color: white !important;
    border-radius: 6px;
}}

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

[data-testid="stExpander"] {{
    border: 1px solid {LAVA} !important;
    border-radius: 10px !important;
    background: white !important;
}}
[data-testid="stExpander"] summary span {{
    color: {NAVY} !important;
    font-weight: 600;
}}

h1, h2 {{ color: {NAVY} !important; }}
h3 {{ color: {ROYAL} !important; }}

[data-testid="stSelectbox"] label,
[data-testid="stRadio"] label {{
    color: {NAVY} !important;
    font-weight: 600 !important;
}}

hr {{ border-color: {LAVA}44 !important; }}

.metric-card {{
    background: white;
    border: 1px solid {LAVA}88;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    box-shadow: 0 1px 4px rgba(28,8,69,0.08);
}}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_pct(v, dec=2):
    try:
        if v is None or pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{v:.{dec}f}%".replace(".", ",")


def fmt_money(v, abbrev=False):
    try:
        if v is None or pd.isna(v):
            return "—"
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if abbrev:
        av = abs(v)
        if av >= 1_000_000:
            return f"R$ {v/1_000_000:.2f}M".replace(".", ",")
        if av >= 1_000:
            return f"R$ {v/1_000:.0f}K"
    neg = v < 0
    s = f"{abs(v):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if neg else ''}R$ {s}"


# Correções manuais para casos ALLCAPS com múltiplas palavras grudadas sem separador,
# que o algoritmo automático não consegue desfazer.
_ESTRATEGIA_OVERRIDES = {
    "carteiraitauinternacional": "Carteira Itaú Internacional",
}


def fmt_estrategia(s):
    """Formata nome de estratégia para exibição: insere espaços e aplica Title Case.

    Ex: 'RFPósFixada'                 -> 'RF Pós Fixada'
        'FundosdeInvestimentoemParticipações' -> 'Fundos de Investimento em Participações'
        'PREVIDÊNCIA'                  -> 'Previdência'
        'AtivosIsentosIndexadosaInflação' -> 'Ativos Isentos Indexados a Inflação'
    """
    if not s or not isinstance(s, str):
        return s
    s = s.replace("�", "")
    if not s:
        return ""

    # Override manual (case-insensitive)
    ov = _ESTRATEGIA_OVERRIDES.get(s.lower())
    if ov:
        return ov

    # 1) Preposições grudadas em minúscula entre lower e UPPER → insere espaços ao redor.
    # Só "de" e "em": outras (da/do/das/dos) também aparecem como sufixo de palavras reais
    # (Renda, Fundos), causando falso positivo. Caso "a" é tratado depois.
    for prep in ("de", "em"):
        i = 0
        out = []
        while i < len(s):
            if (i > 0 and i + len(prep) < len(s)
                and s[i-1].islower()
                and s[i:i+len(prep)] == prep
                and s[i+len(prep)].isupper()):
                out.append(" ")
                out.append(prep)
                out.append(" ")
                i += len(prep)
            else:
                out.append(s[i])
                i += 1
        s = "".join(out)

    # 2) Se >= 70% do alfa é UPPER, aplica Title Case (PREVIDÊNCIA → Previdência)
    alpha = [c for c in s if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) >= 0.7:
        s = s.title()

    # 3) Insere espaço em fronteiras camelCase
    out = [s[0]] if s else []
    for i in range(1, len(s)):
        c, p = s[i], s[i-1]
        if c.isupper() and p.islower():
            out.append(" ")
        elif (c.isupper() and p.isupper()
              and i+1 < len(s) and s[i+1].islower()):
            out.append(" ")
        out.append(c)
    s = "".join(out)

    # 4) Caso específico: "Indexadosa Inflação" → "Indexados a Inflação"
    s = re.sub(r"\b(\w+s)a (?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", r"\1 a ", s)

    # 5) Normaliza múltiplos espaços
    return " ".join(s.split())


# Prefixos de tipos de ativos para separar do emissor
# (mais longos primeiro pra evitar match prematuro: 'LCICAIXA' antes de 'LCI')
_ATIVO_PREFIX_SPLITS = [
    ("LCICAIXA",     "LCI CAIXA"),
    ("LCIITAÚ",      "LCI ITAÚ"),
    ("LCIITAU",      "LCI ITAU"),
    ("LCIBRADESCO",  "LCI BRADESCO"),
    ("LCISANTANDER", "LCI SANTANDER"),
    ("LIGITAÚ",      "LIG ITAÚ"),
    ("LIGITAU",      "LIG ITAU"),
    ("LIGBRADESCO",  "LIG BRADESCO"),
    ("LIGCAIXA",     "LIG CAIXA"),
    ("LIGBANCO",     "LIG BANCO"),
    ("LIGBTG",       "LIG BTG"),
    ("CDBITAÚ",      "CDB ITAÚ"),
    ("CDBITAU",      "CDB ITAU"),
    ("CDBBTG",       "CDB BTG"),
    ("CDBBRADESCO",  "CDB BRADESCO"),
    ("CDBSANTANDER", "CDB SANTANDER"),
    ("CRIBARI",      "CRI BARI"),
    ("CRIBR",        "CRI BR"),
    ("CRIECO",       "CRI ECO"),
    ("CRIRB",        "CRI RB"),
    ("CRITRUE",      "CRI TRUE"),
    ("CRIVIRGO",     "CRI VIRGO"),
    ("CRIOPEA",      "CRI OPEA"),
    ("CRAECO",       "CRA ECO"),
    ("CRATRUE",      "CRA TRUE"),
    ("CRAVERT",      "CRA VERT"),
    ("BTGPACTUAL",   "BTG PACTUAL"),
]


def fmt_ativo(s):
    """Formata nome de ativo (LCI/LCA/CRI/CRA/CDB/Deb./LIG etc.) para exibição.

    Ex: 'LCICAIXA94%CDI-19/02/2026A22/07/2027'
        -> 'LCI CAIXA 94% CDI - 19/02/2026 A 22/07/2027'
        'Deb.TAEB15IPCA+5.85%GrossUp 051121-TEREOS06/2027'
        -> 'Deb. TAEB 15 IPCA + 5.85% GrossUp 051121 - TEREOS 06/2027'
    """
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    if not s:
        return ""

    # 1) Prefixos conhecidos: separa "LCI"/"CRA"/"CDB"/etc. do emissor
    for old, new in _ATIVO_PREFIX_SPLITS:
        s = s.replace(old, new)

    # 2) "Deb.X" -> "Deb. X" (mas evita duplicar espaço se já tem)
    s = re.sub(r"Deb\.(?!\s|$)", "Deb. ", s)

    # 3) Letra ↔ dígito: insere espaço em transições
    #    [^\W\d_] = letras Unicode (ASCII + acentuadas como Í/Á/Ê)
    s = re.sub(r"([^\W\d_])(\d)", r"\1 \2", s)  # BARI1 -> BARI 1
    s = re.sub(r"(\d)([^\W\d_])", r"\1 \2", s)  # 8CDI -> 8 CDI, 2026A -> 2026 A

    # 4) Operadores +/- entre alfanum: insere espaços
    s = re.sub(r"([^\W\d_])([+\-])(\d)", r"\1 \2 \3", s)   # IPCA+5 -> IPCA + 5
    s = re.sub(r"(\d)([+\-])([^\W\d_])", r"\1 \2 \3", s)   # 051121-TEREOS -> 051121 - TEREOS

    # 4b) "letra/dígito + dash" colado em final de palavra (ex: "CDI-" antes de espaço)
    s = re.sub(r"(\S)-(?=\s)", r"\1 -", s)                 # CDI- 25 -> CDI - 25
    s = re.sub(r"(?<=\s)-(\S)", r"- \1", s)

    # 5) "%" + letra: insere espaço
    s = re.sub(r"(%)([^\W\d_])", r"\1 \2", s)

    # 6) Normaliza espaços
    return " ".join(s.split())


def _parse_data(data_str: str):
    try:
        return datetime.strptime(data_str, "%d/%m/%Y")
    except Exception:
        return datetime.min


def _cor_valor(v):
    """Cor verde/vermelho baseada no sinal de um valor numérico."""
    try:
        return VERDE if float(v) >= 0 else VERMELHO
    except (TypeError, ValueError):
        return CINZA_TX


# ── GitHub storage ────────────────────────────────────────────────────────────
def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def merge_clientes(existentes: list, novos: list) -> tuple:
    """Mescla novos uploads com o histórico. Mesmo cliente+data → substitui."""
    merged = {
        (d.get("cliente", ""), d.get("data_extrato", "")): d
        for d in existentes
    }
    adicionados, atualizados = 0, 0
    for d in novos:
        key = (d.get("cliente", ""), d.get("data_extrato", ""))
        if key in merged:
            atualizados += 1
        else:
            adicionados += 1
        merged[key] = d
    return list(merged.values()), adicionados, atualizados


def github_save(dados: list, token: str, repo: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/contents/{GITHUB_DATA_PATH}"
    r = requests.get(url, headers=_gh_headers(token), timeout=10)
    sha = r.json().get("sha") if r.status_code == 200 else None
    content = json.dumps(dados, ensure_ascii=False, indent=2, default=str)
    payload = {
        "message": f"update: posicao clientes {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=_gh_headers(token), json=payload, timeout=15)
    return r.status_code in (200, 201)


@st.cache_data(ttl=300, show_spinner=False)
def github_load(token: str, repo: str):
    url = f"https://api.github.com/repos/{repo}/contents/{GITHUB_DATA_PATH}"
    r = requests.get(url, headers=_gh_headers(token), timeout=10)
    if r.status_code != 200:
        return None, None
    meta = r.json()
    content = base64.b64decode(meta["content"]).decode()
    dados = json.loads(content)
    for d in dados:
        d["_dt"] = _parse_data(d.get("data_extrato", ""))
    return dados, meta.get("sha")


# ── Loader de PDF ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_pdf(raw: bytes, fname: str):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        data = ler_relatorio_consolidado(path, nome_arquivo=fname)
        data["_filename"] = fname
        data["_dt"] = _parse_data(data.get("data_extrato", ""))
        return data
    except Exception as e:
        st.sidebar.error(f"Erro ao ler {fname}: {e}")
        return None
    finally:
        os.unlink(path)


# ── Secrets ───────────────────────────────────────────────────────────────────
ADMIN_PWD    = st.secrets.get("ADMIN_PASSWORD", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "")


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _sb_logo = (
        f'<img src="data:image/png;base64,{_LOGO}" '
        f'style="height:36px;filter:brightness(0) invert(1);margin-bottom:4px;">'
        if _LOGO else
        '<span style="color:white;font-size:1.3rem;font-weight:800;">BWAG.</span>'
    )
    st.markdown(f'<div style="padding:0.8rem 0 0.4rem 0;">{_sb_logo}</div>',
                unsafe_allow_html=True)
    st.markdown("---")

    senha = st.text_input("Senha admin", type="password", key="senha",
                          placeholder="••••••••")
    is_admin = senha == ADMIN_PWD and ADMIN_PWD != ""

    if is_admin:
        st.success("✓ Modo admin ativo")
        st.markdown("---")
        st.markdown(
            f'<p style="color:white;font-weight:600;margin-bottom:4px;">Carregar PDFs</p>',
            unsafe_allow_html=True,
        )
        st.caption("PDFs SmartBrain — um ou vários clientes/datas")
        f_pdfs = st.file_uploader(
            "PDFs", type=["pdf"], accept_multiple_files=True,
            key="pdfs", label_visibility="collapsed",
        )
    else:
        f_pdfs = []
        if senha and senha != ADMIN_PWD:
            st.error("Senha incorreta")

    st.markdown("---")
    st.markdown(
        f'<p style="color:{LAVA};font-size:0.72rem;text-align:center;opacity:0.7;">'
        f'Automações BWAG — v1.0</p>',
        unsafe_allow_html=True,
    )


# ── Carregar dados ────────────────────────────────────────────────────────────
if is_admin and f_pdfs:
    dados_raw = [
        d for f in f_pdfs
        if (d := load_pdf(f.getvalue(), f.name)) is not None
    ]
    fonte = "upload"
    with st.sidebar.expander("🔍 Debug", expanded=False):
        for d in dados_raw:
            st.code(
                f"Arquivo : {d.get('_filename','')}\n"
                f"Cliente : {d.get('cliente','?')}\n"
                f"Data    : {d.get('data_extrato','?')}\n"
                f"Saldo Liq: {fmt_money(d.get('saldo_liquido_total'), abbrev=True)}\n"
                f"Ativos  : {len(d.get('ativos',[]))}"
            )
else:
    dados_raw, _ = github_load(GITHUB_TOKEN, GITHUB_REPO)
    dados_raw = dados_raw or []
    fonte = "github"


# ── Header ────────────────────────────────────────────────────────────────────
_logo_html = (
    f'<img src="data:image/png;base64,{_LOGO}" '
    f'style="height:42px;filter:brightness(0) invert(1);vertical-align:middle;">'
    if _LOGO else
    '<span style="font-size:1.4rem;font-weight:800;color:white;letter-spacing:2px;">BWAG.</span>'
)
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
        <div style="color:white;font-size:1.3rem;font-weight:700;letter-spacing:0.3px;line-height:1.2;">
            Posição dos Clientes
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if not dados_raw:
    if is_admin:
        st.info("👈 Carregue os PDFs SmartBrain na barra lateral para começar.")
    else:
        st.info("Aguardando publicação dos dados pelo administrador.")
    st.stop()


# ── Publicação (admin) ────────────────────────────────────────────────────────
if is_admin and fonte == "upload":
    col_pub, col_sub, _ = st.columns([2, 2, 3])
    with col_pub:
        if st.button("💾 Salvar e publicar", type="primary"):
            with st.spinner("Salvando no GitHub..."):
                existentes, _ = github_load(GITHUB_TOKEN, GITHUB_REPO)
                merged, adicionados, atualizados = merge_clientes(
                    existentes or [], dados_raw
                )
                ok = github_save(merged, GITHUB_TOKEN, GITHUB_REPO)
            if ok:
                partes = []
                if adicionados: partes.append(f"{adicionados} novo(s)")
                if atualizados: partes.append(f"{atualizados} atualizado(s)")
                det = f" ({', '.join(partes)})" if partes else ""
                st.success(f"Publicado{det}! Total: {len(merged)} relatório(s).")
                github_load.clear()
            else:
                st.error("Erro ao salvar. Verifique o token do GitHub.")
    with col_sub:
        if st.button("🗑️ Substituir tudo",
                     help="Apaga o histórico e salva APENAS os PDFs carregados agora"):
            with st.spinner("Substituindo..."):
                ok = github_save(dados_raw, GITHUB_TOKEN, GITHUB_REPO)
            if ok:
                st.success(f"Histórico substituído. {len(dados_raw)} relatório(s) salvos.")
                github_load.clear()
            else:
                st.error("Erro ao salvar.")


# ── Estrutura de dados ────────────────────────────────────────────────────────
# Agrupa por cliente → lista de dicts ordenada por data
def _agrupar(dados: list) -> dict:
    grupos = {}
    for d in dados:
        cliente = d.get("cliente") or "Sem cliente"
        grupos.setdefault(cliente, []).append(d)
    for c in grupos:
        grupos[c].sort(key=lambda d: d.get("_dt", datetime.min))
    return grupos

grupos = _agrupar(dados_raw)
clientes = sorted(grupos.keys())
mais_recentes = {c: datas[-1] for c, datas in grupos.items()}

# Datas disponíveis por cliente
datas_por_cliente = {
    c: [d.get("data_extrato", "") for d in datas]
    for c, datas in grupos.items()
}

# Info de atualização
todas_datas = sorted({d.get("data_extrato","") for d in dados_raw if d.get("data_extrato")}, key=_parse_data)
st.caption(f"Dados de: **{' · '.join(todas_datas)}**  |  {len(dados_raw)} relatório(s) · {len(clientes)} cliente(s)")
st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_geral, tab_pos, tab_perf, tab_liq, tab_hist, tab_comp, tab_mov = st.tabs([
    "🏦 Visão Geral",
    "📋 Posição Detalhada",
    "📈 Performance",
    "💧 Liquidez",
    "📅 Histórico",
    "🔄 Comparativo",
    "💸 Movimentações",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — VISÃO GERAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_geral:
    # Selector de data de referência
    col_dt, _ = st.columns([2, 4])
    with col_dt:
        data_ref = st.selectbox(
            "Data de referência",
            options=sorted(todas_datas, key=_parse_data, reverse=True),
            key="data_ref_geral",
        )

    # Dados filtrados para a data selecionada
    dados_data = [d for d in dados_raw if d.get("data_extrato") == data_ref]
    if not dados_data:
        st.warning("Nenhum dado para a data selecionada.")
    else:
        # Métricas agregadas
        total_liq  = sum(d.get("saldo_liquido_total") or 0 for d in dados_data)
        total_bruto = sum(d.get("saldo_bruto_total") or 0 for d in dados_data)
        total_ganho_mes = sum(d.get("ganho_mes_total") or 0 for d in dados_data)
        total_ganho_ano = sum(d.get("ganho_ano_total") or 0 for d in dados_data)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Saldo Líquido Total", fmt_money(total_liq, abbrev=True))
        m2.metric("Saldo Bruto Total",   fmt_money(total_bruto, abbrev=True))
        m3.metric("Ganho no Mês",        fmt_money(total_ganho_mes, abbrev=True))
        m4.metric("Ganho no Ano",        fmt_money(total_ganho_ano, abbrev=True))
        st.markdown("---")

        col_bar, col_pie = st.columns(2)

        # Barras: AUM por cliente
        with col_bar:
            df_cl = pd.DataFrame([
                {
                    "Cliente": d.get("cliente","?"),
                    "Saldo Líquido": d.get("saldo_liquido_total") or 0,
                    "SL_MM": (d.get("saldo_liquido_total") or 0) / 1e6,
                    "N_Ativos": len(d.get("ativos") or []),
                    "Ganho": d.get("ganho_mes_total") or 0,
                }
                for d in dados_data
            ]).sort_values("Saldo Líquido", ascending=True)
            total_aum = df_cl["Saldo Líquido"].sum()
            df_cl["Pct"] = df_cl["Saldo Líquido"] / total_aum * 100 if total_aum else 0
            media_aum = df_cl["SL_MM"].mean() if len(df_cl) else 0
            fig_bar = go.Figure(go.Bar(
                x=df_cl["SL_MM"], y=df_cl["Cliente"], orientation="h",
                marker=dict(
                    color=ELECTRIC,
                    line=dict(color=NAVY, width=1),
                ),
                text=[fmt_money(v * 1e6, abbrev=True) for v in df_cl["SL_MM"]],
                textposition="outside",
                customdata=df_cl[["Saldo Líquido","Pct","N_Ativos","Ganho"]].values,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Saldo Líquido: R$ %{customdata[0]:,.2f}<br>"
                    "Participação: %{customdata[1]:.1f}%<br>"
                    "Ativos: %{customdata[2]}<br>"
                    "Ganho do Mês: R$ %{customdata[3]:,.2f}"
                    "<extra></extra>"
                ),
            ))
            # Linha de referência: média
            if len(df_cl) > 1:
                fig_bar.add_vline(
                    x=media_aum, line_dash="dot", line_color=LAVA,
                    annotation_text=f"Média: {fmt_money(media_aum * 1e6, abbrev=True)}",
                    annotation_position="top",
                )
            fig_bar.update_layout(
                title="Saldo Líquido por Cliente (R$ MM)",
                showlegend=False, height=max(300, len(df_cl) * 55),
                plot_bgcolor="white", paper_bgcolor="white",
                xaxis_title="R$ Milhões", yaxis_title="",
                margin=dict(l=0, r=80, t=40, b=20),
                hovermode="y",  # destaca a barra inteira no hover
                hoverdistance=100,  # detecta hover a até 100px
                hoverlabel=dict(
                    bgcolor=NAVY, bordercolor=ELECTRIC, font_size=13,
                    font_color="white",
                ),
                xaxis=dict(
                    showspikes=True, spikecolor=ELECTRIC, spikedash="dot",
                    spikethickness=1, spikemode="across",
                ),
            )
            sel_bar = st.plotly_chart(
                fig_bar, use_container_width=True,
                key="vg_bar", on_select="rerun", selection_mode="points",
            )

        # Pizza: alocação por estratégia (todos os clientes somados)
        with col_pie:
            subtotais_all = []
            for d in dados_data:
                for st_rec in (d.get("subtotais") or []):
                    est = fmt_estrategia(st_rec.get("estrategia")) or "Outros"
                    sl = st_rec.get("saldo_liquido") or 0
                    subtotais_all.append({"Estratégia": est, "Saldo": sl})

            if subtotais_all:
                df_est = (
                    pd.DataFrame(subtotais_all)
                    .groupby("Estratégia", as_index=False)["Saldo"].sum()
                    .sort_values("Saldo", ascending=False)
                )
                # Agrupa estratégias pequenas em "Outros"
                total_s = df_est["Saldo"].sum()
                df_est["pct"] = df_est["Saldo"] / total_s * 100
                df_main = df_est[df_est["pct"] >= 1.5].copy()
                df_outros = df_est[df_est["pct"] < 1.5]
                if not df_outros.empty:
                    df_main = pd.concat([
                        df_main,
                        pd.DataFrame([{
                            "Estratégia": "Outros",
                            "Saldo": df_outros["Saldo"].sum(),
                            "pct": df_outros["pct"].sum(),
                        }])
                    ])
                # Selectbox p/ destacar uma estratégia (Plotly pie não suporta
                # click event no Streamlit, então usamos selectbox)
                estr_opcoes = ["— Nenhuma —"] + df_main["Estratégia"].tolist()
                estr_destaque = st.selectbox(
                    "Destacar estratégia",
                    estr_opcoes,
                    key="vg_pie_destaque",
                )
                sel_idx = None
                if estr_destaque != "— Nenhuma —":
                    try:
                        sel_idx = df_main["Estratégia"].tolist().index(estr_destaque)
                    except ValueError:
                        sel_idx = None

                pulls = [0.0] * len(df_main)
                if sel_idx is not None:
                    pulls[sel_idx] = 0.15  # fatia selecionada salta pra fora

                # Cores com alpha se houver destaque
                def _hex_to_rgba(hexc, alpha):
                    h = hexc.lstrip("#")
                    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                    return f"rgba({r},{g},{b},{alpha})"

                if sel_idx is not None:
                    colors = [
                        _hex_to_rgba(BWAG_COLORS[i % len(BWAG_COLORS)],
                                     1.0 if i == sel_idx else 0.2)
                        for i in range(len(df_main))
                    ]
                else:
                    colors = BWAG_COLORS[:len(df_main)]

                fig_pie = go.Figure(go.Pie(
                    values=df_main["Saldo"].tolist(),
                    labels=df_main["Estratégia"].tolist(),
                    hole=0.35,
                    pull=pulls,
                    marker=dict(colors=colors, line=dict(color="white", width=2)),
                    sort=False,
                    textposition="inside",
                    textinfo="percent",
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Saldo: R$ %{value:,.2f}<br>"
                        "Participação: %{percent}"
                        "<extra></extra>"
                    ),
                ))
                fig_pie.update_layout(
                    title="Alocação por Estratégia",
                    height=380, paper_bgcolor="white",
                    legend=dict(
                        orientation="v", x=1.0, y=0.5,
                        title=dict(text="Estratégia", font=dict(size=10, color=CINZA_TX)),
                    ),
                    margin=dict(l=0, r=0, t=40, b=0),
                    hoverlabel=dict(
                        bgcolor=NAVY, bordercolor=ELECTRIC, font_size=13,
                        font_color="white",
                    ),
                )

                st.plotly_chart(fig_pie, use_container_width=True, key="vg_pie")

                # Drill-down: se uma estratégia for destacada, mostra tabela
                estr_clicada = estr_destaque if estr_destaque != "— Nenhuma —" else None
                if estr_clicada:
                    if estr_clicada and estr_clicada != "Outros":
                        st.markdown(f"#### 🎯 Detalhes — **{estr_clicada}**")
                        rows_drill = []
                        for d in dados_data:
                            for a in (d.get("ativos") or []):
                                if fmt_estrategia(a.get("estrategia") or "") == estr_clicada:
                                    rows_drill.append({
                                        "Cliente": d.get("cliente","?"),
                                        "Ativo": fmt_ativo(a.get("nome") or ""),
                                        "Saldo Líquido": a.get("saldo_liquido") or 0,
                                        "% PL": a.get("part_pct"),
                                        "Rent. Mês": a.get("rentabilidade_mes"),
                                    })
                        if rows_drill:
                            df_drill = pd.DataFrame(rows_drill).sort_values(
                                "Saldo Líquido", ascending=False
                            )
                            df_drill["Saldo Líquido"] = df_drill["Saldo Líquido"].apply(fmt_money)
                            df_drill["% PL"]      = df_drill["% PL"].apply(fmt_pct)
                            df_drill["Rent. Mês"] = df_drill["Rent. Mês"].apply(fmt_pct)
                            st.dataframe(df_drill, use_container_width=True, hide_index=True)

        # Tabela resumo por cliente
        st.markdown("### Resumo por Cliente")
        rows_tbl = []
        for d in sorted(dados_data, key=lambda x: x.get("saldo_liquido_total") or 0, reverse=True):
            rows_tbl.append({
                "Cliente":      d.get("cliente","?"),
                "Mês Ref.":     d.get("mes_referencia",""),
                "Saldo Líquido": fmt_money(d.get("saldo_liquido_total")),
                "Saldo Bruto":  fmt_money(d.get("saldo_bruto_total")),
                "Provisão IR":  fmt_money(d.get("provisao_ir_total")),
                "Ganho Mês":    fmt_money(d.get("ganho_mes_total")),
                "Ganho Ano":    fmt_money(d.get("ganho_ano_total")),
                "Ganho Início": fmt_money(d.get("ganho_inicio_total")),
            })
        st.dataframe(pd.DataFrame(rows_tbl), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — POSIÇÃO DETALHADA
# ══════════════════════════════════════════════════════════════════════════════
with tab_pos:
    col_c, col_d, col_f = st.columns([2, 2, 3])
    with col_c:
        cliente_sel = st.selectbox("Cliente", clientes, key="pos_cliente")
    with col_d:
        datas_disp = sorted(datas_por_cliente.get(cliente_sel, []), key=_parse_data, reverse=True)
        data_sel = st.selectbox("Data", datas_disp, key="pos_data")
    with col_f:
        est_opcoes = ["Todas as estratégias"]

    dado = next(
        (d for d in grupos.get(cliente_sel, []) if d.get("data_extrato") == data_sel),
        None,
    )

    if dado is None:
        st.warning("Nenhum dado encontrado para a seleção.")
    else:
        ativos = dado.get("ativos") or []
        subtotais = dado.get("subtotais") or []

        # Filtro de estratégia (mantém valor raw para filtrar; formata para exibir)
        estrategias_disp = sorted({a.get("estrategia","") for a in ativos if a.get("estrategia")})
        est_opcoes = ["Todas"] + estrategias_disp
        with col_f:
            est_sel = st.selectbox(
                "Estratégia", est_opcoes, key="pos_estrategia",
                format_func=lambda v: v if v == "Todas" else fmt_estrategia(v),
            )

        if est_sel != "Todas":
            ativos = [a for a in ativos if a.get("estrategia") == est_sel]
            subtotais = [s for s in subtotais if s.get("estrategia") == est_sel]

        # Métricas da seleção
        sl_sel = sum(a.get("saldo_liquido") or 0 for a in ativos)
        sb_sel = sum(a.get("saldo_bruto") or 0 for a in ativos)
        g_sel  = sum(a.get("ganho") or 0 for a in ativos)
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Saldo Líquido",  fmt_money(sl_sel, abbrev=True))
        mc2.metric("Saldo Bruto",    fmt_money(sb_sel, abbrev=True))
        mc3.metric("Ganho no Mês",   fmt_money(g_sel, abbrev=True))
        mc4.metric("Ativos",         len(ativos))
        st.markdown("---")

        # Tabela de ativos
        if ativos:
            df_ativos = pd.DataFrame(ativos)
            cols_show = {
                "estrategia": "Estratégia",
                "nome": "Ativo",
                "saldo_anterior": "Saldo Ant.",
                "aplicacoes": "Aplicações",
                "resgates": "Resgates",
                "rendimentos": "Rendimentos",
                "imposto_pago": "Imposto Pago",
                "saldo_bruto": "Saldo Bruto",
                "provisao_ir": "Provisão IR",
                "saldo_liquido": "Saldo Líquido",
                "rentabilidade_mes": "Rent. Mês %",
                "pct_cdi_mes": "% CDI Mês",
                "part_pct": "Part. %",
                "ganho": "Ganho",
            }
            cols_exist = [c for c in cols_show if c in df_ativos.columns]
            df_show = df_ativos[cols_exist].rename(columns=cols_show)

            # Formata coluna Estratégia (display)
            if "Estratégia" in df_show.columns:
                df_show["Estratégia"] = df_show["Estratégia"].apply(fmt_estrategia)

            # Formata coluna Ativo (display)
            if "Ativo" in df_show.columns:
                df_show["Ativo"] = df_show["Ativo"].apply(fmt_ativo)

            # Formata colunas monetárias e percentuais
            money_cols = ["Saldo Ant.", "Aplicações", "Resgates", "Rendimentos",
                          "Imposto Pago", "Saldo Bruto", "Provisão IR", "Saldo Líquido",
                          "Ganho"]
            pct_cols   = ["Rent. Mês %", "% CDI Mês", "Part. %"]
            for col in money_cols:
                if col in df_show.columns:
                    df_show[col] = df_show[col].apply(fmt_money)
            for col in pct_cols:
                if col in df_show.columns:
                    df_show[col] = df_show[col].apply(fmt_pct)

            st.dataframe(df_show, use_container_width=True, hide_index=True,
                         height=420)

            # Download CSV
            csv_data = df_show.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Baixar CSV",
                csv_data,
                file_name=f"posicao_{cliente_sel}_{data_sel.replace('/','-')}.csv",
                mime="text/csv",
            )
        else:
            st.info("Nenhum ativo encontrado para os filtros selecionados.")

        # Subtotais por estratégia
        if subtotais:
            st.markdown("### Subtotais por Estratégia")
            df_sub = pd.DataFrame(subtotais)
            sub_cols = {
                "estrategia": "Estratégia",
                "saldo_bruto": "Saldo Bruto",
                "saldo_liquido": "Saldo Líquido",
                "rentabilidade_mes": "Rent. Mês %",
                "pct_cdi_mes": "% CDI Mês",
                "part_pct": "Part. %",
                "ganho": "Ganho",
            }
            sub_exist = [c for c in sub_cols if c in df_sub.columns]
            df_sub_show = df_sub[sub_exist].rename(columns=sub_cols)
            if "Estratégia" in df_sub_show.columns:
                df_sub_show["Estratégia"] = df_sub_show["Estratégia"].apply(fmt_estrategia)
            for col in ["Saldo Bruto", "Saldo Líquido", "Ganho"]:
                if col in df_sub_show.columns:
                    df_sub_show[col] = df_sub_show[col].apply(fmt_money)
            for col in ["Rent. Mês %", "% CDI Mês", "Part. %"]:
                if col in df_sub_show.columns:
                    df_sub_show[col] = df_sub_show[col].apply(fmt_pct)
            st.dataframe(df_sub_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_perf:
    col_pc, col_pd = st.columns([2, 2])
    with col_pc:
        cliente_perf = st.selectbox("Cliente", clientes, key="perf_cliente")
    with col_pd:
        datas_perf = sorted(datas_por_cliente.get(cliente_perf, []), key=_parse_data, reverse=True)
        data_perf  = st.selectbox("Data", datas_perf, key="perf_data")

    dado_perf = next(
        (d for d in grupos.get(cliente_perf, []) if d.get("data_extrato") == data_perf),
        None,
    )

    if dado_perf is None:
        st.warning("Nenhum dado encontrado.")
    else:
        # ── Rentabilidades por estratégia ────────────────────────────────────
        rent_est = dado_perf.get("rentabilidades_estrategia") or []
        if rent_est:
            st.markdown("### Rentabilidades por Estratégia")
            df_re = pd.DataFrame(rent_est)
            cols_re = {
                "estrategia": "Estratégia",
                "ret_mes": "Mês %", "bench_mes": "% CDI Mês",
                "ret_ano": "Ano %", "bench_ano": "% CDI Ano",
                "ret_12m": "12M %", "bench_12m": "% CDI 12M",
                "ret_24m": "24M %", "bench_24m": "% CDI 24M",
                "ret_36m": "36M %", "bench_36m": "% CDI 36M",
                "ret_inicio": "Início %", "bench_inicio": "% CDI Início",
            }
            exist_re = [c for c in cols_re if c in df_re.columns]
            df_re_show = df_re[exist_re].rename(columns=cols_re)
            if "Estratégia" in df_re_show.columns:
                df_re_show["Estratégia"] = df_re_show["Estratégia"].apply(fmt_estrategia)
            pct_re = [v for k, v in cols_re.items() if k in exist_re and k != "estrategia"]
            for col in pct_re:
                if col in df_re_show.columns:
                    df_re_show[col] = df_re_show[col].apply(fmt_pct)
            st.dataframe(df_re_show, use_container_width=True, hide_index=True)
            st.markdown("---")

        # ── Rentabilidades mensais (heatmap) ─────────────────────────────────
        rent_men = dado_perf.get("rentabilidades_mensais") or []
        if rent_men:
            st.markdown("### Rentabilidades Mensais")
            df_rm = pd.DataFrame(rent_men)
            if not df_rm.empty and "ano" in df_rm.columns and "mes" in df_rm.columns:
                # Pivot: anos × meses
                from src.readers.relatorio_consolidado_reader import _MESES_PT
                df_pivot = df_rm.pivot_table(
                    index="ano", columns="mes", values="ret_pct",
                    aggfunc="first",
                )
                # Reordena colunas por mês
                col_order = [m for m in _MESES_PT if m in df_pivot.columns]
                df_pivot = df_pivot[col_order].sort_index(ascending=False)

                # Tabela formatada
                df_fmt = df_pivot.map(
                    lambda v: fmt_pct(v) if pd.notna(v) else "—"
                )
                st.dataframe(df_fmt, use_container_width=True)

                # Gráfico de barras: ano selecionado
                anos_disp = sorted(df_pivot.index.tolist(), reverse=True)
                if anos_disp:
                    ano_sel = st.selectbox("Ano", anos_disp, key="perf_ano")
                    row_ano = df_pivot.loc[ano_sel].dropna()
                    if not row_ano.empty:
                        cores = [VERDE if v >= 0 else VERMELHO for v in row_ano.values]
                        fig_men = go.Figure(go.Bar(
                            x=list(row_ano.index),
                            y=list(row_ano.values),
                            marker_color=cores,
                            text=[fmt_pct(v) for v in row_ano.values],
                            textposition="outside",
                        ))
                        fig_men.update_layout(
                            title=f"Rentabilidade Mensal {ano_sel} — {cliente_perf}",
                            showlegend=False, height=320,
                            plot_bgcolor="white", paper_bgcolor="white",
                            yaxis_title="Ret. %", xaxis_title="",
                            margin=dict(l=20, r=20, t=40, b=20),
                        )
                        st.plotly_chart(fig_men, use_container_width=True)
        else:
            st.info("Rentabilidades mensais não disponíveis neste relatório.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — LIQUIDEZ
# ══════════════════════════════════════════════════════════════════════════════
with tab_liq:
    col_lc, col_ld = st.columns([2, 2])
    with col_lc:
        cliente_liq = st.selectbox("Cliente", clientes, key="liq_cliente")
    with col_ld:
        datas_liq = sorted(datas_por_cliente.get(cliente_liq, []), key=_parse_data, reverse=True)
        data_liq  = st.selectbox("Data", datas_liq, key="liq_data")

    dado_liq = next(
        (d for d in grupos.get(cliente_liq, []) if d.get("data_extrato") == data_liq),
        None,
    )

    if dado_liq is None:
        st.warning("Nenhum dado encontrado.")
    else:
        disponibilidade = dado_liq.get("disponibilidade") or []
        risco = dado_liq.get("risco_retorno") or {}

        if disponibilidade:
            st.markdown("### Disponibilidade Financeira")
            df_disp = pd.DataFrame(disponibilidade)

            # Barras de disponibilidade
            if "periodo" in df_disp.columns and "valor" in df_disp.columns:
                df_d = df_disp[df_disp["periodo"].str.lower().str.strip() != "total"].copy()
                df_d["Valor (R$MM)"] = df_d["valor"].fillna(0) / 1e6
                fig_disp = go.Figure(go.Bar(
                    x=df_d.get("periodo", []),
                    y=df_d["Valor (R$MM)"],
                    marker_color=ELECTRIC,
                    text=[fmt_money(v * 1e6, abbrev=True) for v in df_d["Valor (R$MM)"]],
                    textposition="outside",
                ))
                fig_disp.update_layout(
                    title="Disponibilidade por Prazo",
                    showlegend=False, height=340,
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis_title="R$ Milhões", xaxis_title="Prazo",
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig_disp, use_container_width=True)

            # Tabela de disponibilidade
            disp_cols = {
                "periodo": "Prazo", "valor": "Valor",
                "pct": "%", "valor_acum": "Valor Acum.",
                "pct_acum": "% Acum.", "valor_liq": "Valor Líquido",
            }
            d_exist = [c for c in disp_cols if c in df_disp.columns]
            df_disp_show = df_disp[d_exist].rename(columns=disp_cols)
            for col in ["Valor", "Valor Acum.", "Valor Líquido"]:
                if col in df_disp_show.columns:
                    df_disp_show[col] = df_disp_show[col].apply(fmt_money)
            for col in ["%", "% Acum."]:
                if col in df_disp_show.columns:
                    df_disp_show[col] = df_disp_show[col].apply(
                        lambda v: f"{int(v)}%" if pd.notna(v) and v is not None else "—"
                    )
            st.dataframe(df_disp_show, use_container_width=True, hide_index=True)
        else:
            st.info("Disponibilidade financeira não disponível neste relatório.")

        # Risco e Retorno
        if risco:
            st.markdown("---")
            st.markdown("### Risco e Retorno")

            r1, r2, r3 = st.columns(3)
            r1.metric("Meses acima do índice",  risco.get("meses_acima", "—"))
            r2.metric("Meses abaixo do índice", risco.get("meses_abaixo", "—"))
            r3.metric("% acima",                fmt_pct(risco.get("pct_acima")))

            r4, r5 = st.columns(2)
            maior = risco.get("maior_ret")
            menor = risco.get("menor_ret")
            r4.metric(
                f"Maior retorno ({risco.get('maior_ret_data','')})",
                fmt_pct(maior),
            )
            r5.metric(
                f"Menor retorno ({risco.get('menor_ret_data','')})",
                fmt_pct(menor),
            )

            # Tabela de períodos
            periodos = risco.get("periodos") or []
            if periodos:
                df_perf = pd.DataFrame(periodos)
                perf_cols = {
                    "periodo": "Período",
                    "carteira": "Carteira %",
                    "cdi": "CDI %",
                    "pct_indice": "% do Índice",
                    "volat": "Volatilidade",
                }
                p_exist = [c for c in perf_cols if c in df_perf.columns]
                df_perf_show = df_perf[p_exist].rename(columns=perf_cols)
                for col in ["Carteira %", "CDI %", "% do Índice", "Volatilidade"]:
                    if col in df_perf_show.columns:
                        df_perf_show[col] = df_perf_show[col].apply(fmt_pct)
                st.dataframe(df_perf_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
with tab_hist:
    # Seleção de clientes para comparar
    clientes_hist = st.multiselect(
        "Clientes",
        clientes,
        default=clientes[:min(4, len(clientes))],
        key="hist_clientes",
    )

    if not clientes_hist:
        st.info("Selecione pelo menos um cliente.")
    else:
        # Série temporal de saldo líquido
        rows_ts = []
        for c in clientes_hist:
            for d in grupos.get(c, []):
                rows_ts.append({
                    "Cliente": c,
                    "Data": d.get("data_extrato", ""),
                    "dt": d.get("_dt", datetime.min),
                    "Saldo Líquido": d.get("saldo_liquido_total"),
                    "Ganho Mês": d.get("ganho_mes_total"),
                })
        df_ts = pd.DataFrame(rows_ts).sort_values("dt")

        if len(df_ts) == 0:
            st.info("Nenhuma série temporal disponível.")
        else:
            # Evolução do saldo líquido
            if df_ts["Saldo Líquido"].notna().any():
                df_sl = df_ts.dropna(subset=["Saldo Líquido"]).copy()
                fig_ts = px.line(
                    df_sl, x="Data", y="Saldo Líquido", color="Cliente",
                    markers=True,
                    title="Evolução do Saldo Líquido",
                    color_discrete_sequence=BWAG_COLORS,
                )
                fig_ts.update_layout(
                    height=400,
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis_title="R$", xaxis_title="",
                    hovermode="x unified",
                    hoverdistance=100,
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, x=0,
                        itemclick="toggle", itemdoubleclick="toggleothers",
                    ),
                    hoverlabel=dict(
                        bgcolor=NAVY, bordercolor=ELECTRIC, font_size=13,
                        font_color="white",
                    ),
                    xaxis=dict(
                        showspikes=True, spikecolor=ELECTRIC, spikedash="dot",
                        spikethickness=1, spikemode="across+marker",
                    ),
                    yaxis=dict(
                        showspikes=True, spikecolor=ELECTRIC, spikedash="dot",
                        spikethickness=1, spikemode="across",
                    ),
                )
                fig_ts.update_traces(
                    hovertemplate="<b>%{fullData.name}</b><br>R$ %{y:,.2f}<extra></extra>",
                    marker=dict(size=10, line=dict(width=2, color="white")),
                    line=dict(width=3),
                )
                # Linha de referência: média geral
                media_sl = df_sl["Saldo Líquido"].mean()
                fig_ts.add_hline(
                    y=media_sl, line_dash="dot", line_color=LAVA,
                    annotation_text=f"Média: {fmt_money(media_sl, abbrev=True)}",
                    annotation_position="top left",
                )
                st.plotly_chart(fig_ts, use_container_width=True, key="hist_ts")

            # Evolução do ganho mensal
            if df_ts["Ganho Mês"].notna().any():
                df_gm = df_ts.dropna(subset=["Ganho Mês"]).copy()
                fig_gm = px.bar(
                    df_gm, x="Data", y="Ganho Mês", color="Cliente",
                    barmode="group",
                    title="Ganho Mensal por Período",
                    color_discrete_sequence=BWAG_COLORS,
                )
                fig_gm.update_layout(
                    height=360,
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis_title="R$", xaxis_title="",
                    hovermode="x",
                    hoverdistance=100,
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, x=0,
                        itemclick="toggle", itemdoubleclick="toggleothers",
                    ),
                    hoverlabel=dict(
                        bgcolor=NAVY, bordercolor=ELECTRIC, font_size=13,
                        font_color="white",
                    ),
                    yaxis=dict(
                        showspikes=True, spikecolor=ELECTRIC, spikedash="dot",
                        spikethickness=1, spikemode="across",
                    ),
                )
                fig_gm.update_traces(
                    hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>R$ %{y:,.2f}<extra></extra>",
                    marker=dict(line=dict(color=NAVY, width=1)),
                )
                fig_gm.add_hline(y=0, line_color=CINZA_TX, line_width=1)
                st.plotly_chart(fig_gm, use_container_width=True, key="hist_gm")

            # Tabela resumo do histórico
            st.markdown("### Histórico Completo")
            df_hist_show = df_ts[["Cliente","Data","Saldo Líquido","Ganho Mês"]].copy()
            df_hist_show["Saldo Líquido"] = df_hist_show["Saldo Líquido"].apply(fmt_money)
            df_hist_show["Ganho Mês"]     = df_hist_show["Ganho Mês"].apply(fmt_money)
            st.dataframe(df_hist_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — COMPARATIVO ENTRE DATAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_comp:
    col_c, col_a, col_b = st.columns(3)
    with col_c:
        cliente_comp = st.selectbox("Cliente", clientes, key="comp_cli")
    datas_cli = sorted(
        {d.get("data_extrato","") for d in grupos.get(cliente_comp, [])},
        key=_parse_data,
        reverse=True,
    )
    if len(datas_cli) < 2:
        st.info("Este cliente tem menos de 2 datas — adicione outro PDF para comparar.")
    else:
        with col_a:
            data_a = st.selectbox("Data A (anterior)", datas_cli[1:], key="comp_a")
        with col_b:
            datas_b_opts = [d for d in datas_cli if d != data_a]
            data_b = st.selectbox("Data B (recente)", datas_b_opts, key="comp_b")

        rep_a = next((d for d in grupos[cliente_comp] if d.get("data_extrato") == data_a), None)
        rep_b = next((d for d in grupos[cliente_comp] if d.get("data_extrato") == data_b), None)

        if not (rep_a and rep_b):
            st.warning("Não foi possível localizar os relatórios das datas selecionadas.")
        else:
            # ── KPIs ──────────────────────────────────────────────────────────
            sb_a = rep_a.get("saldo_bruto_total") or 0
            sb_b = rep_b.get("saldo_bruto_total") or 0
            sl_a = rep_a.get("saldo_liquido_total") or 0
            sl_b = rep_b.get("saldo_liquido_total") or 0
            ganho_b = rep_b.get("ganho_mes_total") or 0
            n_a = len(rep_a.get("ativos", []))
            n_b = len(rep_b.get("ativos", []))

            def _delta_pct(a, b):
                if not a:
                    return None
                return (b - a) / a * 100

            def _fmt_delta(valor, pct):
                """Sinal ASCII no início para Streamlit detectar cor (+verde / -vermelho)."""
                if valor is None:
                    return None
                sign = '-' if valor < 0 else '+'
                money_part = fmt_money(abs(valor), abbrev=True).replace('R$ ', 'R$ ')
                if pct is None:
                    return f"{sign}{money_part}"
                # fmt_pct dá ex "1,07%" — colocamos sinal manual entre parênteses
                pct_sign = '-' if pct < 0 else '+'
                pct_str = fmt_pct(abs(pct))
                return f"{sign}{money_part} ({pct_sign}{pct_str})"

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                d_sb = sb_b - sb_a
                dp_sb = _delta_pct(sb_a, sb_b)
                st.metric(
                    "Δ Saldo Bruto",
                    fmt_money(sb_b, abbrev=True),
                    delta=_fmt_delta(d_sb, dp_sb),
                )
            with k2:
                d_sl = sl_b - sl_a
                dp_sl = _delta_pct(sl_a, sl_b)
                st.metric(
                    "Δ Saldo Líquido",
                    fmt_money(sl_b, abbrev=True),
                    delta=_fmt_delta(d_sl, dp_sl),
                )
            with k3:
                st.metric("Ganho Mês (B)", fmt_money(ganho_b, abbrev=True))
            with k4:
                st.metric(
                    "Nº Ativos",
                    f"{n_b}",
                    delta=f"{n_b - n_a:+d}" if n_a else None,
                )

            st.divider()

            # ── Comparativo por Estratégia ────────────────────────────────────
            st.markdown("### Por Estratégia")

            def _subt_dict(rep):
                out = {}
                for s in rep.get("subtotais", []):
                    est = s.get("estrategia") or ""
                    out[est] = s.get("saldo_liquido") or 0
                return out

            sub_a = _subt_dict(rep_a)
            sub_b = _subt_dict(rep_b)
            estr_keys = sorted(set(sub_a) | set(sub_b))

            rows_est = []
            for e in estr_keys:
                va = sub_a.get(e, 0)
                vb = sub_b.get(e, 0)
                rows_est.append({
                    "Estratégia": e,
                    "Saldo A": va,
                    "Saldo B": vb,
                    "Δ R$": vb - va,
                    "Δ %": _delta_pct(va, vb),
                })
            df_est = pd.DataFrame(rows_est).sort_values("Δ R$", ascending=False)

            # Gráfico de barras dos deltas por estratégia
            df_chart = df_est[df_est["Δ R$"].abs() > 0].copy()
            if not df_chart.empty:
                df_chart["cor"] = df_chart["Δ R$"].apply(lambda v: VERDE if v >= 0 else VERMELHO)
                df_chart["EstrFmt"] = df_chart["Estratégia"].apply(fmt_estrategia)
                fig_est = go.Figure(go.Bar(
                    x=df_chart["EstrFmt"],
                    y=df_chart["Δ R$"],
                    marker=dict(
                        color=df_chart["cor"],
                        line=dict(color=NAVY, width=1),
                    ),
                    text=[fmt_money(v, abbrev=True) for v in df_chart["Δ R$"]],
                    textposition="outside",
                    cliponaxis=False,
                    customdata=df_chart[["Saldo A","Saldo B","Δ %"]].values,
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        f"Saldo {data_a}: " + "R$ %{customdata[0]:,.2f}<br>"
                        f"Saldo {data_b}: " + "R$ %{customdata[1]:,.2f}<br>"
                        "Δ R$: %{y:,.2f}<br>"
                        "Δ %: %{customdata[2]:.2f}%"
                        "<extra></extra>"
                    ),
                ))
                # Linha de referência: zero
                fig_est.add_hline(
                    y=0, line_color=CINZA_TX, line_width=1,
                )
                # Linha de referência: variação total
                delta_total = df_chart["Δ R$"].sum()
                if abs(delta_total) > 1:
                    fig_est.add_hline(
                        y=delta_total / len(df_chart),
                        line_dash="dot", line_color=PERIW,
                        annotation_text=f"Δ médio: {fmt_money(delta_total / len(df_chart), abbrev=True)}",
                        annotation_position="top right",
                    )
                fig_est.update_layout(
                    title=f"Δ Saldo Líquido por Estratégia  ({data_a} → {data_b})",
                    height=380,
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis_title="R$", xaxis_title="",
                    margin=dict(t=60, b=40),
                    hovermode="x",
                    hoverdistance=100,
                    hoverlabel=dict(
                        bgcolor=NAVY, bordercolor=ELECTRIC, font_size=13,
                        font_color="white",
                    ),
                    yaxis=dict(
                        showspikes=True, spikecolor=ELECTRIC, spikedash="dot",
                        spikethickness=1, spikemode="across",
                    ),
                )
                st.plotly_chart(fig_est, use_container_width=True, key="comp_bar")

            # Tabela formatada
            df_est_show = df_est.copy()
            df_est_show["Estratégia"] = df_est_show["Estratégia"].apply(fmt_estrategia)
            df_est_show["Saldo A"] = df_est_show["Saldo A"].apply(fmt_money)
            df_est_show["Saldo B"] = df_est_show["Saldo B"].apply(fmt_money)
            df_est_show["Δ R$"]   = df_est_show["Δ R$"].apply(fmt_money)
            df_est_show["Δ %"]    = df_est_show["Δ %"].apply(lambda v: fmt_pct(v) if v is not None else "—")
            st.dataframe(df_est_show, use_container_width=True, hide_index=True)

            st.divider()

            # ── Top variações por Ativo (em ambas as datas) ──────────────────
            def _ativos_dict(rep):
                out = {}
                for a in rep.get("ativos", []):
                    key = (a.get("estrategia") or "", a.get("nome") or "")
                    out[key] = {
                        "saldo_liq": a.get("saldo_liquido") or 0,
                        "part_pct": a.get("part_pct"),
                        "ret_mes": a.get("rentabilidade_mes"),
                    }
                return out

            at_a = _ativos_dict(rep_a)
            at_b = _ativos_dict(rep_b)
            comuns = [k for k in at_b if k in at_a]

            if comuns:
                rows_var = []
                for k in comuns:
                    va = at_a[k]["saldo_liq"]
                    vb = at_b[k]["saldo_liq"]
                    rows_var.append({
                        "Estratégia": fmt_estrategia(k[0]),
                        "Ativo": fmt_ativo(k[1]),
                        "Saldo A": va,
                        "Saldo B": vb,
                        "Δ R$": vb - va,
                        "Δ %": _delta_pct(va, vb),
                    })
                df_var = pd.DataFrame(rows_var)
                df_var = df_var[df_var["Δ R$"].abs() > 0.01]

                if not df_var.empty:
                    st.markdown("### Top variações por Ativo")
                    df_top = df_var.reindex(
                        df_var["Δ R$"].abs().sort_values(ascending=False).index
                    ).head(15).copy()
                    df_top["Saldo A"] = df_top["Saldo A"].apply(fmt_money)
                    df_top["Saldo B"] = df_top["Saldo B"].apply(fmt_money)
                    df_top["Δ R$"]   = df_top["Δ R$"].apply(fmt_money)
                    df_top["Δ %"]    = df_top["Δ %"].apply(lambda v: fmt_pct(v) if v is not None else "—")
                    st.dataframe(df_top, use_container_width=True, hide_index=True)
                    st.divider()

            # ── Comparativo de Rentabilidade por Estratégia ───────────────────
            st.markdown("### Retorno do Mês por Estratégia")

            def _ret_mes_dict(rep):
                return {
                    (r.get("estrategia") or ""): r.get("ret_mes")
                    for r in rep.get("rentabilidades_estrategia", [])
                }

            r_a = _ret_mes_dict(rep_a)
            r_b = _ret_mes_dict(rep_b)
            estr_r = sorted(set(r_a) | set(r_b))
            rows_r = []
            for e in estr_r:
                rows_r.append({
                    "Estratégia": fmt_estrategia(e),
                    f"Ret.Mês {data_a}": r_a.get(e),
                    f"Ret.Mês {data_b}": r_b.get(e),
                })
            df_r = pd.DataFrame(rows_r)
            for col in df_r.columns[1:]:
                df_r[col] = df_r[col].apply(lambda v: fmt_pct(v) if v is not None else "—")
            st.dataframe(df_r, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — MOVIMENTAÇÕES (Aplicações, Resgates, Rendimentos, Imposto)
# ══════════════════════════════════════════════════════════════════════════════
with tab_mov:
    col_mc, col_md = st.columns([2, 2])
    with col_mc:
        cliente_mov = st.selectbox("Cliente", clientes, key="mov_cliente")
    with col_md:
        datas_mov = sorted(datas_por_cliente.get(cliente_mov, []),
                           key=_parse_data, reverse=True)
        data_mov  = st.selectbox("Data", datas_mov, key="mov_data")

    dado_mov = next(
        (d for d in grupos.get(cliente_mov, []) if d.get("data_extrato") == data_mov),
        None,
    )

    if dado_mov is None:
        st.warning("Nenhum dado encontrado para a seleção.")
    else:
        ativos_mov = dado_mov.get("ativos") or []

        # Filtra apenas ativos com movimentação (algum dos campos != 0)
        def _tem_mov(a):
            return any(
                (a.get(k) or 0) != 0
                for k in ("aplicacoes", "resgates", "rendimentos", "imposto_pago")
            )

        ativos_com_mov = [a for a in ativos_mov if _tem_mov(a)]

        # ── KPIs no topo ──────────────────────────────────────────────────────
        total_apl = sum((a.get("aplicacoes") or 0) for a in ativos_mov)
        total_res = sum((a.get("resgates") or 0) for a in ativos_mov)
        total_rend = sum((a.get("rendimentos") or 0) for a in ativos_mov)
        total_imp = sum((a.get("imposto_pago") or 0) for a in ativos_mov)
        fluxo_liq = total_apl + total_res + total_rend + total_imp

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Aplicações", fmt_money(total_apl, abbrev=True))
        k2.metric("Resgates", fmt_money(total_res, abbrev=True))
        k3.metric("Rendimentos", fmt_money(total_rend, abbrev=True))
        k4.metric("Imposto Pago", fmt_money(total_imp, abbrev=True))
        k5.metric("Fluxo Líquido", fmt_money(fluxo_liq, abbrev=True))

        st.divider()

        if not ativos_com_mov:
            st.info("Nenhuma movimentação registrada nesta data.")
        else:
            # ── Por Estratégia ─────────────────────────────────────────────────
            st.markdown("### Movimentações por Estratégia")
            from collections import defaultdict
            agg = defaultdict(lambda: {"aplicacoes":0,"resgates":0,"rendimentos":0,"imposto_pago":0})
            for a in ativos_com_mov:
                est = a.get("estrategia") or "?"
                agg[est]["aplicacoes"]   += (a.get("aplicacoes") or 0)
                agg[est]["resgates"]     += (a.get("resgates") or 0)
                agg[est]["rendimentos"]  += (a.get("rendimentos") or 0)
                agg[est]["imposto_pago"] += (a.get("imposto_pago") or 0)

            rows_est = []
            for est, v in agg.items():
                liq = v["aplicacoes"] + v["resgates"] + v["rendimentos"] + v["imposto_pago"]
                rows_est.append({
                    "Estratégia": fmt_estrategia(est),
                    "Aplicações": v["aplicacoes"],
                    "Resgates":   v["resgates"],
                    "Rendimentos": v["rendimentos"],
                    "Imposto Pago": v["imposto_pago"],
                    "Fluxo Líquido": liq,
                })
            df_est_mov = pd.DataFrame(rows_est).sort_values("Fluxo Líquido", ascending=False)
            df_est_mov_show = df_est_mov.copy()
            for col in ("Aplicações","Resgates","Rendimentos","Imposto Pago","Fluxo Líquido"):
                df_est_mov_show[col] = df_est_mov_show[col].apply(fmt_money)
            st.dataframe(df_est_mov_show, use_container_width=True, hide_index=True)

            st.divider()

            # ── Filtros pra tabela detalhada ───────────────────────────────────
            st.markdown("### Detalhamento por Ativo")
            cf1, cf2 = st.columns([2, 2])
            with cf1:
                estr_uniq = sorted({a.get("estrategia","") for a in ativos_com_mov})
                est_filtro = st.selectbox(
                    "Estratégia",
                    ["Todas"] + estr_uniq,
                    key="mov_est_filtro",
                    format_func=lambda v: v if v == "Todas" else fmt_estrategia(v),
                )
            with cf2:
                tipo_filtro = st.multiselect(
                    "Tipo de movimentação",
                    ["Aplicações", "Resgates", "Rendimentos", "Imposto Pago"],
                    default=["Aplicações", "Resgates", "Rendimentos", "Imposto Pago"],
                    key="mov_tipo_filtro",
                )

            # Aplica filtros
            ativos_filt = ativos_com_mov
            if est_filtro != "Todas":
                ativos_filt = [a for a in ativos_filt if a.get("estrategia") == est_filtro]

            tipo_map = {
                "Aplicações": "aplicacoes",
                "Resgates": "resgates",
                "Rendimentos": "rendimentos",
                "Imposto Pago": "imposto_pago",
            }
            tipos_ativos = {tipo_map[t] for t in tipo_filtro}
            if tipos_ativos:
                ativos_filt = [
                    a for a in ativos_filt
                    if any((a.get(k) or 0) != 0 for k in tipos_ativos)
                ]

            if not ativos_filt:
                st.info("Nenhum ativo corresponde aos filtros selecionados.")
            else:
                rows_at = []
                for a in ativos_filt:
                    rows_at.append({
                        "Estratégia": fmt_estrategia(a.get("estrategia") or ""),
                        "Ativo": fmt_ativo(a.get("nome") or ""),
                        "Aplicações": a.get("aplicacoes") or 0,
                        "Resgates":   a.get("resgates") or 0,
                        "Rendimentos": a.get("rendimentos") or 0,
                        "Imposto Pago": a.get("imposto_pago") or 0,
                        "Saldo Líquido": a.get("saldo_liquido") or 0,
                    })
                df_at_mov = pd.DataFrame(rows_at)
                df_at_mov["Fluxo Líquido"] = (
                    df_at_mov["Aplicações"] + df_at_mov["Resgates"]
                    + df_at_mov["Rendimentos"] + df_at_mov["Imposto Pago"]
                )
                df_at_mov = df_at_mov.sort_values(
                    ["Estratégia", "Fluxo Líquido"], ascending=[True, False]
                )

                df_at_mov_show = df_at_mov.copy()
                for col in ("Aplicações","Resgates","Rendimentos","Imposto Pago",
                            "Saldo Líquido","Fluxo Líquido"):
                    df_at_mov_show[col] = df_at_mov_show[col].apply(fmt_money)
                st.dataframe(df_at_mov_show, use_container_width=True, hide_index=True,
                             height=480)

                # Download CSV
                csv_data = df_at_mov.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 Baixar movimentações (CSV)",
                    data=csv_data,
                    file_name=f"movimentacoes_{cliente_mov}_{data_mov.replace('/','-')}.csv",
                    mime="text/csv",
                )
