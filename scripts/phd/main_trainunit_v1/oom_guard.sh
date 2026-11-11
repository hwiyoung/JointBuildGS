#!/usr/bin/env bash
# TRAINERR has priority: make every process of this task's containers (name jbgs-trainunit-*) the kernel's first OOM choice.
# Only raises oom_score_adj of our own processes (allowed without privilege); never touches other containers.
while true; do
  for id in $(docker ps --filter name=jbgs-trainunit --format '{{.ID}}'); do
    for pid in $(docker top "$id" -eo pid 2>/dev/null | tail -n +2); do
      [ -w /proc/$pid/oom_score_adj ] && [ "$(cat /proc/$pid/oom_score_adj 2>/dev/null)" != "500" ] && echo 500 > /proc/$pid/oom_score_adj 2>/dev/null
    done
  done
  sleep 30
done
