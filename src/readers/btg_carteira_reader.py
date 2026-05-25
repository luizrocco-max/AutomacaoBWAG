"""
Reader genérico para qualquer PDF BTG de carteira (AcompFI_*.pdf).
Funciona para SABIÁ, MAITACA e qualquer outro fundo BTG.
Suporta dois formatos de página 1:
  - Formato 1 (EXCLUSIVE, FALCÃO...): tabela longa com data + 9 colunas numéricas
  - Formato 2 (LHC...): tabela curta com "em DATE / valor" e extração via extract_tables()
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


def _num(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def ler_carteira_btg(caminho: str) -> dict:
    """
    Lê qualquer PDF BTG de carteira diária.
    Retorna:
    {
      data_base, patrimonio,
      perf_total: {mes, ano, m12, m24},
      pct_bench:  {mes, ano, m12, m24},
      fundos: [{nome, pl, financeiro, mes, ano, m12, m24}, ...]
    }
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"PDF não encontrado: {caminho}")

    with pdfplumber.open(caminho) as pdf:
        texto_p1   = pdf.pages[0].extract_text() or ""
        tabelas_p1 = pdf.pages[0].extract_tables() or []
        texto_carteira = ""
        for idx in range(2, min(len(pdf.pages), 5)):
            texto_carteira += "\n" + (pdf.pages[idx].extract_text() or "")

    perf_total, pct_bench, data_base, patrimonio = _extrair_perf_p1(texto_p1, tabelas_p1)
    fundos = _extrair_carteira(texto_carteira)

    return {
        "data_base":  data_base,
        "patrimonio": patrimonio,
        "perf_total": perf_total,
        "pct_bench":  pct_bench,
        "fundos":     fundos,
    }


def _extrair_perf_p1(texto, tabelas=None):
    # Formato 1: linhas longas com data + 9 colunas (EXCLUSIVE, FALCÃO...)
    matches = []
    for linha in texto.split("\n"):
        m = re.search(_LINHA, linha)
        if m:
            matches.append(m)

    if matches:
        t1 = matches[0]
        data_base = t1.group(1)
        mes_pct   = float(t1.group(4)) / 100
        mes_bench = float(t1.group(5)) / 100
        ano_pct   = float(t1.group(6)) / 100
        ano_bench = float(t1.group(7)) / 100

        pat_m = re.search(r'(\d{2}/\d{2}/\d{4})\s+([\d,]+\.\d{2})', texto)
        patrimonio = float(pat_m.group(2).replace(",", "")) if pat_m else 0.0

        meio = len(matches) // 2
        t2 = matches[meio]
        m12_pct   = float(t2.group(6)) / 100
        m12_bench = float(t2.group(7)) / 100
        m24_pct   = float(t2.group(8)) / 100
        m24_bench = float(t2.group(9)) / 100

        perf_total = {"mes": mes_pct,   "ano": ano_pct,   "m12": m12_pct,   "m24": m24_pct}
        pct_bench  = {"mes": mes_bench, "ano": ano_bench, "m12": m12_bench, "m24": m24_bench}
        return perf_total, pct_bench, data_base, patrimonio

    # Formato 2 (LHC...): patrimônio via "em DATE\nVALOR", performance via tabelas
    return _extrair_perf_formato2(texto, tabelas or [])


def _extrair_perf_formato2(texto, tabelas):
    """Formato com 'em DD/MM/YYYY' + patrimônio e tabela de performance separada."""
    data_base  = ""
    patrimonio = 0.0

    # "em DD/MM/YYYY" seguido (com ou sem espaço) pelo valor do patrimônio
    m = re.search(r'em\s+(\d{2}/\d{2}/\d{4})\s*([\d,]+\.\d{2})', texto, re.S)
    if m:
        data_base  = m.group(1)
        patrimonio = float(m.group(2).replace(",", ""))

    # Fallback: primeira linha de tabela com data + patrimônio (com ou sem espaço)
    if not data_base:
        m2 = re.search(r'(\d{2}/\d{2}/\d{4})\s*([\d,]+\.\d{2})', texto)
        if m2:
            data_base  = m2.group(1)
            patrimonio = float(m2.group(2).replace(",", ""))

    perf_total = {"mes": None, "ano": None, "m12": None, "m24": None}
    pct_bench  = {"mes": None, "ano": None, "m12": None, "m24": None}

    # Tenta extrair performance das tabelas da página 1
    # Estrutura esperada: [Data, Patrimônio, Cota, Dia%, Dia%CDI, Mês%, Mês%CDI, Ano%, Ano%CDI, ...]
    for tabela in tabelas:
        for linha in tabela:
            if not linha:
                continue
            cells = [str(c or "").strip() for c in linha]
            if not cells or not re.match(r'\d{2}/\d{2}/\d{4}', cells[0]):
                continue
            nums = [_num(c) for c in cells[1:]]
            # Precisa pelo menos: patrimônio, cota, dia%, dia%CDI, mês%, mês%CDI, ano%, ano%CDI
            valid = [n for n in nums if n is not None]
            if len(valid) < 6:
                continue
            # Se o patrimônio ainda não foi encontrado, usa o primeiro número da linha
            if patrimonio == 0.0 and nums[0] is not None and nums[0] > 1000:
                patrimonio = nums[0]
            # Índices esperados: 0=PL, 1=cota, 2=dia%, 3=dia%CDI, 4=mês%, 5=mês%CDI, 6=ano%, 7=ano%CDI
            try:
                if len(valid) >= 6:
                    perf_total["mes"] = valid[2] / 100
                    pct_bench["mes"]  = valid[3] / 100
                if len(valid) >= 8:
                    perf_total["ano"] = valid[4] / 100
                    pct_bench["ano"]  = valid[5] / 100
                    perf_total["m12"] = valid[6] / 100 if len(valid) > 6 else None
                    pct_bench["m12"]  = valid[7] / 100 if len(valid) > 7 else None
            except (IndexError, TypeError):
                pass
            break  # usa só a primeira linha com data

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
    matches.sort(reverse=True)
    return os.path.join(pasta, matches[0])
