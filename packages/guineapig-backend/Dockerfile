# ============================================================
# GuineaPig Backend — Multi-stage Docker Build
# ============================================================
# Stage 1: Build Go binary
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags "-s -w" -trimpath -o /build/bin/guineapig main.go

# Stage 2: Minimal runtime
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# ffmpeg（用于音频处理，按需启用）
# RUN apk add --no-cache ffmpeg

WORKDIR /app

COPY --from=builder /build/bin/guineapig .
COPY --from=builder /build/config.yaml .
COPY --from=builder /build/private.key .

RUN chmod +x /app/guineapig

EXPOSE 6880

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:6880/health || exit 1

CMD ["./guineapig"]
