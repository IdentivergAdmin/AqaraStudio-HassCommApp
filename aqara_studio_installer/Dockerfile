# The installer is a one-shot filesystem copy, not a long-running S6 service.
# A minimal Alpine image avoids the irrelevant s6-overlay lifecycle messages.
FROM alpine:3.24

ARG BUILD_VERSION="0.1.4"
ARG BUILD_ARCH="amd64"

RUN apk add --no-cache bash jq

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp" \
      org.opencontainers.image.description="Idempotent native Aqara Studio Home Assistant integration installer"

COPY rootfs/ /
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
