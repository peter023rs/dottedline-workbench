"""Pattern-preserving straight-line reconstruction. Coordinates are PDF points.

Research-inspired, not a reproduction of any cited paper. No equipment connectivity
is inferred. Crossings remain independent edges. See research.md and README.md.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import cv2
import numpy as np
import pymupdf as fitz

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / 'data/2401.pdf'
DETECTOR_REVISION = '2.1-local-patterns'


def fragment(p, q, width, source):
    p, q = np.array(p, float), np.array(q, float)
    v = q-p
    length = float(np.linalg.norm(v))
    if length < .04:
        return None
    angle = math.atan2(v[1], v[0]) % math.pi
    # Canonical orientation makes collinear strokes independent of drawing order.
    if abs(angle-math.pi) < 1e-5:
        angle = 0
    u = np.array([math.cos(angle), math.sin(angle)])
    n = np.array([-u[1], u[0]])
    a, b = sorted([float(p@u), float(q@u)])
    return dict(angle=angle, a=a, b=b, c=float((p+q)@n/2), width=max(.1,width), source=[source])


def native_fragments(page):
    out = []
    for idx, path in enumerate(page.get_drawings()):
        if path.get('type') not in ('s','fs') or path.get('stroke_opacity',1) == 0:
            continue
        # Explicit dashed PDF paths are expanded to preserve observed runs.
        dash = re.match(r'\[([^]]*)\]\s*([\d.+-]+)', path.get('dashes') or '[] 0')
        pattern = [float(x) for x in dash[1].split()] if dash else []
        if len(pattern)%2:
            pattern *= 2
        phase = float(dash[2]) if dash else 0
        for j, item in enumerate(path['items']):
            if item[0] != 'l':
                continue
            p, q = np.array(item[1]), np.array(item[2])
            length = float(np.linalg.norm(q-p))
            if not pattern or sum(pattern)<=0 or min(pattern)<0 or length<.04:
                f = fragment(p,q,path.get('width') or .7,f'{idx}:{j}')
                if f: out.append(f)
                continue
            # Restarting at each straight item is conservative for polylines;
            # exact multi-segment PDF dash phase is outside this prototype.
            pos = -(phase % sum(pattern)); k = 0
            while pos < length:
                end = pos+pattern[k%len(pattern)]
                if k%2 == 0 and end>0:
                    aa,bb=max(0,pos),min(length,end)
                    if bb-aa>.04:
                        out.append(fragment(p+(q-p)*aa/length,p+(q-p)*bb/length,path.get('width') or .7,f'{idx}:{j}:{k}'))
                pos=end;k+=1
    return out


def raster_fragments(image, dpi=144):
    """H/V strokes plus small round dots; no native PDF geometry used."""
    scale=dpi/72
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    ink=(gray<200).astype('uint8')*255
    out=[]
    for axis in ['h','v']:
        k=max(3,round(1.6*scale))
        mask=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(k,1) if axis=='h' else (1,k)))
        count,_,stats,cents=cv2.connectedComponentsWithStats(mask,8)
        for i in range(1,count):
            x,y,w,h,area=stats[i];cx,cy=cents[i]
            length,thick=(w,h) if axis=='h' else (h,w)
            if thick>3*scale or length<2*thick:continue
            p,q=([(x/scale,cy/scale),((x+w-1)/scale,cy/scale)] if axis=='h' else [(cx/scale,y/scale),(cx/scale,(y+h-1)/scale)])
            f=fragment(p,q,thick/scale,f'raster-{axis}-{i}')
            if f:out.append(f)
    count,_,stats,cents=cv2.connectedComponentsWithStats(ink,8)
    for i in range(1,count):
        x,y,w,h,area=stats[i];cx,cy=cents[i]
        if max(w,h)>3*scale or min(w,h)<1 or not .55<w/h<1.8 or area<2:continue
        for axis in ['h','v']:
            p,q=([(x/scale,cy/scale),((x+max(1,w-1))/scale,cy/scale)] if axis=='h' else [(cx/scale,y/scale),(cx/scale,(y+max(1,h-1))/scale)])
            out.append(fragment(p,q,min(w,h)/scale,f'dot-{axis}-{i}'))
    return out


def pattern_type(lengths,width):
    arr=np.asarray(lengths); inner=arr[1:-1] if len(arr)>4 else arr
    lo=float(np.percentile(inner,25)); hi=float(np.percentile(inner,85))
    if hi/max(lo,.01)>2.7:
        short=arr<(lo+hi)/2
        long_indices=np.flatnonzero(~short)
        counts=np.diff(long_indices)-1
        if len(counts) and np.mean(counts==2)>=.7:return 'dash_double_dot'
        if len(counts) and np.mean(counts==1)>=.7:return 'dash_dot'
        return 'mixed'
    if np.mean(abs(inner-np.median(inner)) <= max(.35,.3*np.median(inner)))<.75:
        return 'mixed'
    return 'dotted' if float(np.median(inner))<=max(1.2,1.9*width) else 'dashed'


def local_gap_runs(chain, raster=False):
    """Partition adjacent gaps before computing any chain-wide statistics.

    Runs share the stroke at a rhythm transition. This preserves both observed
    patterns without inventing a bridge across the transition or a missing dash.
    The range bound prevents a gradual spacing drift from becoming one run.
    """
    if len(chain) < 2:
        return
    gaps = [right['a'] - left['b'] for left, right in zip(chain, chain[1:])]
    start = 0
    low = high = gaps[0]
    for i, gap in enumerate(gaps[1:], 1):
        next_low, next_high = min(low, gap), max(high, gap)
        tolerance = max(.65 if raster else .15, .25 * next_low)
        if next_high - next_low > tolerance:
            yield chain[start:i + 1]
            start = i
            low = high = gap
        else:
            low, high = next_low, next_high
    yield chain[start:]


def endpoint_support(short, anchors, raster=False):
    """Geometry support only: proximity never asserts an engineering junction."""
    support = []
    tolerance = 1.5 if raster else .35
    for anchor in anchors:
        if anchor['style'] != short['style']:
            continue
        if abs(anchor['width'] - short['width']) > max(.35, .3 * anchor['width']):
            continue
        if abs(anchor['median_gap_pt'] - short['median_gap_pt']) > max(
                .65 if raster else .15, .2 * anchor['median_gap_pt']):
            continue
        lengths = anchor['dash_lengths_pt']
        # End dashes may be clipped or extended at corners and symbols.
        typical = float(np.median(lengths[1:-1] if len(lengths) > 2 else lengths))
        if not all(.6 * typical <= length <= 1.4 * typical
                   for length in short['dash_lengths_pt']):
            continue
        if min(math.dist(p, q) for p in short['points'] for q in anchor['points']) <= tolerance:
            support.append(anchor)
    return support


def reconstruct(frags, text_boxes=(), raster=False, min_fragments=3):
    """Cluster alignment, merge touching runs, split rhythm breaks, then classify."""
    tol=.65 if raster else .16
    buckets=defaultdict(list)
    for f in frags:
        if f is not None:buckets[round(math.degrees(f['angle'])*2)].append(f)
    clusters=[]
    for group in buckets.values():
        tracks=[]
        for f in sorted(group,key=lambda f:f['c']):
            choices=[t for t in tracks[-12:] if abs(t[0]['c']-f['c'])<=tol and abs(t[0]['width']-f['width'])<=max(.35,.45*f['width'])]
            if choices:min(choices,key=lambda t:abs(t[0]['c']-f['c'])).append(f)
            else:tracks.append([f])
        clusters.extend(tracks)
    found=[]
    short_runs=[]
    def emit(chain):
        if len(chain)<2:return
        gaps=np.array([b['a']-a['b'] for a,b in zip(chain,chain[1:])]); med=float(np.median(gaps))
        if med<=.1:return
        if float(np.std(gaps))/med > .25:return
        a,b=chain[0]['a'],chain[-1]['b']; extent=b-a
        if extent<12:return
        lengths=[f['b']-f['a'] for f in chain];width=float(np.median([f['width'] for f in chain]))
        style=pattern_type(lengths,width)
        if style=='mixed':return
        occ=sum(lengths)/extent
        if not .08<=occ<=.94:return
        angle=chain[0]['angle'];u=np.array([math.cos(angle),math.sin(angle)]);n=np.array([-u[1],u[0]])
        c=float(np.median([f['c'] for f in chain]));point=lambda t:[round(float(v),3) for v in t*u+c*n]
        # Text overlap splits evidence rather than filling through a label.
        for k in range(len(chain)-1):
            p,q=point(chain[k]['b']),point(chain[k+1]['a'])
            r=fitz.Rect(min(p[0],q[0])-.05,min(p[1],q[1])-.05,max(p[0],q[0])+.05,max(p[1],q[1])+.05)
            if any(r.intersects(fitz.Rect(box)) for box in text_boxes):
                emit(chain[:k+1]);emit(chain[k+1:]);return
        line=dict(points=[point(a),point(b)],style=style,width=round(width,3),
            angle_degrees=round(math.degrees(angle),2),length_pt=round(extent,3),
            fragment_count=len(chain),observed_fragments=[dict(points=[point(f['a']),point(f['b'])],source_ids=f['source']) for f in chain],
            dash_lengths_pt=[round(x,3) for x in lengths],gap_lengths_pt=[round(float(x),3) for x in gaps],
            inferred_bridges=[{'points':[point(left['b']),point(right['a'])],'reason':'collinearity_and_repeated_gap'} for left,right in zip(chain,chain[1:])],
            median_gap_pt=round(med,3),occupancy=round(occ,3),
            geometry_score=round(max(0,min(1,1-float(np.std(gaps))/(med+1e-6))),3),
            engineering_type='unknown',semantic_status='unresolved',semantic_evidence=None,
            review='candidate',connectivity='not_inferred')
        if len(chain)>=min_fragments:
            line['support']={'kind':'repeated_local_pattern'}
            found.append(line)
        elif len(chain)==2 and style in ('dashed','dotted'):
            short_runs.append(line)

    def emit_local(chain):
        for run in local_gap_runs(chain,raster):
            emit(run)
    for track in clusters:
        merged=[]
        for f in sorted(track,key=lambda f:f['a']):
            f=dict(f);f['source']=list(f['source'])
            if merged and f['a']-merged[-1]['b']<= (.3 if raster else .06):
                merged[-1]['b']=max(merged[-1]['b'],f['b']);merged[-1]['source']+=f['source']
            else:merged.append(f)
        chain=[]
        for f in merged:
            if chain and f['a']-chain[-1]['b']>32:
                emit_local(chain);chain=[]
            chain.append(f)
        emit_local(chain)
    # Only independently detected anchors can promote short runs. A chain of
    # weak two-stroke candidates cannot bootstrap itself into a detected line.
    anchors=list(found)
    supported=[]
    for short in short_runs:
        support=endpoint_support(short,anchors,raster)
        if support:
            short['geometry_score']=round(min(a['geometry_score'] for a in support)*.75,3)
            found.append(short)
            supported.append((short,support))
    # Dots can produce the same H/V chain only if enough dots align in both axes;
    # crossings are deliberately left independent, never unioned here.
    for i,line in enumerate(sorted(found,key=lambda l:(l['angle_degrees'],l['points'][0][1],l['points'][0][0])),1):line['id']=f'L{i:03}'
    for short,support in supported:
        short['support']={'kind':'matching_pattern_at_endpoint','line_ids':[a['id'] for a in support],
                          'note':'Two strokes supported by a longer pattern. No junction or symbol attachment inferred.'}
    return sorted(found,key=lambda l:l['id'])


def render(page,dpi=144):
    pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),colorspace=fitz.csRGB,alpha=False)
    return cv2.cvtColor(np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3),cv2.COLOR_RGB2BGR)


def analyze(path=DEMO,page_number=4,mode='native',dpi=144):
    path=Path(path)
    with fitz.open(path) as doc:
        if not 1<=page_number<=len(doc):raise ValueError('Page is outside this document.')
        page=doc[page_number-1]
        # Work in unrotated PDF coordinates; render rotation is normalized too.
        if doc.is_pdf:page.set_rotation(0)
        if page.rect.width*page.rect.height*(dpi/72)**2>50_000_000:raise ValueError('Page is too large to process at this DPI.')
        image=render(page,dpi)
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        demo_sha=hashlib.sha256(DEMO.read_bytes()).hexdigest() if DEMO.is_file() else None
        excluded=[[1823,1326,2318,1629]] if sha==demo_sha else []
        boxes=[s['bbox'] for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()]
        if mode=='v1':
            from baseline_v1 import detect_logical_dashed
            lines=[]
            for z in detect_logical_dashed(image,dpi):
                pts=([[z['a'],z['coordinate']],[z['b'],z['coordinate']]] if z['orientation']=='h' else [[z['coordinate'],z['a']],[z['coordinate'],z['b']]])
                lines.append(dict(id=f'L{len(lines)+1:03}',points=[[v*72/dpi for v in p] for p in pts],style='unclassified_dashed',width=.7,fragment_count=z['fragment_count'],geometry_score=z['regular_gap_fraction'],engineering_type='unknown',semantic_status='unresolved',semantic_evidence=None,review='candidate',connectivity='not_inferred',observed_fragments=[],dash_lengths_pt=[],gap_lengths_pt=[],length_pt=z['length_px']*72/dpi,median_gap_pt=z['median_gap_px']*72/dpi))
            used='v1'
        else:
            frags=native_fragments(page) if mode=='native' else []
            used='native' if frags else 'raster'
            raster_image=image.copy()
            for x0,y0,x1,y1 in excluded:
                cv2.rectangle(raster_image,(round(x0*dpi/72),round(y0*dpi/72)),(round(x1*dpi/72),round(y1*dpi/72)),(255,255,255),-1)
            lines=reconstruct(frags if frags else raster_fragments(raster_image,dpi),boxes+excluded,raster=used=='raster')
            lines=[l for l in lines if not any(fitz.Rect(b).contains(fitz.Point(p)) for b in excluded for p in l['points'])]
            surviving_ids={l['id'] for l in lines}
            lines=[l for l in lines if l.get('support',{}).get('kind')!='matching_pattern_at_endpoint'
                   or surviving_ids.intersection(l['support']['line_ids'])]
            renamed={l['id']:f'L{i:03}' for i,l in enumerate(lines,1)}
            for l in lines:
                l['id']=renamed[l['id']]
                if 'line_ids' in l.get('support',{}):
                    l['support']['line_ids']=[renamed[x] for x in l['support']['line_ids'] if x in renamed]
        if sha==demo_sha and used!='v1':
            for line in lines:
                if line['style']=='dash_double_dot':
                    line.update(engineering_type='supply_boundary',semantic_status='document_note_supported',semantic_evidence={'document_sha256':sha,'page':4,'text':'双点划线内为厂家供货范围。','basis':'Pattern class plus explicit drawing note. Geometry still requires review.'})
                elif line['style']=='dashed':
                    line.update(engineering_type='electrical_signal_candidate',semantic_status='legend_inferred',semantic_evidence={'document_sha256':sha,'page':3,'bbox':[160,138,335,158],'text':'电信号线','basis':'Repeated dash pattern agrees with legend; legend and drawing dash scales differ. Not verified connectivity.'})
        return dict(schema_version=2,detector_revision='v1-original' if used=='v1' else DETECTOR_REVISION,document=path.name,document_sha256=sha,page=page_number,page_count=len(doc),width=page.rect.width,height=page.rect.height,dpi=dpi,mode=used,excluded_regions=[{'bbox':b,'reason':'2401 title block, document-specific profile'} for b in excluded],coordinate_system='unrotated PDF points, top-left origin, 72 points/inch',lines=lines,warnings=['Candidate geometry, not validated plant connectivity.','Crossings do not create junctions. Corners are separate straight runs.','Native mode supports straight segments; raster fallback supports horizontal/vertical runs.','No symbol recognition: dense symbols, touching marks and occlusions require review.','Geometry score is a heuristic, not a calibrated probability. Two-stroke candidates require matching endpoint support.']),image


def export_images(payload,image,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    scale=payload['dpi']/72;normalized=image.copy();mask=np.zeros(image.shape[:2],np.uint8);boundaries=mask.copy()
    for line in payload['lines']:
        pts=[tuple(round(v*scale) for v in p) for p in line['points']];thick=max(1,round(line['width']*scale))
        cv2.line(normalized,*pts,(0,0,0),thick,cv2.LINE_8)
        cv2.line(boundaries if line['engineering_type']=='supply_boundary' else mask,*pts,255,thick,cv2.LINE_8)
    cv2.imwrite(str(folder/'original.png'),image);cv2.imwrite(str(folder/'normalized.png'),normalized)
    cv2.imwrite(str(folder/'trace-mask.png'),mask);cv2.imwrite(str(folder/'boundary-mask.png'),boundaries)
    (folder/'lines.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('pdf',nargs='?',default=str(DEMO));ap.add_argument('--page',type=int,default=4);ap.add_argument('--mode',choices=['native','raster','v1'],default='native');ap.add_argument('--out',default='outputs/page4');ap.add_argument('--dpi',type=int,default=144);args=ap.parse_args()
    data,img=analyze(args.pdf,args.page,args.mode,args.dpi);export_images(data,img,args.out)
    print(json.dumps({'page':args.page,'mode':data['mode'],'candidates':len(data['lines']),'styles':dict(__import__('collections').Counter(l['style'] for l in data['lines']))}))
