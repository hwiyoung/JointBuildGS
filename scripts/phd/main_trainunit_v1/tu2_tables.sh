#!/usr/bin/env bash
# PHD-MAIN-TRAINUNIT-v2 queue marker: tables and bundles are made by hand (light CPU) while the queue goes on.
#   bash tu2_tables.sh <ga|final>
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2
mkdir -p "$TU/control" && date -Iseconds > "$TU/control/TABLES_READY_$1" && echo "marker $1"
