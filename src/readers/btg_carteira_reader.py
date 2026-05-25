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


def _br2float(s):
    """Converte número no formato brasileiro (1.234.567,89) para float."""
    if s is None:
        return None
    s = str(s).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _ler_formato_lupa(texto_p1: str) -> dict:
    """
    Parser para o formato 'Carteira Diária' (LUPA e similares).
    Extrai data, patrimônio, performance e posições a partir da pág 1.
    """
    # data_base
    data_base = ""
    m = re.search(r'Data de Posi[çc][ãa]o\s*:\s*(\d{2}/\d{2}/\d{4})', texto_p1)
    if m:
        data_base = m.group(1)

    # patrimônio (formato BR)
    patrimonio = 0.0
    m = re.search(r'Total do Patrim[ôo]nio\s+([\d.]+,\d+)', texto_p1)
    if m:
        patrimonio = _br2float(m.group(1)) or 0.0

    # performance e benchmark — tabela Rentabilidade Acumulada
    # Colunas: Indexador | BenchMark | Rent.Real | Var.Diária | Var.Mensal | Var.Anual | Últimos 6M | Últimos 12M
    perf_total = {"mes": None, "ano": None, "m12": None, "m24": None}
    pct_bench  = {"mes": None, "ano": None, "m12": None, "m24": None}

    _PCT = r'([-\d]+,\d+)%'  # captura um valor percentual BR

    # Linha COTA: "COTA ... % ... % ..."
    m_cota = re.search(
        r'COTA\s+\S+\s+\S+\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT,
        texto_p1
    )
    if m_cota:
        perf_total["mes"] = (_br2float(m_cota.group(1)) or 0) / 100
        perf_total["ano"] = (_br2float(m_cota.group(2)) or 0) / 100
        perf_total["m12"] = (_br2float(m_cota.group(5)) or 0) / 100

    # Linha CDI para benchmark
    m_cdi = re.search(
        r'CDI\s+\S+\s+\S+\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT + r'\s+' + _PCT,
        texto_p1
    )
    if m_cdi:
        pct_bench["mes"] = (_br2float(m_cdi.group(1)) or 0) / 100
        pct_bench["ano"] = (_br2float(m_cdi.group(2)) or 0) / 100
        pct_bench["m12"] = (_br2float(m_cdi.group(5)) or 0) / 100

    # posições — linhas: {6-digit-code} {NOME FUNDO+INST} {qty} ... {valor_atual} 0,00 {valor_liq} {%s/fi}% ...
    fundos = []
    _LUPA_FUNDO = re.compile(
        r'^(\d{6})\s+'           # código 6 dígitos
        r'(.+?)\s+'              # nome do fundo (greedy mínimo)
        r'[\d.]+,\d+\s+'         # quantidade
        r'[\d.]+,\d+\s+'         # qtd bloqueada (0)
        r'[\d.]+,\d+\s+'         # valor cota
        r'[\d.]+,\d+\s+'         # valor aplic/resg
        r'([\d.]+,\d+)\s+'       # valor atual  ← grupo 3
        r'[\d.,]+\s+'            # impostos
        r'[\d.]+,\d+\s+'         # valor líquido
        r'([\d.,]+)%'            # % s/fi  ← grupo 4
    )
    vistos = set()
    for linha in texto_p1.split("\n"):
        mf = _LUPA_FUNDO.match(linha.strip())
        if mf:
            nome = mf.group(2).strip()
            if nome in vistos:
                continue
            vistos.add(nome)
            valor_atual = _br2float(mf.group(3)) or 0.0
            pct_fi = _br2float(mf.group(4)) or 0.0
            fundos.append({
                "nome":       nome,
                "pl":         round(pct_fi, 2),
                "financeiro": valor_atual,
                "mes":        None,
                "ano":        None,
                "m12":        None,
                "m24":        None,
            })

    fundos.sort(key=lambda x: x["financeiro"], reverse=True)

    return {
        "data_base":  data_base,
        "patrimonio": patrimonio,
        "perf_total": perf_total,
        "pct_bench":  pct_bench,
        "fundos":     fundos,
    }


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
        # Para formato Lupa lemos todas as páginas na p1 também
        texto_todas = texto_p1
        for idx in range(1, len(pdf.pages)):
            texto_todas += "\n" + (pdf.pages[idx].extract_text() or "")
        texto_carteira = ""
        for idx in range(2, min(len(pdf.pages), 5)):
            texto_carteira += "\n" + (pdf.pages[idx].extract_text() or "")

    # Formato "Carteira Diária" (LUPA e similares)
    if "Carteira Di" in texto_p1:
        return _ler_formato_lupa(texto_todas)

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
    """
    Formato LHC: duas tabelas na pág 1.
    Tabela 1 — Dia/Mês/Ano/Desde: Data|PL|Cota|Dia%|Dia%CDI|Mês%|Mês%CDI|Ano%|Ano%CDI|...
    Tabela 2 — 3M/6M/12M/24M:    Data|PL|Cota|3M%|3M%CDI|6M%|6M%CDI|12M%|12M%CDI|24M%|24M%CDI
    """
    data_base  = ""
    patrimonio = 0.0

    m = re.search(r'em\s+(\d{2}/\d{2}/\d{4})\s*([\d,]+\.\d{2})', texto, re.S)
    if m:
        data_base  = m.group(1)
        patrimonio = float(m.group(2).replace(",", ""))
    if not data_base:
        m2 = re.search(r'(\d{2}/\d{2}/\d{4})\s*([\d,]+\.\d{2})', texto)
        if m2:
            data_base  = m2.group(1)
            patrimonio = float(m2.group(2).replace(",", ""))

    perf_total = {"mes": None, "ano": None, "m12": None, "m24": None}
    pct_bench  = {"mes": None, "ano": None, "m12": None, "m24": None}

    for tabela in tabelas:
        # Detecta tipo pelo cabeçalho: "Dia" só existe na tabela Dia/Mês/Ano
        todas_cells = " ".join(str(c or "") for row in tabela for c in (row or []))
        is_curta = "Dia" in todas_cells and "3 Meses" not in todas_cells
        is_longa = "3 Meses" in todas_cells or "12 Meses" in todas_cells

        for linha in tabela:
            if not linha:
                continue
            cells = [str(c or "").strip() for c in linha]
            if not cells or not re.match(r'\d{2}/\d{2}/\d{4}', cells[0]):
                continue
            # nums[i] corresponde a cells[i+1] (após a data)
            # Estrutura: [PL, Cota, p1%, p1%CDI, p2%, p2%CDI, p3%, p3%CDI, ...]
            nums = [_num(c) for c in cells[1:]]
            if len(nums) < 8:
                continue
            try:
                if is_curta and perf_total["mes"] is None:
                    # índices: 0=PL, 1=Cota, 2=Dia%, 3=Dia%CDI, 4=Mês%, 5=Mês%CDI, 6=Ano%, 7=Ano%CDI
                    perf_total["mes"] = nums[4] / 100 if nums[4] is not None else None
                    pct_bench["mes"]  = nums[5] / 100 if nums[5] is not None else None
                    perf_total["ano"] = nums[6] / 100 if nums[6] is not None else None
                    pct_bench["ano"]  = nums[7] / 100 if nums[7] is not None else None
                    break
                elif is_longa and perf_total["m12"] is None:
                    # índices: 0=PL, 1=Cota, 2=3M%, 3=3M%CDI, 4=6M%, 5=6M%CDI, 6=12M%, 7=12M%CDI, 8=24M%, 9=24M%CDI
                    perf_total["m12"] = nums[6] / 100 if nums[6] is not None else None
                    pct_bench["m12"]  = nums[7] / 100 if nums[7] is not None else None
                    if len(nums) > 8 and nums[8] is not None and nums[8] != 0:
                        perf_total["m24"] = nums[8] / 100
                    break
            except (IndexError, TypeError):
                continue

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
