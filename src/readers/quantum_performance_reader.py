import pandas as pd
import os

BENCHMARKS = ["CDI", "Dólar", "Ibovespa", "IPCA"]

def ler_performance(caminho: str) -> dict:
    """
    Lê o export de performance do Quantum Axis.
    Retorna dict com fundos e benchmarks, retornos em decimal.
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    df = pd.read_excel(caminho, sheet_name="Quantum Axis", header=None)

    fundos = {}
    benchmarks = {}

    for i in range(3, len(df)):
        nome = df.iloc[i, 0]
        if pd.isna(nome):
            break

        nome_str = str(nome).strip()
        vals = {
            "mes":  _val(df, i, 1),
            "ano":  _val(df, i, 2),
            "m12":  _val(df, i, 3),
            "m24":  _val(df, i, 4),
        }

        if nome_str in BENCHMARKS:
            benchmarks[nome_str] = vals
        else:
            fundos[nome_str] = vals

    return {"fundos": fundos, "benchmarks": benchmarks}

def _val(df, row, col):
    v = df.iloc[row, col]
    return float(v) if pd.notna(v) else None
