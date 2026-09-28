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

# Execução: só dependências de produção, usuário sem privilégio.
FROM base AS runtime
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "jeje.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Testes: inclui o grupo dev; o código também pode ser montado por cima em desenvolvimento.
FROM base AS test
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["pytest"]
