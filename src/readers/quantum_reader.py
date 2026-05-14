import pandas as pd
import os
import re

BENCHMARKS = {"CDI", "Dólar", "Ibovespa", "IPCA"}

def _nome_curto(nome_completo: str, mapeamento: dict) -> str:
    """Retorna o nome curto do fundo a partir do mapeamento, ou tenta extrair automaticamente."""
    if nome_completo in mapeamento:
        return mapeamento[nome_completo]
    # fallback: primeira palavra significativa
    partes = nome_completo.split()
    return partes[0] if partes else nome_completo

def ler_quantum(caminho: str, mapeamento_nomes: dict = None) -> dict:
    """
    Lê o export do Quantum Axis e retorna um dict com:
    - data_base: str (ex: "12/05/2026")
    - fundos: list de dicts [{nome, nome_curto, valor}]
    - aum_total: float
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo Quantum não encontrado: {caminho}")

    df = pd.read_excel(caminho, sheet_name="Quantum Axis", header=None)

    # Data base está na linha 2, coluna 1
    data_base = str(df.iloc[2, 1]).strip()

    # Dados dos fundos: linhas a partir da 3, até encontrar benchmark ou vazio
    fundos = []
    for i in range(3, len(df)):
        nome = df.iloc[i, 0]
        valor = df.iloc[i, 1]

        if pd.isna(nome) or str(nome).strip() in BENCHMARKS:
            break

        nome_str = str(nome).strip()
        valor_float = float(valor) if pd.notna(valor) else 0.0

        fundos.append({
            "nome": nome_str,
            "nome_curto": _nome_curto(nome_str, mapeamento_nomes or {}),
            "valor": valor_float,
        })

    aum_total = sum(f["valor"] for f in fundos)

    return {
        "data_base": data_base,
        "fundos": fundos,
        "aum_total": aum_total,
    }
