"""Third key worker after training (RAM freed): keys from the end of both lists, 30,000 first."""
import sys, run_stage3 as S
if __name__ == '__main__': S.worker([int(x) for x in sys.argv[1:]]); S.note(step='extra_worker_done', keys=sys.argv[1:])
