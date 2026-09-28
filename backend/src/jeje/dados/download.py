"""Download idempotente do dataset a partir do S3 dos organizadores, conferido pelo manifesto.

Baixa em paralelo só o que falta ou diverge. Cada arquivo chega primeiro como `.part` e só recebe
o nome final quando tamanho e sha256 batem com o manifesto versionado: a versão dos dados é a do
Git, não a do bucket, e objeto remoto diferente do manifesto é erro. Todos os erros são reunidos
numa única falha, com o arquivo e a resposta do S3.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from jeje.dados.manifesto import Arquivo, sha256_de


class DownloadInvalido(Exception):
    """Algum arquivo não pôde ser baixado íntegro; os demais ficam no destino."""


@dataclass(frozen=True)
class ResultadoDownload:
    baixados: int
    ja_presentes: int


def separar_uri(uri: str) -> tuple[str, str]:
    """`s3://bucket/prefixo/` → (`bucket`, `prefixo/`); o prefixo pode ser vazio."""
    bucket, _, prefixo = uri.removeprefix("s3://").partition("/")
    if not uri.startswith("s3://") or not bucket:
        raise DownloadInvalido("DATASET_S3_URI deve ter a forma s3://bucket/prefixo/")
    if prefixo and not prefixo.endswith("/"):
        prefixo += "/"
    return bucket, prefixo


def local_confere(caminho: Path, esperado: Arquivo) -> bool:
    return (
        caminho.is_file()
        and caminho.stat().st_size == esperado.bytes
        and sha256_de(caminho) == esperado.sha256
    )


def baixar_arquivo(cliente, bucket: str, prefixo: str, destino: Path, esperado: Arquivo) -> bool:
    """Garante o arquivo íntegro em `destino`; devolve True se precisou baixar."""
    alvo = destino / esperado.caminho
    if local_confere(alvo, esperado):
        return False
    alvo.parent.mkdir(parents=True, exist_ok=True)
    parcial = alvo.with_name(alvo.name + ".part")
    try:
        cliente.download_file(bucket, prefixo + esperado.caminho, str(parcial))
    except ClientError as erro:
        parcial.unlink(missing_ok=True)
        codigo = erro.response.get("Error", {}).get("Code", "?")
        raise DownloadInvalido(f"{esperado.caminho}: S3 respondeu {codigo}") from erro
    except BotoCoreError as erro:
        parcial.unlink(missing_ok=True)
        raise DownloadInvalido(f"{esperado.caminho}: {erro}") from erro
    if not local_confere(parcial, esperado):
        parcial.unlink(missing_ok=True)
        raise DownloadInvalido(f"{esperado.caminho}: objeto remoto difere do manifesto")
    parcial.replace(alvo)
    return True


def baixar(
    cliente,
    uri: str,
    destino: Path,
    manifesto: dict[str, list[Arquivo]],
    trabalhadores: int,
) -> ResultadoDownload:
    bucket, prefixo = separar_uri(uri)
    arquivos = [arquivo for arquivos in manifesto.values() for arquivo in arquivos]
    baixados, erros = 0, []
    with ThreadPoolExecutor(max_workers=trabalhadores) as executor:
        futuros = [
            executor.submit(baixar_arquivo, cliente, bucket, prefixo, destino, arquivo)
            for arquivo in arquivos
        ]
        for futuro in as_completed(futuros):
            try:
                baixados += futuro.result()
            except DownloadInvalido as erro:
                erros.append(str(erro))
    if erros:
        raise DownloadInvalido(f"{len(erros)} arquivo(s) com falha:\n" + "\n".join(sorted(erros)))
    return ResultadoDownload(baixados=baixados, ja_presentes=len(arquivos) - baixados)
