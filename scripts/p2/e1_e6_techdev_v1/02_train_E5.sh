#!/usr/bin/env bash
exec "$(dirname "${BASH_SOURCE[0]}")/run_train_condition.sh" E5 "${JBGS_GPU_INDEX:-0}"
