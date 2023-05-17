# syntax=docker/dockerfile:1
FROM plone/plone-backend:6.0.1

RUN <<EOT
    ./bin/pip install "https://github.com/plone/plone.restapi/archive/refs/heads/issue-1587-purge.zip"
EOT
