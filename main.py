import yaml
import os
from dotenv import load_dotenv
from pptx import Presentation

from src.builders.capa_sumario import build_capa, build_sumario
from src.builders.overview import build_overview
from src.readers.quantum_reader import ler_quantum

load_dotenv()

def carregar_config(caminho: str = "config/config.yaml") -> dict:
    with open(caminho, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    config = carregar_config()
    competencia = config["competencia"]
    print(f"\nGerando apresentacao - competencia: {competencia}\n")

    prs = Presentation(config["caminhos"]["template"])

    print("[ Capa ]")
    build_capa(prs.slides[0], competencia)

    print("[ Sumario ]")
    build_sumario(prs.slides[1], config["sumario"])

    print("[ Overview ]")
    cfg_ov = config["overview"]
    dados_quantum = ler_quantum(
        caminho=cfg_ov["arquivo_quantum"],
        mapeamento_nomes=cfg_ov.get("nomes_curtos", {}),
    )
    build_overview(
        slide=prs.slides[3],
        dados_quantum=dados_quantum,
        valor_fundos=cfg_ov["valor_fundos"],
        valor_direto=cfg_ov["valor_direto"],
    )

    pasta_saida = os.path.join(config["caminhos"]["output"], competencia)
    os.makedirs(pasta_saida, exist_ok=True)
    arquivo_saida = os.path.join(pasta_saida, f"comite_{competencia}.pptx")
    prs.save(arquivo_saida)
    print(f"\nApresentacao salva em: {arquivo_saida}")

if __name__ == "__main__":
    main()
