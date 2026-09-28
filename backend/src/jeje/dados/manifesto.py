"""Manifesto versionado do dataset: um CSV por tabela com arquivo, bytes, sha256 e registros.

É o que fixa a versão dos dados no Git: qualquer máquina baixa os mesmos arquivos, confere os
hashes e carrega o mesmo banco. A versão é o sha256 do conteúdo dos manifestos das tabelas
selecionadas, logo muda se um arquivo, uma contagem ou a seleção de tabelas mudar.
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

CAMPOS = ("arquivo", "bytes", "sha256", "registros")


class ManifestoInvalido(Exception):
    """Manifesto ausente ou inconsistente para as tabelas pedidas."""


@dataclass(frozen=True)
class Arquivo:
    caminho: str  # relativo ao diretório raw, separador "/"
    bytes: int
    sha256: str
    registros: int  # registros CSV (sem o cabeçalho); campos com quebra de linha contam uma vez


def tabela_do_caminho(caminho: str) -> str:
    return caminho.split("/", 1)[0].removesuffix(".csv")


def sha256_de(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def contar_registros(caminho: Path) -> int:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return sum(1 for _ in csv.reader(arquivo)) - 1


def arquivos_da_tabela(diretorio_raw: Path, tabela: str) -> list[Path]:
    unico = diretorio_raw / f"{tabela}.csv"
    particionados = sorted((diretorio_raw / tabela).rglob("*.csv"))
    return ([unico] if unico.is_file() else []) + particionados


def gerar(diretorio_raw: Path, tabelas: list[str]) -> dict[str, list[Arquivo]]:
    manifesto = {}
    for tabela in tabelas:
        caminhos = arquivos_da_tabela(diretorio_raw, tabela)
        if not caminhos:
            raise ManifestoInvalido(f"nenhum arquivo da tabela {tabela} em {diretorio_raw}")
        manifesto[tabela] = [
            Arquivo(
                caminho=caminho.relative_to(diretorio_raw).as_posix(),
                bytes=caminho.stat().st_size,
                sha256=sha256_de(caminho),
                registros=contar_registros(caminho),
            )
            for caminho in caminhos
        ]
    return manifesto


def escrever(diretorio_manifesto: Path, manifesto: dict[str, list[Arquivo]]) -> None:
    diretorio_manifesto.mkdir(parents=True, exist_ok=True)
    for tabela, arquivos in manifesto.items():
        with (diretorio_manifesto / f"{tabela}.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.writer(f, lineterminator="\n")
            escritor.writerow(CAMPOS)
            for a in arquivos:
                escritor.writerow((a.caminho, a.bytes, a.sha256, a.registros))


def ler(diretorio_manifesto: Path, tabelas: list[str]) -> dict[str, list[Arquivo]]:
    manifesto = {}
    for tabela in tabelas:
        caminho = diretorio_manifesto / f"{tabela}.csv"
        if not caminho.is_file():
            raise ManifestoInvalido(f"manifesto de {tabela} ausente em {diretorio_manifesto}")
        with caminho.open(encoding="utf-8", newline="") as f:
            leitor = csv.DictReader(f)
            if tuple(leitor.fieldnames or ()) != CAMPOS:
                raise ManifestoInvalido(f"cabeçalho inválido no manifesto de {tabela}")
            manifesto[tabela] = [
                Arquivo(
                    caminho=linha["arquivo"],
                    bytes=int(linha["bytes"]),
                    sha256=linha["sha256"],
                    registros=int(linha["registros"]),
                )
                for linha in leitor
            ]
        if not manifesto[tabela]:
            raise ManifestoInvalido(f"manifesto da tabela {tabela} não lista arquivos")
    return manifesto


def versao(diretorio_manifesto: Path, tabelas: list[str]) -> str:
    """sha256 dos manifestos das tabelas selecionadas (ordem alfabética, nome incluso)."""
    ler(diretorio_manifesto, tabelas)  # valida antes de versionar
    resumo = hashlib.sha256()
    for tabela in sorted(tabelas):
        resumo.update(f"{tabela}\n".encode())
        resumo.update((diretorio_manifesto / f"{tabela}.csv").read_bytes())
    return resumo.hexdigest()
