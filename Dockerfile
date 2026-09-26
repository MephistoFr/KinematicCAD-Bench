# Supply an immutable digest through BASE_IMAGE for published runs.
ARG BASE_IMAGE=python:3.11.15-slim-bookworm
FROM ${BASE_IMAGE} AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONHASHSEED=0 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 XDG_CACHE_HOME=/tmp/cache TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglu1-mesa libglib2.0-0 libgomp1 libxrender1 libxext6 libsm6 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /opt/kcb/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/kcb/requirements.lock
WORKDIR /work
USER 10001:10001

FROM dependencies AS candidate
# The candidate image deliberately has neither the judge nor solved references.
COPY src/kinematiccad/__init__.py src/kinematiccad/sdk.py src/kinematiccad/schema.py \
     src/kinematiccad/io.py src/kinematiccad/process.py src/kinematiccad/transport.py \
     src/kinematiccad/worker.py /usr/local/lib/python3.11/site-packages/kinematiccad/
CMD ["python", "-I", "-m", "kinematiccad.worker", "candidate", "--input", "/input", "--archive"]

FROM dependencies AS judge
COPY src/kinematiccad /usr/local/lib/python3.11/site-packages/kinematiccad
LABEL org.opencontainers.image.title="KinematicCAD-Bench" \
      org.opencontainers.image.version="0.1.0" org.opencontainers.image.licenses="MIT"
CMD ["python", "-I", "-m", "kinematiccad.worker", "judge", "--input", "/input", "--archive"]

