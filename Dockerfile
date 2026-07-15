FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
       ca-certificates cmake g++ make git libglpk-dev coinor-libcbc-dev libzip-dev \
       libprotobuf-dev protobuf-compiler python3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src/loom
COPY . .
RUN git submodule update --init --recursive
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --parallel "$(nproc)" \
    && cmake --install build --prefix /opt/loom

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
       ca-certificates python3 libglpk40 coinor-cbc libzip4t64 libprotobuf32t64 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/loom /usr/local
COPY wrapper/loom_map /opt/loom-wrapper/loom_map
COPY scripts/loom-map /usr/local/bin/loom-map
COPY scripts/loom-entrypoint /usr/local/bin/loom-entrypoint
ENV PYTHONPATH=/opt/loom-wrapper
WORKDIR /data
ENTRYPOINT ["loom-entrypoint"]
CMD ["--help"]
