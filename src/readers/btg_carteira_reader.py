"""
Reader genérico para qualquer PDF BTG de carteira (AcompFI_*.pdf).
Funciona para SABIÁ, MAITACA e qualquer outro fundo BTG.
"""
import pdfplumber
import re
import os

_LINHA = r'(\d{2}/\d{2}/\d{4})\s+[\d,]+\.\d+\s+[\d.]+\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)'
_FUNDO = re.compile(r'^(.+?)\s+(\d{1,3}\.\d{2})\s+([\d,]+\.\d{2})')
_PERF  = re.compile(r'^%\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s*([-\d.]+|-)?')


def _val(s):
    if s is None or str(s).strip() in ('-', ''):
        return None
    return float(s) / 100


def ler_carteira_btg(caminho: str) -> dict:
    """
    Lê qualquer PDF BTG de carteira diária.
    Retorna:
    {
      data_base, patrimonio,
      perf_total: {mes, ano, m12, m24},
      pct_bench:  {mes, ano, m12, m24},   # %CDI da pag 1
      fundos: [{nome, pl, financeiro, mes, ano, m12, m24}, ...]
    }
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"PDF não encontrado: {caminho}")

    with pdfplumber.open(caminho) as pdf:
        texto_p1 = pdf.pages[0].extract_text() or ""
        texto_carteira = ""
        for idx in range(2, min(len(pdf.pages), 5)):
            texto_carteira += "\n" + (pdf.pages[idx].extract_text() or "")

    perf_total, pct_bench, data_base, patrimonio = _extrair_perf_p1(texto_p1)
    fundos = _extrair_carteira(texto_carteira)

    return {
        "data_base":  data_base,
        "patrimonio": patrimonio,
        "perf_total": perf_total,
        "pct_bench":  pct_bench,
        "fundos":     fundos,
    }


def _extrair_perf_p1(texto):
    matches = []
    for linha in texto.split("\n"):
        m = re.search(_LINHA, linha)
        if m:
            matches.append(m)

    if not matches:
        return {}, {}, "", 0.0

    t1 = matches[0]
    data_base  = t1.group(1)
    mes_pct    = float(t1.group(4)) / 100
    mes_bench  = float(t1.group(5)) / 100
    ano_pct    = float(t1.group(6)) / 100
    ano_bench  = float(t1.group(7)) / 100

    # Patrimônio da mesma linha
    pat_m = re.search(r'(\d{2}/\d{2}/\d{4})\s+([\d,]+\.\d{2})', texto)
    patrimonio = float(pat_m.group(2).replace(",", "")) if pat_m else 0.0

    # Segunda tabela (3M/6M/12M/24M)
    meio = len(matches) // 2
    t2 = matches[meio]
    m12_pct   = float(t2.group(6)) / 100
    m12_bench = float(t2.group(7)) / 100
    m24_pct   = float(t2.group(8)) / 100
    m24_bench = float(t2.group(9)) / 100

    perf_total = {"mes": mes_pct,   "ano": ano_pct,   "m12": m12_pct,   "m24": m24_pct}
    pct_bench  = {"mes": mes_bench, "ano": ano_bench, "m12": m12_bench, "m24": m24_bench}
    return perf_total, pct_bench, data_base, patrimonio


def _extrair_carteira(texto):
    """
    Formato do PDF BTG: linha % vem ANTES da linha do fundo.
      % DIA MES ANO 12M 24M DESDE [texto gestor]
      NOME_FUNDO PL FINANCEIRO [LIQUIDEZ] [DATA ...]
      % CDI / % IBOV [valores]
    """
    linhas = [l.strip() for l in texto.split("\n")]
    fundos = []
    i = 0
    SKIP = {'A PAGAR', 'A RECEBER', 'DESPESA', 'LTN ', 'LFT ', 'NTN '}

    while i < len(linhas):
        linha = linhas[i]

        if (linha.startswith('%')
                and not linha.startswith('% CDI')
                and not linha.startswith('% IBOV')
                and not linha.startswith('%PL')):

            mp = _PERF.match(linha)
            if mp and i + 1 < len(linhas):
                prox = linhas[i + 1]
                mf = _FUNDO.match(prox)
                if mf:
                    nome       = mf.group(1).strip()
                    pl         = float(mf.group(2))
                    financeiro = float(mf.group(3).replace(",", ""))

                    skip = any(nome.upper().startswith(p) for p in SKIP)
                    if not skip and pl > 0:
                        fundos.append({
                            "nome":       nome,
                            "pl":         pl,
                            "financeiro": financeiro,
                            "mes":  _val(mp.group(2)),
                            "ano":  _val(mp.group(3)),
                            "m12":  _val(mp.group(4)),
                            "m24":  _val(mp.group(5)),
                        })
                    i += 2
                    continue
        i += 1

    # Remove duplicatas mantendo o primeiro
    vistos = set()
    unicos = []
    for f in fundos:
        if f["nome"] not in vistos:
            vistos.add(f["nome"])
            unicos.append(f)

    unicos.sort(key=lambda x: x["pl"], reverse=True)
    return unicos


def encontrar_pdf_fundo(pasta: str, palavra_chave: str) -> str | None:
    """Encontra o PDF mais recente cujo nome contém a palavra-chave."""
    if not os.path.exists(pasta):
        return None
    matches = [
        arq for arq in os.listdir(pasta)
        if arq.lower().endswith(".pdf") and palavra_chave.lower() in arq.lower()
    ]
    if not matches:
        return None
    matches.sort(reverse=True)  # mais recente pelo nome
    return os.path.join(pasta, matches[0])
