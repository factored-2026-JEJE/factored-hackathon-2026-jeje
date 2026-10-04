"""A base de avaliação (VAL-003, EXP-002): sintética, gerada pela validação no formato da fixture.

Parte da fixture do commit (`data/fixture/raw`, que fica como está) e acrescenta `CLIENTES` clientes
sintéticos, cada um com um cartão de crédito numerado (números fictícios), uma conta e o mesmo
conjunto de vagas de transação, para que qualquer modelo de cenário sirva a qualquer cliente:

- A1 a A4: compras aprovadas em dólar, de dia, com valor único (consulta, contestação, pré-caso);
- A5 e A6: duas compras aprovadas com o mesmo valor em comércios diferentes (ambiguidade);
- D1: recusada com código do catálogo (51, 14, 54 ou 05); D2: recusada com código fora dele (91);
- P1: pendente; H1: aprovada acima do limite do pré-caso;
- N1: compra noturna pelo app acima do limite noturno;
- T1: transferência acima do limite de segurança; O1: compra antiga, fora da janela;
- C1: compra em pesos sem valor em dólar; M1: pagamento sem comércio;
- Q1: registro com valor ilegível (vai para a quarentena);
- V1: compra revisada (o valor novo vale, o antigo some).

Os valores têm centavos próprios por vaga, então nenhum se repete no mesmo cliente (fora o par A5 e
A6). Nada vem da base do desafio. O manifesto é regenerado pelo próprio produto.
"""

import csv
import hashlib
import io
import shutil
from decimal import Decimal
from pathlib import Path

CLIENTES = 24
# Tipos de documento só do domínio do contrato do produto (CC, CE, DNI e Pasaporte): fora dele, o
# cliente vai para a quarentena e não vira persona (achado no piloto do EXP-002, 01/10).
PAISES = [
    ("Colombia", "Bogotá", "CC"),
    ("México", "Ciudad de México", "DNI"),
    ("Argentina", "Buenos Aires", "DNI"),
    ("Chile", "Santiago", "Pasaporte"),
    ("Perú", "Lima", "DNI"),
    ("Brasil", "São Paulo", "Pasaporte"),
]
NOMES = [
    "Camila",
    "Mateo",
    "Lucía",
    "Santiago",
    "Valeria",
    "Sebastián",
    "Isabella",
    "Tomás",
    "Mariana",
    "Joaquín",
    "Daniela",
    "Emilio",
    "Fernanda",
    "Gabriel",
    "Renata",
    "Nicolás",
    "Paula",
    "Andrés",
    "Juliana",
    "Martín",
    "Beatriz",
    "Rafael",
    "Larissa",
    "Thiago",
]
SOBRENOMES = [
    "Rojas",
    "Castro",
    "Morales",
    "Vargas",
    "Herrera",
    "Medina",
    "Ortiz",
    "Silva",
    "Navarro",
    "Cruz",
    "Reyes",
    "Flores",
    "Acosta",
    "Molina",
    "Suárez",
    "Ríos",
    "Peña",
    "Campos",
    "Vega",
    "Fuentes",
    "Souza",
    "Lima",
    "Costa",
    "Ramos",
]
COMERCIOS = [
    "Supermercado La Esquina",
    "Farmacia del Centro",
    "Librería Nueva Era",
    "Cine Estelar",
    "Restaurante El Fogón",
    "Ferretería Industrial",
    "Tienda Deportiva Andes",
    "Electrónica Pacífico",
    "Hotel Mirador",
    "Gasolinera Ruta 5",
    "Panadería Doña Rosa",
    "Óptica Visión",
    "Juguetería Arcoíris",
    "Zapatería Paso Firme",
    "Floristería Jardín",
    "Mascotas Felices",
    "Papelería Escolar",
    "Muebles Hogar",
    "Café Montaña",
    "Lavandería Burbujas",
]
CODIGOS_DO_CATALOGO = ["51", "14", "54", "05"]

# vaga: (valor em função do cliente i, moeda, status, código, data e hora, data de processamento,
# canal, tipo, produto, comércio?)
VAGAS = {
    "A1": (
        lambda i: Decimal(10 + 3 * i) + Decimal("0.45"),
        "USD",
        "Approved",
        "00",
        "2025-03-10 10:15:00",
        "2025-03-10",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "A2": (
        lambda i: Decimal(50 + 5 * i) + Decimal("0.20"),
        "USD",
        "Approved",
        "00",
        "2025-03-10 13:40:00",
        "2025-03-10",
        "Web",
        "Purchase",
        "cartao",
        True,
    ),
    "A3": (
        lambda i: Decimal(100 + 7 * i) + Decimal("0.75"),
        "USD",
        "Approved",
        "00",
        "2025-03-11 11:05:00",
        "2025-03-11",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "A4": (
        lambda i: Decimal(200 + 11 * i) + Decimal("0.10"),
        "USD",
        "Approved",
        "00",
        "2025-03-11 15:25:00",
        "2025-03-11",
        "App",
        "Purchase",
        "cartao",
        True,
    ),
    "A5": (
        lambda i: Decimal(31 + 2 * i) + Decimal("0.50"),
        "USD",
        "Approved",
        "00",
        "2025-03-10 12:00:00",
        "2025-03-10",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "A6": (
        lambda i: Decimal(31 + 2 * i) + Decimal("0.50"),
        "USD",
        "Approved",
        "00",
        "2025-03-11 12:30:00",
        "2025-03-11",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "D1": (
        lambda i: Decimal(75 + 3 * i) + Decimal("0.30"),
        "USD",
        "Declined",
        None,
        "2025-03-10 15:30:00",
        "2025-03-10",
        "Web",
        "Purchase",
        "cartao",
        True,
    ),
    "D2": (
        lambda i: Decimal(88 + 4 * i) + Decimal("0.60"),
        "USD",
        "Declined",
        "91",
        "2025-03-11 09:45:00",
        "2025-03-11",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "P1": (
        lambda i: Decimal(140 + 2 * i) + Decimal("0.05"),
        "USD",
        "Pending",
        "",
        "2025-03-11 08:15:00",
        "2025-03-11",
        "Web",
        "Purchase",
        "cartao",
        True,
    ),
    "H1": (
        lambda i: Decimal(6000 + 50 * i),
        "USD",
        "Approved",
        "00",
        "2025-03-10 11:00:00",
        "2025-03-10",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "N1": (
        lambda i: Decimal(1500 + 10 * i),
        "USD",
        "Approved",
        "00",
        "2025-03-10 23:15:00",
        "2025-03-10",
        "App",
        "Purchase",
        "cartao",
        True,
    ),
    "T1": (
        lambda i: Decimal(60000 + 100 * i),
        "USD",
        "Approved",
        "00",
        "2025-03-10 10:30:00",
        "2025-03-10",
        "App",
        "Transfer",
        "conta",
        False,
    ),
    "O1": (
        lambda i: Decimal(42 + i) + Decimal("0.80"),
        "USD",
        "Approved",
        "00",
        "2024-09-15 14:00:00",
        "2024-09-15",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "C1": (
        lambda i: Decimal(250000 + 1000 * i),
        "COP",
        "Approved",
        "00",
        "2025-03-10 13:20:00",
        "2025-03-10",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
    "M1": (
        lambda i: Decimal(17 + i) + Decimal("0.35"),
        "USD",
        "Approved",
        "00",
        "2025-03-11 10:10:00",
        "2025-03-11",
        "App",
        "Payment",
        "conta",
        False,
    ),
    "V1": (
        lambda i: Decimal(65 + i) + Decimal("0.40"),
        "USD",
        "Approved",
        "00",
        "2025-03-10 17:05:00",
        "2025-03-11",
        "POS",
        "Purchase",
        "cartao",
        True,
    ),
}


def valor_antigo_de_v1(i: int) -> Decimal:
    """A versão de 10/03, que a revisão de 11/03 substitui."""
    return Decimal(60 + i)


QUARENTENA = "9,99"  # valor com vírgula: não numérico na camada raw


def cliente_id(i: int) -> str:
    return f"CLI-AV{i:08d}"


def transacao_id(i: int, vaga: str) -> str:
    return f"TRX-AV{i:04d}{list(VAGAS).index(vaga) + 1 if vaga in VAGAS else 99:012d}"


def _comercio(i: int, vaga: str) -> str:
    """Comércio da vaga no cliente i: rotação pela lista, sem repetir dentro do cliente."""
    posicao = (list(VAGAS).index(vaga) if vaga in VAGAS else len(VAGAS)) + 3 * i
    return COMERCIOS[posicao % len(COMERCIOS)]


def _ler(caminho: Path) -> tuple[str, list[str], list[dict]]:
    texto = caminho.read_text(encoding="utf-8")
    bom = "﻿" if texto.startswith("﻿") else ""
    leitor = csv.DictReader(io.StringIO(texto.lstrip("﻿")))
    return bom, list(leitor.fieldnames), list(leitor)


def _gravar(caminho: Path, bom: str, colunas: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=colunas, lineterminator="\n", extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows([{c: linha.get(c, "") for c in colunas} for linha in linhas])
    caminho.write_text(bom + saida.getvalue(), encoding="utf-8")


def _particao(raiz: Path, dia: str) -> Path:
    ano, mes, d = dia.split("-")
    return (
        raiz
        / "transactions"
        / f"year={ano}"
        / f"month={mes}"
        / f"day={d}"
        / f"transactions_{ano}{mes}{d}.csv"
    )


def digest(raiz: Path) -> str:
    """O sha256 dos arquivos da base (caminho relativo e conteúdo, em ordem): os cenários foram
    materializados sobre esta base, e outra base deixa os cenários velhos."""
    resumo = hashlib.sha256()
    for arquivo in sorted(raiz.rglob("*.csv")):
        resumo.update(arquivo.relative_to(raiz).as_posix().encode() + b"\n")
        resumo.update(arquivo.read_bytes())
    return resumo.hexdigest()


def gerar(produto: Path, destino: Path) -> dict:
    """Escreve a base em `destino/raw` (com `destino/manifesto` vazio, para o produto gerar) e
    devolve o que criou."""
    origem = produto / "data" / "fixture" / "raw"
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(origem, destino / "raw")
    (destino / "manifesto").mkdir(parents=True)
    raiz = destino / "raw"

    bom, colunas, clientes = _ler(raiz / "customers.csv")
    filial = clientes[0].get("registration_branch_id", "")
    for i in range(1, CLIENTES + 1):
        pais, cidade, documento = PAISES[(i - 1) % len(PAISES)]
        clientes.append(
            {
                "customer_id": cliente_id(i),
                "document_number": f"AV{i:07d}",
                "document_type": documento,
                "first_name": NOMES[i - 1],
                "last_name": SOBRENOMES[i - 1],
                "city": cidade,
                "country": pais,
                "segment": "Plus" if i % 2 else "Basic",
                "customer_status": "Active",
                "registration_branch_id": filial,
            }
        )
    _gravar(raiz / "customers.csv", bom, colunas, clientes)

    bom, colunas, produtos = _ler(raiz / "products.csv")
    for i in range(1, CLIENTES + 1):
        produtos.append(
            {
                "product_id": f"PRD-AV{i:06d}01",
                "customer_id": cliente_id(i),
                "product_type": "Tarjeta Crédito",
                "product_number": f"000000000000{i:02d}{(37 * i) % 100:02d}",
                "currency": "USD",
                "current_balance": "0.00",
                "credit_limit": "8000.00",
                "opening_date": "2023-01-15",
                "product_status": "Active",
            }
        )
        produtos.append(
            {
                "product_id": f"PRD-AV{i:06d}02",
                "customer_id": cliente_id(i),
                "product_type": "Cuenta Ahorro",
                "currency": "USD",
                "current_balance": "1500.00",
                "opening_date": "2022-06-01",
                "product_status": "Active",
            }
        )
    _gravar(raiz / "products.csv", bom, colunas, produtos)

    arquivos = {}
    exemplo = next(iter(sorted((raiz / "transactions").rglob("*.csv"))))
    bom_t, colunas_t, _ = _ler(exemplo)
    for caminho in sorted((raiz / "transactions").rglob("*.csv")):
        arquivos[caminho] = _ler(caminho)[2]

    def acrescentar(dia: str, linha: dict) -> None:
        arquivos.setdefault(_particao(raiz, dia), []).append(linha)

    criadas = {}
    for i in range(1, CLIENTES + 1):
        for vaga, (
            valor,
            moeda,
            status,
            codigo,
            quando,
            processo,
            canal,
            tipo,
            produto_da_vaga,
            com_comercio,
        ) in VAGAS.items():
            codigo = (
                CODIGOS_DO_CATALOGO[(i - 1) % len(CODIGOS_DO_CATALOGO)]
                if codigo is None
                else codigo
            )
            linha = {
                "transaction_id": transacao_id(i, vaga),
                "transaction_date": quando,
                "process_date": processo,
                "product_id": f"PRD-AV{i:06d}{'01' if produto_da_vaga == 'cartao' else '02'}",
                "customer_id": cliente_id(i),
                "transaction_type": tipo,
                "amount": f"{valor(i):.2f}",
                "currency": moeda,
                "channel": canal,
                "merchant_name": _comercio(i, vaga) if com_comercio else "",
                "transaction_country": PAISES[(i - 1) % len(PAISES)][0],
                "transaction_status": status,
                "response_code": codigo,
                "is_fraud": "False",
            }
            if vaga == "V1":  # a versão antiga, de 10/03, que a revisão de 11/03 substitui
                acrescentar(
                    "2025-03-10",
                    {
                        **linha,
                        "process_date": "2025-03-10",
                        "amount": f"{valor_antigo_de_v1(i):.2f}",
                    },
                )
            acrescentar(processo, linha)
            criadas[linha["transaction_id"]] = vaga
        quarentena = {
            "transaction_id": transacao_id(i, "Q1"),
            "transaction_date": "2025-03-10 16:00:00",
            "process_date": "2025-03-10",
            "product_id": f"PRD-AV{i:06d}01",
            "customer_id": cliente_id(i),
            "transaction_type": "Purchase",
            "amount": QUARENTENA,
            "currency": "USD",
            "channel": "POS",
            "merchant_name": _comercio(i, "Q1"),
            "transaction_country": PAISES[(i - 1) % len(PAISES)][0],
            "transaction_status": "Approved",
            "response_code": "00",
            "is_fraud": "False",
        }
        acrescentar("2025-03-10", quarentena)
        criadas[quarentena["transaction_id"]] = "Q1"
    for caminho, linhas in arquivos.items():
        _gravar(caminho, bom_t, colunas_t, linhas)
    return {"clientes": [cliente_id(i) for i in range(1, CLIENTES + 1)], "transacoes": len(criadas)}
