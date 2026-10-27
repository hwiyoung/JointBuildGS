"""Validate eleven scored ALS arms and one explicit frozen-criterion stop."""
from verify_eight_arms import main
from twelve_arm_report import SITES, REPORT

if __name__ == '__main__':
    main(sites=SITES, report_name=REPORT, prefix='twelve_arm', expected_scored=11, expected_stopped=1)
