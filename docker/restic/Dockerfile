FROM golang:1.26.11-alpine3.24@sha256:ecb67f987aa1a57794c91d19ade7ae0209f2f0f5496aaef9e6ae85ddf92d02ab AS builder
WORKDIR /src
RUN wget -q https://github.com/restic/restic/releases/download/v0.19.1/restic-0.19.1.tar.gz \
    && echo 'bb9b1a19040744d26d8a79be029d4e6b189c45ccc9d8831d7fe367d3c33df725  restic-0.19.1.tar.gz' | sha256sum -c - \
    && tar -xzf restic-0.19.1.tar.gz --strip-components=1
RUN GOSUMDB=sum.golang.org GOFLAGS=-mod=mod go get golang.org/x/net@v0.60.0 \
    && GOSUMDB=sum.golang.org GOFLAGS=-mod=mod go mod tidy
RUN CGO_ENABLED=0 go build -trimpath -ldflags '-s -w -X main.version=0.19.1' -o /restic ./cmd/restic

FROM scratch
LABEL org.opencontainers.image.source="https://github.com/restic/restic" \
      org.opencontainers.image.version="0.19.1" \
      org.opencontainers.image.revision="6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf"
COPY --from=builder /restic /restic
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 65532:65532
ENTRYPOINT ["/restic"]
