import yaml
from dotenv import load_dotenv

load_dotenv()

def carregar_config(caminho: str = "config/config.yaml") -> dict:
    with open(caminho, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    config = carregar_config()
    competencia = config["competencia"]
    print(f"Gerando apresentação — competência: {competencia}")
    # TODO: chamar readers, processors e builders

if __name__ == "__main__":
    main()
