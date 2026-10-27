# Security rebuild of upstream Caddy's standard module set; no plugins.
FROM golang:1.26.10-alpine3.23@sha256:34414731924cf2263160f0021f5cf6e1807382d85248f7cb419d4187b96d5e43 AS builder
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify
COPY main.go ./
RUN go build -mod=readonly -trimpath -ldflags='-s -w' -o /out/caddy . \
    && go version -m /out/caddy > /out/build-info.txt \
    && go list -mod=readonly -deps . > /out/packages.txt
# GO-2026-5932 affects OpenPGP, not the other x/crypto packages Caddy uses.
# Fail future builds if an affected package ever enters the compiled graph.
RUN ! grep -q '^golang.org/x/crypto/openpgp' /out/packages.txt

# Retain upstream entrypoint, paths, CA store, health tools and volume behavior.
FROM caddy:2.11.7-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f
RUN apk add --no-cache brotli-libs=1.2.1-r0 curl=8.23.0-r0 libcurl=8.23.0-r0
COPY --from=builder /out/caddy /usr/bin/caddy
COPY --from=builder /out/build-info.txt /out/packages.txt /usr/share/caddy-build/
LABEL org.opencontainers.image.version="2.11.7-portal.1" \
      org.opencontainers.image.description="Caddy 2.11.7 security rebuild: Go 1.26.10 and checksum-locked patched dependencies"
