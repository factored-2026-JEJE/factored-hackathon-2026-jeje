"""Arquivos remotos fixados por URL (com commit), tamanho e sha256, como o manifesto do dataset:
qualquer máquina baixa os mesmos bytes, e objeto remoto diferente é erro."""

import urllib.request
from dataclasses import dataclass
from pathlib import Path

from jeje.dados.manifesto import sha256_de


class FonteInvalida(Exception):
    """Arquivo ausente, corrompido ou diferente do fixado."""


@dataclass(frozen=True)
class Arquivo:
    nome: str  # caminho relativo dentro do destino
    url: str
    bytes: int
    sha256: str


def confere(caminho: Path, arquivo: Arquivo) -> bool:
    return (
        caminho.is_file()
        and caminho.stat().st_size == arquivo.bytes
        and sha256_de(caminho) == arquivo.sha256
    )


def baixar(destino: Path, arquivos: tuple[Arquivo, ...], timeout_s: int = 120) -> int:
    """Garante cada arquivo íntegro em `destino`; devolve quantos precisou baixar."""
    baixados = 0
    for arquivo in arquivos:
        alvo = destino / arquivo.nome
        if confere(alvo, arquivo):
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        parcial = alvo.with_name(alvo.name + ".part")
        try:
            with (
                urllib.request.urlopen(arquivo.url, timeout=timeout_s) as resposta,
                parcial.open("wb") as saida,
            ):
                for bloco in iter(lambda: resposta.read(1 << 20), b""):
                    saida.write(bloco)
        except OSError as erro:
            parcial.unlink(missing_ok=True)
            raise FonteInvalida(f"{arquivo.nome}: falha ao baixar {arquivo.url}: {erro}") from erro
        if not confere(parcial, arquivo):
            parcial.unlink(missing_ok=True)
            raise FonteInvalida(f"{arquivo.nome}: conteúdo remoto difere do fixado")
        parcial.replace(alvo)
        baixados += 1
    return baixados


def exigir(destino: Path, arquivo: Arquivo) -> Path:
    """Caminho do arquivo já baixado e íntegro; senão, erro (nunca lê bytes não conferidos)."""
    caminho = destino / arquivo.nome
    if not confere(caminho, arquivo):
        raise FonteInvalida(f"{arquivo.nome}: ausente ou diferente do fixado em {destino}")
    return caminho
