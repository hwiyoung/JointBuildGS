"""덧붙임 1 뷰어 HTML 고침(템플릿 building_eval.html 과 같은 바꿈을 이미 만든 HTML 에 덧씌움; 자료는 그대로).
1 창 크기가 0일 때 시점 맞춤이 NaN 이 되지 않게(resize 에서 건너뛰고, zoom 이 수가 아니면 처음 화면). 2 점 비율 판을 왼쪽 판 오른쪽으로. 3 주소 #w=<n> = 틀림 목록 n번째 고르기. 4 단면 세로 범위에 ③ 시작 점을 넣음(기둥 반길이 안). 5 창 크기가 아직 0이면 시점 맞춤을 미룸(헤드리스 갈무리).
사용: python g18_viewer_patch.py <html...>  (호스트 파이썬 표준 라이브러리만)"""
import sys
REP = [("function resize(){const w=innerWidth,h=innerHeight;R.setSize(w,h);", "function resize(){const w=innerWidth,h=innerHeight;if(!w||!h)return;R.setSize(w,h);"),
       ("addEventListener('resize',resize);", "addEventListener('resize',()=>{resize();if(!isFinite(cam.zoom))home();});"),
       ("cam.zoom=Math.min(W*.8/(x1-x0),H*.86/(y1-y0));cam.updateProjectionMatrix();upd();}", "cam.zoom=Math.min(W*.8/(x1-x0),H*.86/(y1-y0));if(!isFinite(cam.zoom)||cam.zoom<=0)cam.zoom=1;cam.updateProjectionMatrix();upd();}"),
       ("lo=Math.max(lo,-H);hi=Math.min(hi,H);\n const X=a=>", "if(col&&col.s){const s3=dec(col.s,Int16Array);for(let k=1;k<s3.length;k+=3){lo=Math.min(lo,s3[k]/1000-.3);hi=Math.max(hi,s3[k]/1000+.3);}}lo=Math.max(lo,-H);hi=Math.min(hi,H);\n const X=a=>"),
       ("function fit(){const a=new THREE.Vector3(", "function fit(){if(!innerWidth||!innerHeight){setTimeout(()=>{if(!selObj)fit();else resize();},100);return;}resize();const a=new THREE.Vector3("),
       ("#thin{left:10px;bottom:10px;", "#thin{left:310px;bottom:10px;"),
       ("\nwindow.__ready=true;", "\nif(q.get(\"w\")!==null){const bs=$(\"worst\").querySelectorAll(\"button\");const k=+q.get(\"w\");if(bs[k])bs[k].click();}\nwindow.__ready=true;")]
def patch(s):
    for a, b in REP:
        if b in s: continue
        assert s.count(a) == 1, a; s = s.replace(a, b)
    return s
if __name__ == '__main__':
    for p in sys.argv[1:]:
        s = open(p, encoding='utf-8').read(); t = patch(s)
        if t != s: open(p, 'w', encoding='utf-8').write(t); print('patched', p)
        else: print('same', p)
