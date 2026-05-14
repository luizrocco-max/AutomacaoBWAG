from lxml import etree

NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"

def _formatar_mm(valor: float) -> str:
    """69781560.28 → '69,8MM'"""
    mm = valor / 1_000_000
    return f"{mm:,.1f}MM".replace(",", "X").replace(".", ",").replace("X", ".")

def _formatar_aum(valor: float) -> str:
    """Para o texto principal do AUM: R$729,1MM"""
    mm = valor / 1_000_000
    return f"R${mm:,.1f}MM".replace(",", "X").replace(".", ",").replace("X", ".")

def _formatar_valor(valor: float) -> str:
    """Para Fundos e Direto: R$ 633,6MM"""
    mm = valor / 1_000_000
    return f"R$ {mm:,.1f}MM".replace(",", "X").replace(".", ",").replace("X", ".")

def _atualizar_texto_shape(shape, linha0: str, linha1: str = None):
    """Atualiza até duas linhas de texto em um shape, preservando formatação."""
    tf = shape.text_frame
    paras = tf.paragraphs
    if paras and paras[0].runs:
        paras[0].runs[0].text = linha0
        for run in paras[0].runs[1:]:
            run.text = ""
    if linha1 and len(paras) > 1 and paras[1].runs:
        paras[1].runs[0].text = linha1
        for run in paras[1].runs[1:]:
            run.text = ""

def _atualizar_grafico_xml(shape, fundos: list):
    """Atualiza categorias e valores do gráfico de pizza via XML."""
    chart = shape.chart
    root = chart._element
    ns = {"c": NS}

    cats = root.findall(".//c:cat//c:v", ns)
    vals = root.findall(".//c:val//c:v", ns)

    for i, fundo in enumerate(fundos):
        if i < len(cats):
            cats[i].text = fundo["nome_curto"]
        if i < len(vals):
            vals[i].text = str(fundo["valor"])

def build_overview(slide, dados_quantum: dict, valor_fundos: float, valor_direto: float):
    """
    Atualiza o slide de Overview com dados do Quantum.

    dados_quantum: resultado de quantum_reader.ler_quantum()
    valor_fundos: total alocado em fundos (informado manualmente por enquanto)
    valor_direto: total em investimentos diretos
    """
    aum_total = dados_quantum["aum_total"]
    data_base = dados_quantum["data_base"]
    fundos = dados_quantum["fundos"]

    for shape in slide.shapes:
        nome = shape.name

        if nome == "CaixaDeTexto 7" and shape.has_text_frame:
            _atualizar_texto_shape(shape, "AUM", _formatar_aum(aum_total))

        elif nome == "CaixaDeTexto 11" and shape.has_text_frame:
            _atualizar_texto_shape(shape, "FUNDOS", _formatar_valor(valor_fundos))

        elif nome == "CaixaDeTexto 12" and shape.has_text_frame:
            _atualizar_texto_shape(shape, "DIRETO", _formatar_valor(valor_direto))

        elif "Rodap" in nome and shape.has_text_frame:
            tf = shape.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = (
                    f"Fontes: BWAG e Quantum Axis (data base {data_base})"
                )

        elif shape.shape_type == 3:  # CHART
            _atualizar_grafico_xml(shape, fundos)

    print(f"  Overview: AUM={_formatar_aum(aum_total)} | Fundos={_formatar_valor(valor_fundos)} | Direto={_formatar_valor(valor_direto)} | Data base={data_base}")
