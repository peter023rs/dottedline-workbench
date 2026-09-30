import io
import json
import zipfile
import cv2
import numpy as np
import pytest
from engine import fragment, reconstruct, raster_fragments, analyze, DEMO

requires_2401=pytest.mark.skipif(not DEMO.is_file(),reason='Private 2401 PDF is not installed in data/2401.pdf')

def chain(lengths=(12,)*8,gap=6,y=50,angle=0,start=10,width=1):
    a=np.radians(angle);u=np.array([np.cos(a),np.sin(a)]);origin=np.array([0,y]);out=[]
    for i,length in enumerate(lengths):
        out.append(fragment(origin+u*start,origin+u*(start+length),width,str(i)));start+=length+gap
    return out

@pytest.mark.parametrize('lengths,style',[( [12]*8,'dashed'),([1]*9,'dotted'),([24,3]*5,'dash_dot'),([30,3,3]*4,'dash_double_dot')])
def test_visual_grammar_is_preserved(lengths,style):
    lines=reconstruct(chain(lengths));assert len(lines)==1
    l=lines[0];assert l['style']==style;assert l['fragment_count']==len(lengths)
    assert l['engineering_type']=='unknown';assert len(l['observed_fragments'])==len(lengths)

@pytest.mark.parametrize('angle',[0,30,45,90,135,179])
def test_native_angles(angle):
    lines=reconstruct(chain(angle=angle));assert len(lines)==1
    assert lines[0]['style']=='dashed'

def test_parallel_lines_are_separate():
    lines=reconstruct(chain(y=50)+chain(y=53));assert len(lines)==2

def test_crossings_do_not_create_junctions():
    lines=reconstruct(chain(y=50)+chain(y=0,angle=90,start=0));assert len(lines)==2
    assert all(l['connectivity']=='not_inferred' for l in lines)

def test_solid_strokes_are_not_dashes():
    assert reconstruct(chain(gap=0))==[]

def test_missing_dash_is_not_blindly_bridged():
    f=chain();f.pop(4);lines=reconstruct(f);assert len(lines)==2
    assert sorted(l['fragment_count'] for l in lines)==[3,4]

def test_text_in_gap_splits_chain():
    lines=reconstruct(chain(),text_boxes=[[80,48,82,52]])
    assert len(lines)==2

def test_irregular_fragments_rejected():
    f=chain();offset=0
    for i,z in enumerate(f):
        z['a']+=i*i*3;z['b']+=i*i*3
    assert reconstruct(f)==[]

@pytest.mark.parametrize('dpi',[72,144,216])
def test_raster_dots_and_dashes(dpi):
    s=dpi/72;im=np.full((round(160*s),round(230*s),3),255,np.uint8)
    for x in range(10,210,20):
        cv2.line(im,(round(x*s),round(45*s)),(round((x+12)*s),round(45*s)),(0,0,0),max(1,round(s)))
        cv2.circle(im,(round(x*s),round(100*s)),max(1,round(s)),(0,0,0),-1)
    lines=reconstruct(raster_fragments(im,dpi),raster=True)
    assert any(l['style']=='dashed' and l['fragment_count']>=8 for l in lines)
    assert any(l['style']=='dotted' and l['fragment_count']>=8 for l in lines)

@requires_2401
def test_2401_four_boundary_sides_and_original_preserved():
    data,img=analyze(DEMO,4)
    boundary=[l for l in data['lines'] if l['engineering_type']=='supply_boundary']
    assert len(boundary)==4
    assert all(l['style']=='dash_double_dot' and l['semantic_evidence']['page']==4 for l in boundary)
    assert all(not (l['points'][0][0]>1823 and l['points'][0][1]>1326) for l in data['lines'])

@requires_2401
def test_api_review_export_roundtrip():
    from server import app
    c=app.test_client();data=c.get('/api/analyze?page=4').json
    chosen=next(l for l in data['lines'] if l['style']=='dashed')
    response=c.post('/api/export?page=4',json={'detector_revision':data['detector_revision'],'accepted_only':True,'reviews':{chosen['id']:{'review':'accepted','engineering_type':'pneumatic_signal','note':'test reviewer evidence'}}})
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        exported=json.loads(z.read('lines.json'));assert len(exported['lines'])==1
        assert exported['lines'][0]['engineering_type']=='pneumatic_signal'
        assert exported['lines'][0]['style']=='dashed'
        assert exported['lines'][0]['semantic_status']=='user_assigned'
        assert exported['lines'][0]['semantic_evidence']['note']=='test reviewer evidence'
        source=cv2.imdecode(np.frombuffer(z.read('original.png'),np.uint8),cv2.IMREAD_COLOR)
        assert np.array_equal(source,analyze(DEMO,4)[1])
        mask=cv2.imdecode(np.frombuffer(z.read('boundary-mask.png'),np.uint8),0);assert not mask.any()

def test_invalid_inputs():
    from server import app
    c=app.test_client()
    assert c.get('/api/analyze?page=999').status_code==400
    assert c.get('/api/analyze?mode=garbage').status_code==400
    assert c.post('/api/upload',data={'file':(io.BytesIO(b'broken'), 'bad.pdf')}).status_code==400

def test_uploaded_image_runs_through_ui_api():
    from server import app
    c=app.test_client();im=np.full((160,400,3),255,np.uint8)
    for x in range(15,360,30):cv2.line(im,(x,80),(x+15,80),(0,0,0),2)
    _,png=cv2.imencode('.png',im)
    response=c.post('/api/upload',data={'file':(io.BytesIO(png.tobytes()),'dots.png')})
    assert response.status_code==200
    result=c.get('/api/analyze?doc='+response.json['id']+'&page=1')
    assert result.status_code==200
    assert result.json['mode']=='raster'
    assert any(l['style']=='dashed' for l in result.json['lines'])


def covers_vertical(lines,x,start,end):
    return any(abs(l['points'][0][0]-x)<1 and abs(l['points'][1][0]-x)<1
               and l['points'][0][1]<=start+1 and l['points'][1][1]>=end-1
               for l in lines)


@requires_2401
def test_2401_ui_api_recovers_both_reported_misses():
    from server import app
    data=app.test_client().get('/api/analyze?page=4&mode=native').json
    assert covers_vertical(data['lines'],797.487,593.571,678.711), 'TI00203 upper dashed run missing'
    assert covers_vertical(data['lines'],1263.319,841.835,875.564), 'PI00206 two-stroke corner missing'
    assert covers_vertical(data['lines'],636.958,850.367,875.564), 'PI00202 clipped two-stroke corner missing'
    ids={l['id'] for l in data['lines']}
    assert all(set(l.get('support',{}).get('line_ids',[]))<=ids for l in data['lines'])


def test_adjacent_fine_pattern_cannot_erase_coarse_pattern():
    coarse=chain(lengths=[12]*5,gap=6)
    fine=chain(lengths=[3]*8,gap=1.5,start=coarse[-1]['b']+1.5)
    lines=reconstruct(coarse+fine)
    assert any(l['points'][0][0]==10 and l['points'][1][0]>=coarse[-1]['b'] for l in lines)
    assert any(l['median_gap_pt']==1.5 for l in lines)
    assert not any(l['points'][0][0]==10 and l['points'][1][0]>=fine[-1]['b'] for l in lines)


def corner_fragments(short_gap=6,offset=0,width=1):
    horizontal=chain(lengths=[12]*6,gap=6,start=10,y=50)
    x=horizontal[-1]['b']+offset
    vertical=[fragment((x,50),(x,62),width,'short-0'),
              fragment((x,62+short_gap),(x,74+short_gap),width,'short-1')]
    return horizontal,vertical


def test_two_strokes_require_matching_endpoint_support():
    horizontal,vertical=corner_fragments()
    assert reconstruct(vertical)==[]
    lines=reconstruct(horizontal+vertical)
    recovered=[l for l in lines if l['fragment_count']==2]
    assert len(recovered)==1
    assert recovered[0]['support']['kind']=='matching_pattern_at_endpoint'
    assert recovered[0]['support']['line_ids']
    assert recovered[0]['connectivity']=='not_inferred'


@pytest.mark.parametrize('gap,offset,width',[(10,0,1),(6,3,1),(6,0,3)])
def test_two_stroke_distractors_are_not_promoted(gap,offset,width):
    horizontal,vertical=corner_fragments(gap,offset,width)
    assert all(l['fragment_count']>=3 for l in reconstruct(horizontal+vertical))


def test_midline_crossing_is_not_endpoint_support():
    horizontal,_=corner_fragments()
    vertical=[fragment((50,50),(50,62),1,'short-0'),fragment((50,68),(50,80),1,'short-1')]
    assert all(l['fragment_count']>=3 for l in reconstruct(horizontal+vertical))


def test_corner_support_uses_interior_dash_size():
    horizontal=chain(lengths=[17,12,12,17],gap=6)
    x=horizontal[-1]['b']
    vertical=[fragment((x,50),(x,58),1,'corner-0'),fragment((x,64),(x,72),1,'corner-1')]
    assert any(l['fragment_count']==2 for l in reconstruct(horizontal+vertical))


@requires_2401
def test_reviews_from_previous_detector_are_not_applied_to_renumbered_lines():
    from server import app
    c=app.test_client()
    response=c.post('/api/export?page=4',json={'detector_revision':'old-revision','reviews':{'L017':{'review':'accepted'}}})
    assert response.status_code==409
