import pdfplumber
import re
import os

# Padrão: data patrimônio cota val1 val2 val3 val4 val5 val6 val7 val8
_LINHA = r'(\d{2}/\d{2}/\d{4})\s+[\d,]+\.\d+\s+[\d.]+\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)'

def ler_btg_pdf(caminho: str) -> dict:
    """
    Lê carteira diária do BTG e extrai performance do fundo.
    Retorna dict com retornos em decimal e %CDI em decimal.
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"PDF não encontrado: {caminho}")

    texto = ""
    with pdfplumber.open(caminho) as pdf:
        texto = pdf.pages[0].extract_text() or ""

    linhas = [l.strip() for l in texto.split("\n")]
    matches = []
    for linha in linhas:
        m = re.match(_LINHA, linha)
        if m:
            matches.append(m)

    if len(matches) < 2:
        raise ValueError(f"Não foi possível extrair performance de {caminho}")

    # Primeira tabela: Dia | Mês | Ano | Desde Início (posições 2-9)
    t1 = matches[0]
    mes_pct   = float(t1.group(4)) / 100
    mes_cdi   = float(t1.group(5)) / 100
    ano_pct   = float(t1.group(6)) / 100
    ano_cdi   = float(t1.group(7)) / 100

    # Segunda tabela: 3M | 6M | 12M | 24M
    t2 = matches[len(matches) // 2]  # segunda metade
    m12_pct   = float(t2.group(6)) / 100
    m12_cdi   = float(t2.group(7)) / 100
    m24_pct   = float(t2.group(8)) / 100
    m24_cdi   = float(t2.group(9)) / 100

    return {
        "mes": mes_pct,
        "ano": ano_pct,
        "m12": m12_pct,
        "m24": m24_pct,
        # %CDI como decimal (ex: 98.56% → 0.9856)
        "mes_cdi": mes_cdi,
        "ano_cdi": ano_cdi,
        "m12_cdi": m12_cdi,
        "m24_cdi": m24_cdi,
    }

def carregar_overrides_btg(pasta: str) -> dict:
    """
    Varre pasta data/input/pdf/ e carrega todos os PDFs do BTG.
    Nome do arquivo: AcompFI_{NOME_FUNDO}_{DATA}.pdf
    Retorna dict: {nome_parcial → dados_btg}
    """
    overrides = {}
    if not os.path.exists(pasta):
        return overrides

    for arquivo in os.listdir(pasta):
        if not arquivo.endswith(".pdf"):
            continue
        caminho = os.path.join(pasta, arquivo)
        try:
            dados = ler_btg_pdf(caminho)
            # extrai nome do fundo do filename
            partes = arquivo.replace("AcompFI_", "").rsplit("_", 1)
            nome_btg = partes[0].strip()
            overrides[nome_btg] = dados
            print(f"  BTG override carregado: {nome_btg}")
        except Exception as e:
            print(f"  Aviso: nao foi possivel ler {arquivo}: {e}")

    return overrides
