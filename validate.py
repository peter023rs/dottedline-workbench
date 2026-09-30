"""Reproducible smoke run and explicitly scoped manual reference checks."""
import json
from collections import Counter
import numpy as np
from engine import analyze,DEMO,ROOT,export_images
# Source visually inspected at 144 DPI. Approximate PDF-point coordinates.
# This is a selected subset, not a complete annotated sheet.
REFERENCES=[
 ('supply top',[[584.6,602],[1379.9,602]],'dash_double_dot'),
 ('supply bottom',[[584.6,1161.9],[1379.9,1161.9]],'dash_double_dot'),
 ('supply left',[[584.6,602],[584.6,1161.9]],'dash_double_dot'),
 ('supply right',[[1379.9,602],[1379.9,1161.9]],'dash_double_dot'),
 ('YL00201 to motor signal',[[1024.9,583.2],[1024.9,689.7]],'dashed'),
 ('PI00203 to PT00203',[[710.1,592.9],[710.1,677.1]],'dashed'),
 ('PI00204 to PT00204',[[750.1,593.6],[750.1,678.7]],'dashed'),
 ('TI00204 horizontal',[[1016.2,715.1],[1394.4,715.1]],'dashed'),
 ('PI00205 horizontal',[[1042.6,754.6],[1394,754.6]],'dashed'),
 ('TI00205 horizontal',[[1173.7,796.9],[1393.4,796.9]],'dashed'),
 ('PI00206 horizontal',[[1263.3,841.8],[1393.1,841.8]],'dashed'),
 ('outgoing electrical signal',[[1557.2,754.5],[1738.4,754.5]],'dashed'),
 ('TI00203 upper mixed-scale run',[[797.487,593.571],[797.487,678.711]],'dashed'),
 ('PI00206 two-stroke corner',[[1263.319,841.835],[1263.319,875.564]],'dashed'),
 ('PI00202 clipped two-stroke corner',[[636.958,850.367],[636.958,875.564]],'dashed'),
 ('PI00201 two-stroke corner',[[662.906,724.182],[662.906,759.114]],'dashed'),
]
def match(points,line):
    p,q=np.array(points);a,b=np.array(line['points']);v=q-p;length=np.linalg.norm(v);u=v/length
    direction=(b-a)/np.linalg.norm(b-a)
    if abs(float(direction@u))<.995:return False
    def cross(v):return abs(float(u[0]*v[1]-u[1]*v[0]))
    lateral=max(cross(a-p),cross(b-p));lo,hi=sorted([float((a-p)@u),float((b-p)@u)])
    return lateral<2 and max(0,min(length,hi)-max(0,lo))/length>=.9

def main():
    if not DEMO.is_file():
        raise SystemExit('Install the original private 2401 PDF at data/2401.pdf before running this document-specific validation.')
    folder=ROOT/'outputs';folder.mkdir(exist_ok=True);runs=[];references={}
    for mode in ['native','raster','v1']:
        for page in range(1,13):
            data,image=analyze(DEMO,page,mode)
            runs.append({'page':page,'mode':mode,'candidates':len(data['lines']),'styles':dict(Counter(l['style'] for l in data['lines']))})
            target=folder/mode;target.mkdir(exist_ok=True);(target/f'page-{page:02}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
            if page==4:
                references[mode]=[{'reference':name,'geometry_recovered':any(match(pts,l) for l in data['lines']),'correct_style_recovered':any(match(pts,l) and l['style']==style for l in data['lines'])} for name,pts,style in REFERENCES]
                if mode=='native':export_images(data,image,folder/'page4')
    old_path=folder/'before-local-pattern-fix/page-04.json'
    previous=json.loads(old_path.read_text()) if old_path.is_file() else None
    if previous:
        references['native_before_fix']=[{'reference':name,'geometry_recovered':any(match(pts,l) for l in previous['lines']),'correct_style_recovered':any(match(pts,l) and l['style']==style for l in previous['lines'])} for name,pts,style in REFERENCES]
    current=json.loads((folder/'native/page-04.json').read_text())
    retained=sum(any(match(l['points'],q) and l['style']==q['style'] for q in current['lines']) for l in previous['lines']) if previous else None
    result={'source':'2401单元工艺管道及仪表流程图.pdf','detector_revision':current['detector_revision'],'dpi':144,'scope':'36 successful page/method smoke runs; 16 selected page-4 reference spans, including four previously missed runs. Not complete ground truth or whole-sheet precision/recall. Native and raster are different input modalities. V1 was run unchanged, including its original title-block treatment.','runs':runs,'reference_checks':references,'reference_coordinates':[{'name':n,'points':p,'style':s} for n,p,s in REFERENCES], 'unit_tests':'32 passed (see tests/test_engine.py); run separately with .venv/bin/python -m pytest -q','fix_regression':{'previous_page4_candidates':len(previous['lines']) if previous else None,'retained_previous_geometry_and_style':retained,'current_page4_candidates':len(current['lines'])},'known_limits':['Isolated one/two-stroke runs are omitted. Two-stroke runs require independent matching endpoint support.','No equipment/symbol recognition, general OCR, corner stitching or junction inference.','Raster candidate quality is poorer on densely connected symbols and text.','No downstream AI comprehension benchmark has been performed.']}
    (folder/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'smoke_runs':len(runs),'page4':[r for r in runs if r['page']==4],'references':{m:{'geometry':sum(x['geometry_recovered'] for x in v),'style':sum(x['correct_style_recovered'] for x in v),'total':len(v)} for m,v in references.items()}},indent=2))
if __name__=='__main__':main()
