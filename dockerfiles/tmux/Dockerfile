# Stage 1: Extract tmux from CentOS Stream RPM
# Uses alpine with rpm2cpio to avoid QEMU issues with UBI10 during cross-builds.
FROM alpine:3.21 AS builder

ARG TARGETARCH

RUN apk add --no-cache curl rpm2cpio cpio

RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) RPMARCH="x86_64" ;; \
      arm64) RPMARCH="aarch64" ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    REPO_URL="https://mirror.stream.centos.org/9-stream/BaseOS/${RPMARCH}/os/Packages" && \
    TMUX_RPM=$(curl -fsSL "${REPO_URL}/" | grep -o 'tmux-[^"]*\.rpm' | tail -1) && \
    LIBEVENT_RPM=$(curl -fsSL "${REPO_URL}/" | grep -o 'libevent-[0-9][^"]*'"${RPMARCH}"'\.rpm' | tail -1) && \
    echo "tmux RPM: ${TMUX_RPM}" && \
    echo "libevent RPM: ${LIBEVENT_RPM}" && \
    mkdir -p /tmp/extract && cd /tmp/extract && \
    curl -fsSL -o tmux.rpm "${REPO_URL}/${TMUX_RPM}" && \
    curl -fsSL -o libevent.rpm "${REPO_URL}/${LIBEVENT_RPM}" && \
    rpm2cpio tmux.rpm | cpio -idmv 2>/dev/null && \
    rpm2cpio libevent.rpm | cpio -idmv 2>/dev/null && \
    cp /tmp/extract/usr/bin/tmux /usr/local/bin/tmux && \
    chmod +x /usr/local/bin/tmux && \
    mkdir -p /usr/local/lib64 && \
    cp /tmp/extract/usr/lib64/libevent*.so* /usr/local/lib64/

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/tmux /usr/local/bin/tmux
COPY --from=builder /usr/local/lib64/libevent*.so* /usr/lib64/

LABEL org.opencontainers.image.description="tmux init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/akurinnoy/tools-injector"
