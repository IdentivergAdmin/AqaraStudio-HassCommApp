FROM ghcr.io/home-assistant/base:3.24-2026.10.0

ARG BUILD_VERSION="0.1.0"
ARG BUILD_ARCH="amd64"

RUN apk add --no-cache bash jq

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp" \
      org.opencontainers.image.description="One-shot installer for the native Aqara Studio Home Assistant integration"

COPY rootfs/ /
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
