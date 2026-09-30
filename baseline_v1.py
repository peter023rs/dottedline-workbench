#!/usr/bin/env python3
"""P&ID dashed/dotted logical-line tracing demo.

Focus: line tracing only. No OCR, symbol recognition, or equipment classification.
The method is deliberately classical / explainable:
  1) rasterize page
  2) directional morphology to isolate H/V stroke fragments
  3) align and chain collinear fragments
  4) use dash-gap periodicity to reject text / symbol-box false positives
  5) emit each dashed/dotted chain as ONE logical line segment

Best suited to orthogonal engineering drawings. Curves/diagonals are not handled here.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import cv2
import numpy as np
import fitz  # PyMuPDF


def render_page(pdf_path: str, page_number: int, dpi: int) -> np.ndarray:
    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    else:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return arr


def parse_crop(s: str | None, shape):
    h, w = shape[:2]
    if not s:
        return 0, 0, w, h
    x1, y1, x2, y2 = map(int, s.split(','))
    x1=max(0,x1); y1=max(0,y1); x2=min(w,x2); y2=min(h,y2)
    if x2<=x1 or y2<=y1:
        raise ValueError('invalid crop')
    return x1,y1,x2,y2


def components_to_segments(mask: np.ndarray, orient: str, scale: float):
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    segs=[]
    min_len=max(8, round(12*scale))
    max_th=max(5, round(10*scale))
    for i in range(1,n):
        x,y,w,h,area = map(int, stats[i])
        cx,cy = cents[i]
        if orient=='h':
            if w < min_len or h > max_th or w < 2*h: continue
            segs.append({'x1':x,'x2':x+w-1,'y':float(cy),'len':w})
        else:
            if h < min_len or w > max_th or h < 2*w: continue
            segs.append({'y1':y,'y2':y+h-1,'x':float(cx),'len':h})
    return segs


def cluster_axis(segs, orient, tol):
    key=(lambda s:s['y']) if orient=='h' else (lambda s:s['x'])
    clusters=[]
    for s in sorted(segs,key=key):
        if not clusters:
            clusters.append([s]); continue
        med=float(np.median([key(q) for q in clusters[-1]]))
        if key(s)-med > tol: clusters.append([s])
        else: clusters[-1].append(s)
    return clusters


def form_chains(cluster, orient, max_gap):
    if orient=='h':
        ordered=sorted(cluster,key=lambda s:s['x1']); start=lambda s:s['x1']; end=lambda s:s['x2']
    else:
        ordered=sorted(cluster,key=lambda s:s['y1']); start=lambda s:s['y1']; end=lambda s:s['y2']
    chains=[]; cur=[]; cur_end=None
    for s in ordered:
        if not cur:
            cur=[s]; cur_end=end(s); continue
        gap=start(s)-cur_end-1
        if gap <= max_gap:
            cur.append(s); cur_end=max(cur_end,end(s))
        else:
            chains.append(cur); cur=[s]; cur_end=end(s)
    if cur: chains.append(cur)
    return chains


def robust_periodicity(gaps):
    g=np.asarray([x for x in gaps if x>0],dtype=float)
    if len(g)<2: return 0.0,0.0
    med=float(np.median(g))
    regular=float(np.mean((g>=0.70*med) & (g<=1.40*med)))
    return med, regular


def detect_logical_dashed(img: np.ndarray, dpi: int):
    scale=dpi/250.0
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    ink=(gray<210).astype(np.uint8)*255

    k=max(7, round(13*scale))
    hmask=cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT,(k,1)))
    vmask=cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT,(1,k)))

    hsegs=components_to_segments(hmask,'h',scale)
    vsegs=components_to_segments(vmask,'v',scale)

    coord_tol=max(3,round(5*scale))
    max_gap=max(80,round(190*scale))  # permits interruptions by instrument bubbles / symbols
    min_extent=max(100,round(220*scale))
    gap_min=max(7,round(14*scale))
    gap_max=round(70*scale)

    lines=[]
    for orient,segs in [('h',hsegs),('v',vsegs)]:
        for cl in cluster_axis(segs,orient,coord_tol):
            for ch in form_chains(cl,orient,max_gap):
                if orient=='h':
                    a=min(s['x1'] for s in ch); b=max(s['x2'] for s in ch)
                    coord=float(np.median([s['y'] for s in ch]))
                    oo=sorted(ch,key=lambda s:s['x1'])
                    gaps=[max(0,oo[i+1]['x1']-oo[i]['x2']-1) for i in range(len(oo)-1)]
                    ink_len=sum(s['x2']-s['x1']+1 for s in ch)
                else:
                    a=min(s['y1'] for s in ch); b=max(s['y2'] for s in ch)
                    coord=float(np.median([s['x'] for s in ch]))
                    oo=sorted(ch,key=lambda s:s['y1'])
                    gaps=[max(0,oo[i+1]['y1']-oo[i]['y2']-1) for i in range(len(oo)-1)]
                    ink_len=sum(s['y2']-s['y1']+1 for s in ch)
                extent=b-a+1; n=len(ch); occ=min(1.0,ink_len/extent)
                gmed,greg=robust_periodicity(gaps)

                # Core classifier: multiple fragments, substantial line extent,
                # expected P&ID dash-gap scale, and repeated gap periodicity.
                # Occupancy filter removes stacked box edges and sparse text alignments.
                is_dashed=(
                    n>=5 and extent>=min_extent and
                    0.45<=occ<=0.82 and
                    gap_min<=gmed<=gap_max and
                    greg>=0.55
                )
                if is_dashed:
                    lines.append({
                        'orientation':orient,'a':int(a),'b':int(b),'coordinate':coord,
                        'length_px':int(extent),'fragment_count':int(n),
                        'occupancy':float(occ),'median_gap_px':float(gmed),
                        'regular_gap_fraction':float(greg)
                    })

    # deduplicate near-identical detections
    out=[]
    for line in sorted(lines,key=lambda z:(z['orientation'],z['coordinate'],z['a'])):
        dup=False
        for q in out:
            if q['orientation']!=line['orientation']: continue
            if abs(q['coordinate']-line['coordinate'])>coord_tol: continue
            inter=max(0,min(q['b'],line['b'])-max(q['a'],line['a']))
            smaller=max(1,min(q['b']-q['a'],line['b']-line['a']))
            if inter/smaller>=0.7:
                if line['length_px']>q['length_px']: q.update(line)
                dup=True; break
        if not dup: out.append(line)
    return out


def draw_overlay(img, lines):
    out=img.copy()
    for z in lines:
        if z['orientation']=='h':
            p1=(z['a'],round(z['coordinate'])); p2=(z['b'],round(z['coordinate']))
        else:
            p1=(round(z['coordinate']),z['a']); p2=(round(z['coordinate']),z['b'])
        cv2.line(out,p1,p2,(0,0,255),5,cv2.LINE_AA)
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('--page',type=int,required=True)
    ap.add_argument('--dpi',type=int,default=250)
    ap.add_argument('--crop',help='x1,y1,x2,y2 in rendered-page pixels')
    ap.add_argument('--out-prefix',required=True)
    args=ap.parse_args()

    page=render_page(args.pdf,args.page,args.dpi)
    x1,y1,x2,y2=parse_crop(args.crop,page.shape)
    crop=page[y1:y2,x1:x2].copy()
    lines=detect_logical_dashed(crop,args.dpi)
    overlay=draw_overlay(crop,lines)

    prefix=Path(args.out_prefix)
    prefix.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(prefix.with_name(prefix.name+'_crop.png')),crop)
    cv2.imwrite(str(prefix.with_name(prefix.name+'_overlay.png')),overlay)
    payload={'page':args.page,'dpi':args.dpi,'crop':[x1,y1,x2,y2],'logical_dashed_lines':[]}
    for i,z in enumerate(lines,1):
        zz=dict(z); zz['id']=i
        if z['orientation']=='h':
            zz['crop_endpoints']=[[z['a'],round(z['coordinate'])],[z['b'],round(z['coordinate'])]]
            zz['page_endpoints']=[[z['a']+x1,round(z['coordinate'])+y1],[z['b']+x1,round(z['coordinate'])+y1]]
        else:
            zz['crop_endpoints']=[[round(z['coordinate']),z['a']],[round(z['coordinate']),z['b']]]
            zz['page_endpoints']=[[round(z['coordinate'])+x1,z['a']+y1],[round(z['coordinate'])+x1,z['b']+y1]]
        payload['logical_dashed_lines'].append(zz)
    with open(prefix.with_name(prefix.name+'_lines.json'),'w',encoding='utf-8') as f:
        json.dump(payload,f,indent=2)
    print(f"Detected {len(lines)} logical dashed/dotted line segments")
    for z in sorted(lines,key=lambda q:q['length_px'],reverse=True)[:12]:
        print(z)

if __name__=='__main__': main()
