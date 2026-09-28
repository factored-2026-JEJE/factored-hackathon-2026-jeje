"""Gera a fixture de dados (sintética, escrita à mão) usada pelo CI e pelas stacks de mutantes.

Mesmo formato dos CSV do desafio (BOM, cabeçalho completo da camada raw, partições diárias), com
poucos registros revisáveis. NÃO contém dados do dataset real. Rodar dentro do container de testes:

    docker compose -p jeje-test --profile test run --rm --no-deps --user "$(id -u):$(id -g)" \\
      -v ./data:/data test python /data/fixture/gerar.py
"""

import csv
import io
import shutil
from pathlib import Path

from jeje.dados import manifesto
from jeje.dados.raw import COLUNAS

RAIZ = Path(__file__).resolve().parent
DIA_1, DIA_2 = ("2025", "03", "10"), ("2025", "03", "11")

REGISTROS: dict[str, dict[tuple[str, str, str] | None, list[dict[str, str]]]] = {
    "branches": {None: [
        {"branch_id": "SUC-FX000001", "branch_code": "S9001", "branch_name": "Banco LATAM Bogotá Centro",
         "branch_type": "Premium", "city": "Bogotá", "state": "Cundinamarca", "country": "Colombia",
         "opening_time": "08:00:00", "closing_time": "16:00:00", "has_atms": "True", "atm_count": "3",
         "branch_status": "Active"},
        {"branch_id": "SUC-FX000002", "branch_code": "S9002", "branch_name": "Banco LATAM CDMX Reforma",
         "branch_type": "Express", "city": "Ciudad de México", "state": "CDMX", "country": "México",
         "opening_time": "09:00:00", "closing_time": "17:00:00", "has_atms": "False", "atm_count": "0",
         "branch_status": "Active"},
    ]},
    "customers": {None: [
        {"customer_id": "CLI-FX00000001", "document_number": "FX1000001", "document_type": "CC",
         "first_name": "Valentina", "last_name": "Gómez Ríos", "country": "Colombia", "city": "Bogotá",
         "segment": "Plus", "customer_status": "Active", "registration_branch_id": "SUC-FX000001",
         "detected_accent": "colombian"},
        {"customer_id": "CLI-FX00000002", "document_number": "FX1000002", "document_type": "DNI",
         "first_name": "Diego", "last_name": "Hernández López", "country": "México",
         "city": "Ciudad de México", "segment": "Basic", "customer_status": "Active",
         "registration_branch_id": "SUC-FX000002", "detected_accent": "mexican"},
    ]},
    "products": {None: [
        {"product_id": "PRD-FX00000001", "customer_id": "CLI-FX00000001", "product_type": "Tarjeta Crédito",
         "currency": "COP", "current_balance": "1250000.00", "credit_limit": "5000000.00",
         "opening_date": "2023-02-01", "product_status": "Active"},
        {"product_id": "PRD-FX00000002", "customer_id": "CLI-FX00000002", "product_type": "Cuenta Ahorro",
         "currency": "USD", "current_balance": "830.55", "opening_date": "2022-07-15",
         "product_status": "Active"},
    ]},
    "service_agents": {None: [
        {"agent_id": "AGT-FX000001", "employee_code": "E90001", "first_name": "Lucía", "last_name": "Pérez",
         "native_accent": "colombian", "agent_type": "Remote", "languages": "español,portugués",
         "agent_status": "Active"},
    ]},
    "marketing_campaigns": {None: [
        {"campaign_id": "CMP-FX0000001", "campaign_name": "CMP_RET_SAV_Mar2025_9001",
         "campaign_type": "Email", "campaign_objective": "Retention", "start_date": "2025-03-01",
         "end_date": "2025-03-31", "campaign_status": "Completed"},
    ]},
    "daily_exchange_rates": {None: [
        {"date": "2025-03-10", "source_currency": "COP", "target_currency": "USD",
         "exchange_rate": "0.000242", "source": "Central Bank"},
        {"date": "2025-03-10", "source_currency": "ARS", "target_currency": "USD",
         "exchange_rate": "0.000950", "source": "Reuters"},
    ]},
    "transactions": {
        DIA_1: [
            {"transaction_id": "TRX-FX0000000000000001", "transaction_date": "2025-03-10 14:09:12",
             "process_date": "2025-03-10", "product_id": "PRD-FX00000001", "customer_id": "CLI-FX00000001",
             "transaction_type": "Purchase", "amount": "189900.00", "currency": "COP", "channel": "POS",
             "merchant_name": "Almacenes Éxito", "transaction_country": "Colombia",
             "transaction_status": "Approved", "response_code": "00", "is_fraud": "False"},
            {"transaction_id": "TRX-FX0000000000000002", "transaction_date": "2025-03-10 18:45:03",
             "process_date": "2025-03-10", "product_id": "PRD-FX00000001", "customer_id": "CLI-FX00000001",
             "transaction_type": "Purchase", "amount": "1500000.00", "currency": "COP", "channel": "Web",
             "merchant_name": 'Viajes "El Cóndor", S.A.', "transaction_country": "Colombia",
             "transaction_status": "Declined", "response_code": "51", "is_fraud": "False"},
        ],
        DIA_2: [
            {"transaction_id": "TRX-FX0000000000000003", "transaction_date": "2025-03-11 09:02:44",
             "process_date": "2025-03-11", "product_id": "PRD-FX00000002", "customer_id": "CLI-FX00000002",
             "transaction_type": "Withdrawal", "amount": "200.00", "currency": "USD", "channel": "ATM",
             "transaction_country": "México", "transaction_status": "Pending", "response_code": "05",
             "is_fraud": "False"},
            # Defeito deliberado (Q-TIPO:amount): vírgula decimal não é um número válido.
            {"transaction_id": "TRX-FX0000000000000004", "transaction_date": "2025-03-11 11:30:00",
             "process_date": "2025-03-11", "product_id": "PRD-FX00000002", "customer_id": "CLI-FX00000002",
             "transaction_type": "Payment", "amount": "12,50", "currency": "USD", "channel": "App",
             "transaction_status": "Approved", "response_code": "00", "is_fraud": "False"},
        ],
    },
    "call_center_interactions": {DIA_1: [
        {"interaction_id": "INT-FX00000000000001", "interaction_date": "2025-03-10 19:10:00",
         "process_date": "2025-03-10", "customer_id": "CLI-FX00000001", "agent_id": "AGT-FX000001",
         "interaction_type": "Inbound Call", "channel": "Phone", "contact_reason": "Transaccional",
         "was_resolved": "False", "has_transcript": "True"},
    ]},
    "call_transcripts": {DIA_1: [
        {"transcript_id": "TRS-FX0000000000000001", "interaction_id": "INT-FX00000000000001",
         "process_date": "2025-03-10", "customer_id": "CLI-FX00000001", "agent_id": "AGT-FX000001",
         "full_text": "Cliente: Hola, mi compra fue rechazada.\nAgente: Reviso su tarjeta, un momento.",
         "detected_language": "es"},
    ]},
    "satisfaction_surveys": {DIA_2: [
        {"survey_id": "SRV-FX0000000000000001", "survey_date": "2025-03-11 08:00:00",
         "process_date": "2025-03-11", "interaction_id": "INT-FX00000000000001",
         "customer_id": "CLI-FX00000001", "survey_type": "CSAT", "main_score": "2",
         "open_comments": "No resolvieron mi problema."},
    ]},
    "complaints": {DIA_1: [
        {"complaint_id": "CMP-FX0000000000000001", "creation_date": "2025-03-10 20:34:30",
         "process_date": "2025-03-10", "customer_id": "CLI-FX00000001", "case_type": "Claim",
         "category": "Transactions", "subcategory": "Cargo no reconocido",
         "affected_product_id": "PRD-FX00000001", "claimed_amount": "189900.00", "currency": "COP",
         "status": "Open"},
        # Defeito deliberado (A-PROP, como ACH-016): produto de outro cliente; a curadoria anula.
        {"complaint_id": "CMP-FX0000000000000002", "creation_date": "2025-03-10 21:00:00",
         "process_date": "2025-03-10", "customer_id": "CLI-FX00000002", "case_type": "Complaint",
         "category": "Service", "affected_product_id": "PRD-FX00000001", "status": "Open"},
    ]},
    "campaign_sends": {DIA_1: [
        {"send_id": "SND-FX0000000000000001", "send_date": "2025-03-10 10:00:00",
         "process_date": "2025-03-10", "campaign_id": "CMP-FX0000001", "customer_id": "CLI-FX00000002",
         "send_channel": "Email", "send_status": "Sent", "was_delivered": "True"},
    ]},
}  # fmt: skip


def caminho(tabela: str, dia: tuple[str, str, str] | None) -> Path:
    if dia is None:
        return Path(f"{tabela}.csv")
    ano, mes, d = dia
    return Path(tabela, f"year={ano}", f"month={mes}", f"day={d}", f"{tabela}_{ano}{mes}{d}.csv")


def main() -> None:
    raw = RAIZ / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    for tabela, por_dia in REGISTROS.items():
        for dia, registros in por_dia.items():
            desconhecidas = {c for r in registros for c in r} - set(COLUNAS[tabela])
            if desconhecidas:
                raise SystemExit(f"{tabela}: colunas inexistentes {sorted(desconhecidas)}")
            buffer = io.StringIO()
            escritor = csv.writer(buffer, lineterminator="\n")
            escritor.writerow(COLUNAS[tabela])
            for r in registros:
                escritor.writerow([r.get(coluna, "") for coluna in COLUNAS[tabela]])
            destino = raw / caminho(tabela, dia)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text("﻿" + buffer.getvalue(), encoding="utf-8")
    manifesto.escrever(RAIZ / "manifesto", manifesto.gerar(raw, list(REGISTROS)))


if __name__ == "__main__":
    main()
