"""Account for every ALS condition, including preserved training stops."""
from eight_arm_report import main

SITES = ['B173nb_b10', 'B0_b10', 'R1rep_b10']
REPORT = '중간보고_항공LiDAR_12조건_v1.md'

if __name__ == '__main__':
    main(sites=SITES, report=REPORT, prefix='twelve_arm', allow_stopped=True)
