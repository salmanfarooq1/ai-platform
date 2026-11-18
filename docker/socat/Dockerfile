FROM alpine/socat:1.8.0.3@sha256:beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e
LABEL org.opencontainers.image.source="https://github.com/alpine-docker/socat" \
      org.opencontainers.image.base.digest="sha256:beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e"
USER root
# Patch OS packages until upstream rebuilds the pinned base; remove this line then.
# See docs/deployment.md "image patch layer".
RUN apk upgrade --no-cache
