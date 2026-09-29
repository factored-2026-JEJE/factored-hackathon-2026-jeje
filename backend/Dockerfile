# Imagem do backend. Base fixada por digest; dependências exatas do uv.lock (--frozen).
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.12.19
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./

# Dependências de produção com o leitor (torch só-CPU, ~1,4 GB): uma camada só, comum ao treino e
# à execução, para o torch não ser instalado (nem guardado) duas vezes. Sem o cache do uv na imagem
# (seriam mais ~1 GB de pacotes baixados).
FROM base AS dependencias
RUN uv sync --frozen --no-dev --group leitor --no-install-project --no-cache

# Leitor e5: baixa o corpus e os pesos fixados por commit e sha256 e treina (CPU, ~11 min).
# Copia só o código que o treino usa, para o cache do Docker não retreinar a cada mudança no resto
# do backend. Saída em /opt/modelos: os pesos do e5 e o artefato do classificador.
FROM dependencias AS modelo
RUN uv sync --frozen --no-dev --group leitor --group modelo --no-install-project --no-cache
COPY src/jeje/__init__.py ./src/jeje/
COPY src/jeje/dados/__init__.py src/jeje/dados/manifesto.py ./src/jeje/dados/
COPY src/jeje/leitor ./src/jeje/leitor
RUN PYTHONPATH=src python -m jeje.leitor treinar /tmp/corpus /opt/modelos/e5 \
        /opt/modelos/leitor.joblib \
    && rm -rf /tmp/corpus

# Execução: dependências de produção e o leitor treinado, usuário sem privilégio. O leitor só lê
# arquivos locais conferidos: nada é baixado do Hugging Face em execução.
FROM dependencias AS runtime
ENV HF_HUB_OFFLINE=1 \
    HF_HOME=/tmp/huggingface
COPY --from=modelo /opt/modelos /opt/modelos
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev --group leitor --no-editable --no-cache \
    && useradd --system --uid 10001 app \
    && mkdir -p /dataset && chown app /dataset
USER app
EXPOSE 8000
# Acesso registrado pela própria app (jeje.logs: id da requisição, rota-modelo e duração).
CMD ["uvicorn", "jeje.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# Testes: inclui o grupo dev, sem o leitor (os testes usam um codificador falso); o código também
# pode ser montado por cima em desenvolvimento.
FROM base AS test
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["pytest"]
