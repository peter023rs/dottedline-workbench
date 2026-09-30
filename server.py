"""Local-only review app. No drawing leaves this computer."""
from functools import lru_cache
from pathlib import Path
import argparse
import io
import json
import threading
import uuid
import zipfile
import cv2
import pymupdf as fitz
from flask import Flask, request, jsonify, send_file, send_from_directory
from engine import ROOT, DEMO, DETECTOR_REVISION, analyze, export_images

app=Flask(__name__,static_folder='static',static_url_path='/static')
app.config['MAX_CONTENT_LENGTH']=24*1024*1024
UPLOADS=ROOT/'data/uploads';UPLOADS.mkdir(exist_ok=True)
DOCS={'demo':DEMO}
LOCK=threading.Lock()

@app.get('/')
def index():return send_from_directory(ROOT/'static','index.html')

@app.get('/health')
def health():return {'app':'dottedline-workbench','version':DETECTOR_REVISION,'demo_available':DEMO.is_file()}

@app.post('/api/upload')
def upload():
    file=request.files.get('file')
    if not file:return {'error':'Choose a PDF or image.'},400
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'):return {'error':'Choose a PDF or supported image.'},400
    data=file.read()
    try:
        with fitz.open(stream=data,filetype=suffix.lstrip('.')) as doc:
            if doc.needs_pass:return {'error':'Unlock this PDF before uploading.'},400
            pages=len(doc)
            if not pages:return {'error':'This document has no pages.'},400
    except Exception:return {'error':'This file could not be read as a drawing.'},400
    token=uuid.uuid4().hex;path=UPLOADS/(token+suffix);path.write_bytes(data);DOCS[token]=path
    return {'id':token,'name':file.filename,'pages':pages}

@lru_cache(maxsize=8)
def cached(doc_id,page,mode):
    if doc_id not in DOCS:raise ValueError('Drawing not found. Upload it again.')
    if not DOCS[doc_id].is_file():raise ValueError('The local sample is not installed. Upload a PDF or image using Open drawing.')
    # PyMuPDF does not support multithreaded access; serialize document work.
    with LOCK:return analyze(DOCS[doc_id],page,mode)

def arguments():
    mode=request.args.get('mode','native')
    if mode not in ('native','raster','v1'):raise ValueError('Unknown detection method.')
    return request.args.get('doc','demo'),int(request.args.get('page',4)),mode

@app.get('/api/analyze')
def run():
    try:
        data,_=cached(*arguments());return jsonify(data)
    except (ValueError,RuntimeError) as e:return {'error':str(e)},400

@app.get('/api/source.png')
def source():
    try:
        _,image=cached(*arguments());ok,png=cv2.imencode('.png',image)
        return send_file(io.BytesIO(png.tobytes()),mimetype='image/png')
    except (ValueError,RuntimeError) as e:return {'error':str(e)},400

@app.get('/api/research')
def research():return send_file(ROOT/'research.md',mimetype='text/plain')

@app.get('/api/validation')
def validation():
    path=ROOT/'outputs/validation.json'
    return send_file(path,mimetype='application/json') if path.exists() else jsonify({'status':'Validation has not run yet.'})

@app.post('/api/export')
def export():
    try:
        data,img=cached(*arguments());data=json.loads(json.dumps(data));body=request.get_json() or {};reviews=body.get('reviews',{})
        if reviews and body.get('detector_revision')!=data['detector_revision']:
            return {'error':'The detector changed. Reload, analyze, and review these candidates before exporting.'},409
        for line in data['lines']:
            edit=reviews.get(line['id'],{})
            if edit.get('review') in ['accepted','rejected','candidate']:line['review']=edit['review']
            if edit.get('engineering_type') in ['unknown','electrical_signal','pneumatic_signal','hydraulic_signal','data_link','supply_boundary','unit_boundary']:
                line['detected_semantics']={k:line[k] for k in ['engineering_type','semantic_status','semantic_evidence']}
                line.update(engineering_type=edit['engineering_type'],semantic_status='user_assigned',semantic_evidence={'basis':'User assignment in local review UI','note':str(edit.get('note',''))[:2000]})
        original_count=len(data['lines']);all_lines=data['lines'];accepted_only=body.get('accepted_only',False)
        data['lines']=[l for l in all_lines if l['review']!='rejected' and (not accepted_only or l['review']=='accepted')]
        data['export_policy']='accepted_only' if accepted_only else 'all_nonrejected_candidates'
        data['all_review_records']=[{k:l[k] for k in ['id','review','engineering_type','semantic_status','semantic_evidence']} for l in all_lines]
        data['detected_candidate_count']=original_count
        s=data['dpi']/72
        normalized=img.copy();trace=__import__('numpy').zeros(img.shape[:2],dtype='uint8');boundary=trace.copy()
        for line in data['lines']:
            pts=[tuple(round(v*s) for v in p) for p in line['points']];width=max(1,round(line['width']*s))
            cv2.line(normalized,*pts,(0,0,0),width,cv2.LINE_8)
            cv2.line(boundary if line['engineering_type'] in ['supply_boundary','unit_boundary'] else trace,*pts,255,width,cv2.LINE_8)
        result=io.BytesIO()
        with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('lines.json',json.dumps(data,ensure_ascii=False,indent=2))
            for name,image in [('original',img),('normalized',normalized),('trace-mask',trace),('boundary-mask',boundary)]:
                _,buf=cv2.imencode('.png',image);z.writestr(name+'.png',buf.tobytes())
            z.writestr('README.txt','Coordinates in lines.json are PDF points; PNG coordinates = points * dpi/72. White mask pixels denote lines. trace-mask excludes assigned boundaries but may include unknown candidates. A flattened normalized image alone loses meaning: always carry lines.json with it. Crossings are not junctions. Original drawing retained.\n')
        result.seek(0);return send_file(result,mimetype='application/zip',as_attachment=True,download_name=f'dottedline-page-{data["page"]}-{data["mode"]}.zip')
    except (ValueError,RuntimeError) as e:return {'error':str(e)},400

@app.errorhandler(413)
def too_large(e):return {'error':'File is larger than 24 MB.'},413

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8767);p.add_argument('--open',action='store_true');args=p.parse_args()
    if args.open:
        import webbrowser
        threading.Timer(.7,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    app.run(host='127.0.0.1',port=args.port,debug=False,threaded=True)
