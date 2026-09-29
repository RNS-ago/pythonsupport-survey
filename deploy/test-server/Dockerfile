# A throwaway "fresh Ubuntu server" for running deploy/setup.sh and update.sh by hand.
# systemd runs as PID 1, so systemctl, journalctl and cron behave like on the real machine.
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
# Only what a stock Ubuntu server already has (systemd, cron, tzdata) plus git and CA
# certificates to clone the repo. setup.sh installs everything else, as it would for real.
RUN apt-get update \
 && apt-get install -y --no-install-recommends systemd systemd-sysv cron tzdata git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 # /mnt/repo is owned by your host user, not root; let root's git clone and fetch from it.
 && git config --system safe.directory '*'

ENV container=docker
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
