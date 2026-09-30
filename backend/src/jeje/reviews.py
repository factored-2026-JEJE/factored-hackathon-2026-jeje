"""Reviews das conversas de teste: alguém do time conversa com o assistente como cliente e depois
avalia a conversa (nota, se resolveu, o que deu errado).

A review fica sempre no banco, ligada à conversa (e por ela aos turnos). Com repositório e token
configurados, vira também uma Issue no GitHub, com a transcrição, para o time discutir e corrigir;
falha no GitHub não perde a review (fica sem `issue_url`, e o log diz por quê).
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from sqlalchemy import Connection, text

from jeje.conversa import historico

log = logging.getLogger("jeje.reviews")

ETIQUETA = "review-teste"
MARCA_DOS_DADOS = "<!-- jeje-review"
RESOLVEU_ROTULO = {"sim": "resolveu", "parcial": "resolveu em parte", "nao": "não resolveu"}
TIMEOUT_GITHUB_S = 10


@dataclass(frozen=True)
class Review:
    avaliador: str
    nota: int
    resolveu: str
    comentario: str


def testadores(configurados: str) -> list[str]:
    """Quem pode avaliar (logins do GitHub, separados por vírgula na configuração)."""
    return [t.strip() for t in configurados.split(",") if t.strip()]


def gravar(conexao: Connection, customer_id: str, conversa_id: str, review: Review) -> dict:
    """Grava a review da conversa do dono e devolve o que a Issue precisa (conversa e turnos).
    Conversa de outro cliente é igual a inexistente (ConversaNaoEncontrada, como no histórico)."""
    conversa, turnos = historico(conexao, customer_id, conversa_id)
    review_id = conexao.execute(
        text(
            "INSERT INTO app.reviews (conversa_id, avaliador, nota, resolveu, comentario)"
            " VALUES (:conversa, :avaliador, :nota, :resolveu, :comentario) RETURNING id"
        ),
        {"conversa": conversa_id, **review.__dict__},
    ).scalar_one()
    return {"review_id": review_id, "conversa": conversa, "turnos": turnos}


def anotar_issue(conexao: Connection, review_id: int, url: str) -> None:
    conexao.execute(
        text("UPDATE app.reviews SET issue_url = :url WHERE id = :id"),
        {"url": url, "id": review_id},
    )


def titulo(review: Review, turnos: list[dict]) -> str:
    primeira = turnos[0]["mensagem"] if turnos else "(conversa sem mensagens)"
    resumo = primeira if len(primeira) <= 60 else primeira[:57] + "..."
    return f"[review {review.nota}/5, {RESOLVEU_ROTULO[review.resolveu]}] {resumo}"


def corpo(review: Review, customer_id: str, conversa: dict, turnos: list[dict]) -> str:
    """Markdown da Issue: a avaliação e a conversa inteira, turno a turno, com regra e estado."""
    linhas = [
        f"**Avaliador:** @{review.avaliador}  ",
        f"**Nota:** {review.nota}/5 · **{RESOLVEU_ROTULO[review.resolveu]}**  ",
        f"**Cliente:** `{customer_id}` · **Conversa:** `{conversa['id']}` · "
        f"**Idioma:** {conversa['idioma']} · **Estado final:** `{conversa['estado']}`",
        "",
        "### O que deu errado / como deveria ser",
        "",
        review.comentario or "_(sem comentário)_",
        "",
        "### Conversa",
        "",
    ]
    for t in turnos:
        linhas += [
            f"**{t['numero']}. Cliente:** {t['mensagem']}",
            "",
            f"> {t['resposta'].replace(chr(10), chr(10) + '> ')}",
            "",
            f"<sub>`{t['regra']}` · `{t['acao']}` → `{t['estado']}`</sub>",
            "",
        ]
    # A mesma conversa para máquina (invisível na Issue): o importador da QA refaz a conversa daqui.
    dados = {
        "avaliador": review.avaliador,
        "nota": review.nota,
        "resolveu": review.resolveu,
        "comentario": review.comentario,
        "cliente": customer_id,
        "conversa": conversa["id"],
        "idioma": conversa["idioma"],
        "turnos": [
            {k: t[k] for k in ("numero", "mensagem", "resposta", "regra", "acao", "estado")}
            for t in turnos
        ],
    }
    # ">" escapado no JSON: nenhuma mensagem consegue fechar o comentário ("-->") antes da hora.
    json_seguro = json.dumps(dados, ensure_ascii=False).replace(">", "\\u003e")
    linhas += [MARCA_DOS_DADOS, json_seguro, "-->"]
    return "\n".join(linhas)


def publicar(api_url: str, repo: str, token: str, titulo_: str, corpo_: str) -> str | None:
    """Cria a Issue e devolve a URL dela; qualquer falha do GitHub vira None (e um aviso no log)."""
    pedido = urllib.request.Request(
        f"{api_url.rstrip('/')}/repos/{repo}/issues",
        data=json.dumps({"title": titulo_, "body": corpo_, "labels": [ETIQUETA]}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_GITHUB_S) as resposta:
            return json.loads(resposta.read())["html_url"]
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as erro:
        # Fronteira externa: a review já está no banco; só a Issue fica por fazer.
        log.warning("issue nao criada repo=%s erro=%s", repo, type(erro).__name__)
        return None


def dados_da_fixture(conexao: Connection) -> bool:
    """A review só vira Issue quando os dados carregados são a fixture sintética: com a base real, o
    cliente e a transcrição iriam para o GitHub (ACH-038). Sem dados carregados, também não."""
    fonte = conexao.execute(text("SELECT source FROM meta.dataset_version")).scalar_one_or_none()
    return fonte == "fixture"


def pendentes(conexao: Connection) -> list[dict]:
    """Reviews ainda sem Issue (GitHub fora do ar ou sem token quando foram feitas)."""
    consulta = (
        "SELECT r.id, r.conversa_id, r.avaliador, r.nota, r.resolveu, r.comentario, c.customer_id"
        " FROM app.reviews r JOIN app.conversas c ON c.id = r.conversa_id"
        " WHERE r.issue_url IS NULL ORDER BY r.id"
    )
    return [dict(linha) for linha in conexao.execute(text(consulta)).mappings()]


def publicar_pendentes(engine, api_url: str, repo: str, token: str) -> tuple[int, int]:
    """Publica as reviews pendentes como Issues; devolve (publicadas, que continuam pendentes)."""
    publicadas = falharam = 0
    with engine.connect() as conexao:
        lista = pendentes(conexao)
        if not dados_da_fixture(conexao):
            log.warning("issues nao criadas: os dados carregados nao sao a fixture (ACH-038)")
            return 0, len(lista)
    for p in lista:
        review = Review(p["avaliador"], p["nota"], p["resolveu"], p["comentario"])
        with engine.connect() as conexao:
            conversa, turnos = historico(conexao, p["customer_id"], p["conversa_id"])
        url = publicar(
            api_url, repo, token, titulo(review, turnos),
            corpo(review, p["customer_id"], conversa, turnos),
        )  # fmt: skip
        if url is None:
            falharam += 1
            continue
        with engine.begin() as conexao:
            anotar_issue(conexao, p["id"], url)
        publicadas += 1
    return publicadas, falharam


if __name__ == "__main__":
    from jeje.config import Settings
    from jeje.db import create_db_engine

    config = Settings()
    if not (config.reviews_repo and config.github_token):
        raise SystemExit("Sem REVIEWS_REPO ou GITHUB_TOKEN: nada a publicar.")
    feitas, restam = publicar_pendentes(
        create_db_engine(config), config.github_api_url, config.reviews_repo, config.github_token
    )
    print(f"{feitas} reviews publicadas como Issue; {restam} continuam pendentes.")
