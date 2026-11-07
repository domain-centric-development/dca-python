# syntax=docker/dockerfile:1
# `docker build .` succeeds exactly when the tests pass, mypy --strict finds nothing and ruff's lint and format
# hold. Fully qualified image names, so the build works under Podman without a registry alias.
FROM docker.io/library/python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen \
 && uv run pytest -q \
 && uv run mypy \
 && uv run ruff check . \
 && uv run ruff format --check . \
 && uv build --all-packages -o /out \
 && cp dca-rules/src/dca_rules/rules.json /out/

FROM docker.io/library/debian:bookworm-slim
COPY --from=build /out /out
CMD ["ls", "-l", "/out"]
