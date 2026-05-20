import pdfplumber
import re
import os

# Reutiliza o mesmo padrão do btg_pdf_reader para extrair rentabilidade da pag 1
_LINHA = r'(\d{2}/\d{2}/\d{4})\s+[\d,]+\.\d+\s+[\d.]+\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)'

# Fundo: nome %PL financeiro [liquidez]  (sem $ — há mais texto após liquidez)
_FUNDO  = re.compile(r'^(.+?)\s+(\d{1,3}\.\d{2})\s+([\d,]+\.\d{2})')
# Rentabilidade: % dia mes ano 12m 24m [desde]  (NÃO começa com % CDI / % IBOV)
_PERF   = re.compile(r'^%\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s+([-\d.]+|-)\s*([-\d.]+|-)?')


def _val(s):
    if s is None or s.strip() in ('-', ''):
        return None
    return float(s) / 100


def ler_sabia(caminho: str) -> dict:
    """
    Lê o PDF BTG do SABIÁ e retorna:
    {
      data_base, patrimonio,
      perf_total: {mes, ano, m12, m24},
      pct_cdi:    {mes, ano, m12, m24},
      fundos: [{nome, pl, financeiro, mes, ano, m12, m24}, ...]
    }
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"PDF nao encontrado: {caminho}")

    with pdfplumber.open(caminho) as pdf:
        texto_p1 = pdf.pages[0].extract_text() or ""
        # Carteira está nas páginas 3 e 4 (índice 2 e 3)
        texto_carteira = ""
        for idx in [2, 3]:
            if idx < len(pdf.pages):
                texto_carteira += "\n" + (pdf.pages[idx].extract_text() or "")

    perf_total, pct_cdi, data_base, patrimonio = _extrair_perf_p1(texto_p1)
    fundos = _extrair_carteira(texto_carteira)

    return {
        "data_base":  data_base,
        "patrimonio": patrimonio,
        "perf_total": perf_total,
        "pct_cdi":    pct_cdi,
        "fundos":     fundos,
    }


def _extrair_perf_p1(texto):
    """Extrai performance total e %CDI da página 1."""
    matches = []
    for linha in texto.split("\n"):
        m = re.search(_LINHA, linha)
        if m:
            matches.append(m)

    # Primeira tabela (Dia/Mês/Ano/Desde): grupos 4=mês%, 5=%CDImes, 6=ano%, 7=%CDIano
    t1 = matches[0]
    mes_pct = float(t1.group(4)) / 100
    mes_cdi = float(t1.group(5)) / 100
    ano_pct = float(t1.group(6)) / 100
    ano_cdi = float(t1.group(7)) / 100

    # Data base e patrimônio da primeira linha
    data_base = t1.group(1)
    pat_m = re.search(r'(\d{2}/\d{2}/\d{4})\s+([\d,]+\.\d{2})', texto)
    patrimonio = float(pat_m.group(2).replace(",", "")) if pat_m else 0.0

    # Segunda tabela (3M/6M/12M/24M): grupos 6=12m%, 7=%CDI12m, 8=24m%, 9=%CDI24m
    meio = len(matches) // 2
    t2 = matches[meio]
    m12_pct = float(t2.group(6)) / 100
    m12_cdi = float(t2.group(7)) / 100
    m24_pct = float(t2.group(8)) / 100
    m24_cdi = float(t2.group(9)) / 100

    perf_total = {"mes": mes_pct, "ano": ano_pct, "m12": m12_pct, "m24": m24_pct}
    pct_cdi    = {"mes": mes_cdi, "ano": ano_cdi, "m12": m12_cdi, "m24": m24_cdi}

    return perf_total, pct_cdi, data_base, patrimonio


def _extrair_carteira(texto):
    """
    Extrai todos os fundos da seção Carteira (páginas 3-4).

    Formato real do PDF (linha de % vem ANTES da linha do fundo):
      % DIA MES ANO 12M 24M DESDE [texto_gestor]
      NOME_FUNDO PL FINANCEIRO [LIQUIDEZ] [DATA] [...]
      % CDI / % IBOV [valores comparativos]

    Retorna lista de dicts: {nome, pl, financeiro, mes, ano, m12, m24}
    """
    linhas = [l.strip() for l in texto.split("\n")]
    fundos = []
    i = 0

    while i < len(linhas):
        linha = linhas[i]

        # Identifica linha de rentabilidade (começa com % mas não % CDI / % IBOV)
        if (linha.startswith('%')
                and not linha.startswith('% CDI')
                and not linha.startswith('% IBOV')
                and not linha.startswith('%PL')):

            mp = _PERF.match(linha)
            if mp:
                # grupos: 1=dia, 2=mes, 3=ano, 4=12m, 5=24m
                mes_v = _val(mp.group(2))
                ano_v = _val(mp.group(3))
                m12_v = _val(mp.group(4))
                m24_v = _val(mp.group(5))

                # A linha do fundo vem logo a seguir (i+1)
                if i + 1 < len(linhas):
                    prox = linhas[i + 1]
                    mf = _FUNDO.match(prox)
                    if mf:
                        nome       = mf.group(1).strip()
                        pl         = float(mf.group(2))
                        financeiro = float(mf.group(3).replace(",", ""))

                        # Ignora a seção "Outros" (taxas/despesas)
                        palavras_skip = ('A PAGAR', 'A RECEBER', 'DESPESA', 'OUTROS')
                        if not any(nome.upper().startswith(p) for p in palavras_skip):
                            fundos.append({
                                "nome":       nome,
                                "pl":         pl,
                                "financeiro": financeiro,
                                "mes":        mes_v,
                                "ano":        ano_v,
                                "m12":        m12_v,
                                "m24":        m24_v,
                            })
                        i += 2
                        continue
        i += 1

    # Remove duplicatas mantendo o primeiro
    vistos = set()
    fundos_unicos = []
    for f in fundos:
        if f["nome"] not in vistos:
            vistos.add(f["nome"])
            fundos_unicos.append(f)

    # Ordena por %PL decrescente
    fundos_unicos.sort(key=lambda x: x["pl"], reverse=True)
    return fundos_unicos


def encontrar_pdf_sabia(pasta: str) -> str | None:
    """Encontra o PDF do SABIÁ na pasta de PDFs."""
    if not os.path.exists(pasta):
        return None
    for arq in sorted(os.listdir(pasta), reverse=True):  # mais recente primeiro
        if arq.lower().endswith(".pdf") and "sabia" in arq.lower():
            return os.path.join(pasta, arq)
    return None
