# GROBID for ATLAS on a free Hugging Face Space (Docker SDK, CPU basic: 2 vCPU, 16 GB RAM).
# Why a Space: GROBID's CRF models need ~2.3 GB resident, more than a small laptop's Docker
# VM can give it (see docker-compose.yml). Same image and version as the compose file.
FROM grobid/grobid:0.9.1-crf

# Spaces run the container as uid 1000; GROBID writes temp files under grobid-home.
USER root
RUN mkdir -p /opt/grobid/grobid-home/tmp && chmod -R a+rwX /opt/grobid

# Plenty of RAM here, so keep GROBID's defaults (all models preloaded, concurrency 10).
ENV JAVA_OPTS="-Xmx4g"
EXPOSE 8070
