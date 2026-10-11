FROM node:22-bookworm

# iptables: used once at container start to lock down egress to just the
# model endpoint (see sandcastle.sandboxes.network_lockdown). No `gh`/
# GitHub CLI — v1 has no GitHub integration, issues are local files.
RUN apt-get update && apt-get install -y \
  git \
  curl \
  iptables \
  python3 \
  && rm -rf /var/lib/apt/lists/*

# Build-args for UID/GID alignment: the sandbox is started with
# --user <host-uid>:<host-gid>, so image-built files and bind-mounted
# files share an owner without runtime chown.
ARG AGENT_UID=1000
ARG AGENT_GID=1000

RUN groupmod -o -g $AGENT_GID node && usermod -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node

RUN npm install -g @mariozechner/pi-coding-agent

USER ${AGENT_UID}:${AGENT_GID}

WORKDIR /home/agent

# DockerSandboxProvider bind-mounts the git worktree at /home/agent/workspace
# and overrides the working directory at container start.
ENTRYPOINT ["sleep", "infinity"]
