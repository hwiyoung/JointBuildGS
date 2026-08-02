BEGIN {
  FS = "\t"
  protocol_count = 0
  malformed = 0
}

$1 == "JBGS_MACHINE_DECISION_V1" {
  protocol_count += 1
  if (NF != 3) {
    malformed = 1
  } else {
    action = $2
    attempt = $3
  }
}

END {
  if (protocol_count != 1 || malformed) {
    exit 64
  }
  if (action == "SKIP_COMPLETED" && attempt == "0") {
    print action
    print attempt
    exit 0
  }
  if (action == "RUN" && (attempt == "1" || attempt == "2")) {
    print action
    print attempt
    exit 0
  }
  exit 64
}
