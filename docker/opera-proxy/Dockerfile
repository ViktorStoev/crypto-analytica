FROM golang:1.26-alpine AS builder

ARG OPERA_PROXY_VERSION=v1.22.0

RUN apk add --no-cache \
    git \
    ca-certificates

WORKDIR /src

RUN git clone \
    --depth 1 \
    --branch "${OPERA_PROXY_VERSION}" \
    https://github.com/Alexey71/opera-proxy.git \
    .

RUN CGO_ENABLED=0 \
    GOOS=linux \
    go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/opera-proxy \
    .


FROM alpine:3.22

RUN apk add --no-cache ca-certificates \
    && addgroup -S proxy \
    && adduser -S -G proxy proxy

COPY --from=builder \
    /out/opera-proxy \
    /usr/local/bin/opera-proxy

USER proxy

EXPOSE 18080

ENTRYPOINT ["/usr/local/bin/opera-proxy"]