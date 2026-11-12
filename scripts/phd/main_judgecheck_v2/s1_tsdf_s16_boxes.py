"""s1_tsdf_s16.py 의 칸 셈(quadrant)을 칸 번호 목록으로 돌림 (같은 구역을 여러 컨테이너가 나눠 맡기 위함; 이미 있는 칸은 건너뜀).  s1_tsdf_s16_boxes.py <tile> <k> [k ...]"""
import sys
import s1_tsdf_s16 as T
if __name__ == '__main__':
    T.cfg()
    for k in sys.argv[2:]: T.quadrant(sys.argv[1], int(k))
    print('BOXES_DONE', sys.argv[1:], flush=True)
