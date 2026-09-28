"""CLI do pipeline de dados.

python -m jeje.dados preparar    # seed do compose: baixa o que falta e carrega (idempotente)
python -m jeje.dados manifesto   # regenera o manifesto a partir dos arquivos locais
"""

import sys

import boto3
from botocore.config import Config

from jeje.config import Settings
from jeje.dados import manifesto
from jeje.dados.carga import CargaInvalida, carregar, versao_carregada
from jeje.dados.config import ConfigDados
from jeje.dados.download import DownloadInvalido, baixar
from jeje.dados.versao import versao_pipeline
from jeje.db import create_db_engine


def versao_no_banco(settings: Settings) -> tuple[str, str] | None:
    engine = create_db_engine(settings)
    try:
        with engine.connect() as conexao:
            return versao_carregada(conexao)
    finally:
        engine.dispose()


def cliente_s3(config: ConfigDados):
    return boto3.client(
        "s3",
        endpoint_url=config.dataset_s3_endpoint or None,
        config=Config(
            retries={"max_attempts": 5, "mode": "standard"},
            max_pool_connections=config.dataset_download_workers,
        ),
    )


def preparar(settings: Settings, config: ConfigDados) -> None:
    tabelas = config.dataset_tables
    versao = manifesto.versao(config.dataset_manifest_dir, tabelas)
    pipeline = versao_pipeline()
    if versao_no_banco(settings) == (versao, pipeline):
        print(f"[dados] versão {versao[:12]} já carregada; nada a fazer", flush=True)
        return
    if config.dataset_source == "s3":
        esperado = manifesto.ler(config.dataset_manifest_dir, tabelas)
        resultado = baixar(
            cliente_s3(config),
            config.dataset_s3_uri,
            config.dataset_raw_dir,
            esperado,
            config.dataset_download_workers,
        )
        print(
            f"[dados] download: {resultado.baixados} baixados, "
            f"{resultado.ja_presentes} já presentes",
            flush=True,
        )
    carga = carregar(
        settings,
        config.dataset_raw_dir,
        config.dataset_manifest_dir,
        tabelas,
        config.dataset_source,
        pipeline,
    )
    print(f"[dados] versão {carga.versao[:12]} carregada ({config.dataset_source})", flush=True)


def main(argv: list[str]) -> int:
    comando = argv[1] if len(argv) > 1 else ""
    config = ConfigDados()
    try:
        if comando == "preparar":
            preparar(Settings(), config)
        elif comando == "manifesto":
            gerado = manifesto.gerar(config.dataset_raw_dir, config.dataset_tables)
            manifesto.escrever(config.dataset_manifest_dir, gerado)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (DownloadInvalido, CargaInvalida, manifesto.ManifestoInvalido) as erro:
        print(f"[dados] ERRO: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
