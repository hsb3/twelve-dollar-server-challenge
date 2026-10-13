# The benchmark box as a container: Ubuntu 24.04, the submission installed as root and built as a
# normal user (README rules 8-10), plus Nginx for submissions that run behind it (rule 9).
FROM ubuntu:24.04

# A DigitalOcean droplet image ships these; the bare ubuntu image does not.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg git sudo xz-utils unzip lsb-release \
    && rm -rf /var/lib/apt/lists/*

ARG SUBMISSION
ENV SUBMISSION=${SUBMISSION}
WORKDIR /srv/challenge/submissions/${SUBMISSION}
COPY --chown=ubuntu:ubuntu submissions/${SUBMISSION}/ ./
RUN chown ubuntu:ubuntu .

RUN bash install.sh
USER ubuntu
RUN bash build.sh
USER root

# After install.sh so a submission can't lean on Nginx's dependencies. Settings from bench/nginx.conf;
# one worker because the box has one vCPU.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/* \
    && sed -i -e 's/^worker_processes .*/worker_processes 1;\nworker_rlimit_nofile 65535;/' \
              -e 's/worker_connections .*/worker_connections 16384;/' /etc/nginx/nginx.conf
COPY bench/nginx.conf /etc/nginx/sites-enabled/bench.conf
COPY docker/server-entrypoint.sh /usr/local/bin/server-entrypoint.sh

EXPOSE 80
ENTRYPOINT ["bash", "/usr/local/bin/server-entrypoint.sh"]
