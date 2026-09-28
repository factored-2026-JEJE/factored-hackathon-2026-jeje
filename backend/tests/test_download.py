"""Download do dataset contra um servidor S3 real (versitygw no compose de testes).

O servidor valida assinatura SigV4, responde 403/404 como o S3 e guarda objetos de verdade:
nenhuma resposta do S3 é simulada.
"""

import os
import re
import time
import uuid

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError

from jeje.dados import manifesto
from jeje.dados.download import DownloadInvalido, baixar, separar_uri

ARQUIVOS = {
    "branches.csv": "﻿branch_id,city\nSUC-1,Bogotá\n",
    "complaints/year=2025/month=03/day=10/complaints_20250310.csv": "﻿id\nCMP-1\nCMP-2\n",
    "complaints/year=2025/month=03/day=11/complaints_20250311.csv": "﻿id\nCMP-3\n",
}


def cliente(segredo: str | None = None):
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_TEST_ENDPOINT"],
        aws_access_key_id=os.environ["S3_TEST_ACCESS_KEY"],
        aws_secret_access_key=segredo or os.environ["S3_TEST_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(retries={"max_attempts": 1}),
    )


@pytest.fixture
def publicado(tmp_path):
    """Bucket novo com os arquivos sob `data/` e o manifesto gerado dos originais."""
    s3 = cliente()
    limite = time.monotonic() + 15
    while True:  # o servidor sobe junto com o teste
        try:
            s3.list_buckets()
            break
        except EndpointConnectionError:
            if time.monotonic() > limite:
                raise
            time.sleep(0.2)
    bucket = f"teste-{uuid.uuid4().hex[:10]}"
    s3.create_bucket(Bucket=bucket)
    originais = tmp_path / "originais"
    for caminho, conteudo in ARQUIVOS.items():
        local = originais / caminho
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(conteudo, encoding="utf-8")
        s3.upload_file(str(local), bucket, f"data/{caminho}")
    esperado = manifesto.gerar(originais, ["branches", "complaints"])
    return s3, f"s3://{bucket}/data/", originais, esperado


def test_baixa_todos_os_arquivos_identicos_aos_originais(publicado, tmp_path):
    s3, uri, originais, esperado = publicado
    destino = tmp_path / "destino"
    resultado = baixar(s3, uri, destino, esperado, trabalhadores=4)
    assert (resultado.baixados, resultado.ja_presentes) == (3, 0)
    for caminho in ARQUIVOS:
        assert (destino / caminho).read_bytes() == (originais / caminho).read_bytes()


def test_segunda_execucao_nao_baixa_nada(publicado, tmp_path):
    s3, uri, _, esperado = publicado
    destino = tmp_path / "destino"
    baixar(s3, uri, destino, esperado, trabalhadores=4)
    resultado = baixar(s3, uri, destino, esperado, trabalhadores=4)
    assert (resultado.baixados, resultado.ja_presentes) == (0, 3)


def test_arquivo_local_corrompido_e_baixado_de_novo(publicado, tmp_path):
    s3, uri, originais, esperado = publicado
    destino = tmp_path / "destino"
    baixar(s3, uri, destino, esperado, trabalhadores=4)
    (destino / "branches.csv").write_text("corrompido", encoding="utf-8")
    resultado = baixar(s3, uri, destino, esperado, trabalhadores=4)
    assert resultado.baixados == 1
    assert (destino / "branches.csv").read_bytes() == (originais / "branches.csv").read_bytes()


def test_objeto_remoto_adulterado_com_mesmo_tamanho_e_recusado(publicado, tmp_path):
    s3, uri, _, esperado = publicado
    bucket = uri.removeprefix("s3://").split("/")[0]
    # "Bogotá" e "Bogot@!" têm 7 bytes: só o sha256 distingue.
    adulterado = ARQUIVOS["branches.csv"].replace("Bogotá", "Bogot@!")
    assert len(adulterado.encode()) == len(ARQUIVOS["branches.csv"].encode())
    s3.put_object(Bucket=bucket, Key="data/branches.csv", Body=adulterado.encode())
    destino = tmp_path / "destino"
    # Um trabalhador e o arquivo adulterado primeiro na fila: a falha não pode barrar os demais.
    erro = re.escape("branches.csv: objeto remoto difere do manifesto")
    with pytest.raises(DownloadInvalido, match=erro):
        baixar(s3, uri, destino, esperado, trabalhadores=1)
    assert not (destino / "branches.csv").exists()
    assert not (destino / "branches.csv.part").exists()
    assert all((destino / caminho).is_file() for caminho in ARQUIVOS if "complaints" in caminho)


def test_objeto_ausente_no_bucket_falha_nomeando_o_arquivo(publicado, tmp_path):
    s3, uri, _, esperado = publicado
    bucket = uri.removeprefix("s3://").split("/")[0]
    s3.delete_object(Bucket=bucket, Key="data/branches.csv")
    with pytest.raises(DownloadInvalido, match=re.escape("branches.csv: S3 respondeu 404")):
        baixar(s3, uri, tmp_path / "destino", esperado, trabalhadores=4)


def test_credencial_errada_falha_com_acesso_negado(publicado, tmp_path):
    _, uri, _, esperado = publicado
    with pytest.raises(DownloadInvalido, match="S3 respondeu 403"):
        baixar(cliente("segredo-errado"), uri, tmp_path / "destino", esperado, trabalhadores=4)


@pytest.mark.parametrize(
    ("uri", "esperado"),
    [
        ("s3://bucket/data/", ("bucket", "data/")),
        ("s3://bucket/data", ("bucket", "data/")),
        ("s3://bucket", ("bucket", "")),
    ],
)
def test_separar_uri(uri, esperado):
    assert separar_uri(uri) == esperado


@pytest.mark.parametrize("uri", ["bucket/data/", "https://bucket/data/", "s3:///data/"])
def test_uri_invalida_e_recusada(uri):
    with pytest.raises(DownloadInvalido, match="s3://bucket/prefixo/"):
        separar_uri(uri)
