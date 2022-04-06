FROM plone/plone-backend:6.0.0a3

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc
