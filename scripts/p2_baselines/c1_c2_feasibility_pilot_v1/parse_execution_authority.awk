BEGIN {
  approved_status = 0
  approved_user = 0
}

$0 == "- status: `APPROVED_FOR_EXECUTION`" {
  approved_status += 1
}

$0 == "- user_approval: `APPROVED_FOR_EXECUTION`" {
  approved_user += 1
}

END {
  if (approved_status == 1 && approved_user == 1) {
    exit 0
  }
  exit 64
}
