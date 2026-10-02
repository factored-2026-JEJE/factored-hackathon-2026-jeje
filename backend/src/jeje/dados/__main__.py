"""CLI do pipeline de dados.

python -m jeje.dados preparar    # seed do compose: baixa o que falta e carrega (idempotente)
python -m jeje.dados manifesto   # regenera o manifesto a partir dos arquivos locais
"""

import sys

import boto3
from botocore.config import Config
from sqlalchemy import text

from jeje import sessao
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


def provisionar(settings: Settings, config: ConfigDados) -> None:
    engine = create_db_engine(settings)
    try:
        with engine.begin() as conexao:
            personas = sessao.provisionar_personas(conexao, config.personas_quantidade)
    finally:
        engine.dispose()
    print(f"[dados] {len(personas)} personas de demonstração provisionadas", flush=True)


def preparar(settings: Settings, config: ConfigDados) -> None:
    carregar_se_preciso(settings, config)
    provisionar(settings, config)


# O que faz uma versão nova ser recusada: o download, o manifesto ou a carga (contrato violado,
# coluna nova). Com uma anterior no banco, nada disso derruba o serviço.
RECUSAS = (DownloadInvalido, CargaInvalida, manifesto.ManifestoInvalido)


def registrar_recusa(settings: Settings, versao: str, motivo: str) -> None:
    engine = create_db_engine(settings)
    try:
        with engine.begin() as conexao:
            conexao.execute(
                text(
                    "update meta.dataset_version set recusada_versao = :versao, "
                    "recusada_motivo = :motivo, recusada_em = now()"
                ),
                {"versao": versao, "motivo": motivo},
            )
    finally:
        engine.dispose()


def carregar_se_preciso(settings: Settings, config: ConfigDados) -> None:
    """Carrega a versão dos manifestos, se for outra. Recusada com uma anterior no banco (ACH-112),
    a anterior continua valendo e a recusa fica gravada; sem anterior, o erro sobe."""
    anterior = versao_no_banco(settings)
    versao = "?"
    try:
        versao = manifesto.versao(config.dataset_manifest_dir, config.dataset_tables)
        _carregar(settings, config, versao, anterior)
    except RECUSAS as erro:
        if anterior is None:
            raise
        registrar_recusa(settings, versao, str(erro))
        print(
            f"[dados] versão {versao[:12]} recusada; segue a {anterior[0][:12]}: {erro}",
            file=sys.stderr,
            flush=True,
        )


def _carregar(
    settings: Settings, config: ConfigDados, versao: str, anterior: tuple[str, str] | None
) -> None:
    tabelas = config.dataset_tables
    pipeline = versao_pipeline()
    if anterior == (versao, pipeline):
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
