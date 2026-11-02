"""Copy the locked AXES71-v2 cell labels, without deriving or regrouping cells."""
from common import *
from screen_sim_tables import table
def main():
 c=json.loads((REPO/'configs/phd/main_axes71_v2/axes71_v2.json').read_text())['cells'];rows=[dict(cell='all',label='전체',kind='전체',members='기존 AXES71-v2 전체 모집단')]
 rows += [dict(cell=k,label=c['ko'][k],kind='참값 칸',members=k) for k in c['order']]
 rows += [dict(cell=k,label=v[0],kind='합계',members=', '.join(v[1])) for k,v in c['sums'].items()]
 table('cell_definitions',rows)
if __name__=='__main__':main()
