"""
Lê o export do Quantum Axis com Beta - Ibovespa.
Retorna Beta (6m) e Beta (12m) por fundo, e retornos do Ibovespa.
"""
import pandas as pd
import os


def ler_quantum_beta(caminho: str) -> dict:
    """
    Lê o arquivo Quantum com colunas:
      Nome | Retorno mês | Retorno ano | 12M | 24M | Beta 6m | Beta 12m

    Retorna:
    {
      "fundos":    {nome_completo: {beta6m, beta12m, mes, ano, m12, m24}},
      "ibovespa":  {mes, ano, m12, m24}
    }
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    df = pd.read_excel(caminho, sheet_name="Quantum Axis", header=None)

    # Dados começam na linha 3 (índice 3)
    fundos = {}
    ibovespa = {}

    for i in range(3, len(df)):
        nome = df.iloc[i, 0]
        if pd.isna(nome) or str(nome).strip() == "":
            continue

        nome_str = str(nome).strip()

        def _v(col):
            v = df.iloc[i, col]
            return float(v) if pd.notna(v) and str(v).strip() != "" else None

        mes  = _v(1)
        ano  = _v(2)
        m12  = _v(3)
        m24  = _v(4)
        b6m  = _v(5)
        b12m = _v(6)

        dados = {
            "mes":   mes,
            "ano":   ano,
            "m12":   m12,
            "m24":   m24,
            "beta6m":  b6m,
            "beta12m": b12m,
        }

        if nome_str == "Ibovespa":
            ibovespa = {"mes": mes, "ano": ano, "m12": m12, "m24": m24}
        elif nome_str not in ("CDI", "Dólar", "IPCA"):
            fundos[nome_str] = dados

    return {"fundos": fundos, "ibovespa": ibovespa}


def match_nome_quantum(nome_pdf: str, quantum_nomes: list,
                       mapeamento: dict = None) -> str | None:
    """
    Tenta associar um nome curto do PDF ao nome completo do Quantum.
    Prioridade: mapeamento explícito do config > match automático.
    """
    if mapeamento and nome_pdf in mapeamento:
        alvo = mapeamento[nome_pdf]
        # Se o alvo está no Quantum, retorna; senão é só display name
        if alvo in quantum_nomes:
            return alvo
        return alvo  # retorna mesmo assim (display name)

    nome_up = nome_pdf.upper()

    # Match direto (ticker como BOVA11, SMAL11, DIVO11)
    for qnome in quantum_nomes:
        if nome_up in qnome.upper():
            return qnome

    # Match por palavras relevantes (ignora sufixos genéricos)
    IGNORAR = {'FIC', 'FIA', 'FIF', 'FIM', 'FC', 'CIC', 'CP', 'IE',
               'RESP', 'LIMITADA', 'FI', 'DE', 'DO', 'DA', 'E', 'A'}
    tokens_pdf = set(nome_up.replace('+', '').replace('-', ' ').split()) - IGNORAR

    melhor_score = 0
    melhor = None
    for qnome in quantum_nomes:
        q_up = qnome.upper()
        tokens_q = set(q_up.replace('+', '').replace('-', ' ').split()) - IGNORAR
        # Checa prefixo (ex: "ABSOLUT" ⊂ "ABSOLUTEPACE" não funciona; "ABSOLUTE" ≈ "ABSOLUTEPACE"?)
        score = sum(1 for t in tokens_pdf if any(w.startswith(t[:5]) for w in tokens_q))
        if score > melhor_score:
            melhor_score = score
            melhor = qnome

    return melhor if melhor_score >= 1 else None
