import asyncio, time, uuid, hashlib, threading, io, csv, os, json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict
try:
    from backend.engine import Dataset, ingest
    from backend.schema import REQUIRED, RECOMMENDED, FIELDS, LABELS
except ImportError:
    from engine import Dataset, ingest
    from schema import REQUIRED, RECOMMENDED, FIELDS, LABELS

try:
    from vercel.blob import BlobClient, BlobNotFoundError
except ImportError:
    BlobClient = None
    BlobNotFoundError = Exception

# Warm-process cache; private Blob files are the source of truth in production.
SESSIONS = {}
TTL = 3600
REMOTE_TTL = 86400
MAX_UPLOAD = 100_000_000
BLOB_TOKEN = os.getenv('BLOB_READ_WRITE_TOKEN')
BLOB = BlobClient(BLOB_TOKEN) if BLOB_TOKEN and BlobClient else None

def manifest_path(sid): return f'sessions/{sid}/manifest.json'

def new_state(files=None, frames=None):
    frames=frames or {}
    return {'files':files or [],'frames':frames,'dataset':Dataset(list(frames.values())),'touched':time.monotonic(),'lock':threading.RLock()}

def persist(sid,s):
    if not BLOB:return
    payload=json.dumps({'updated_at':datetime.now(timezone.utc).isoformat(),'files':s['files']},separators=(',',':'))
    BLOB.put(manifest_path(sid),payload,access='private',content_type='application/json',overwrite=True)

def load_remote(sid):
    if not BLOB:return None
    try: files=json.loads(BLOB.get(manifest_path(sid),access='private',use_cache=False).content)['files']
    except (BlobNotFoundError,KeyError,ValueError,TypeError):return None
    frames={}
    try:
        for f in files: frames[f['id']]=__import__('pandas').read_pickle(io.BytesIO(BLOB.get(f['_frame_path'],access='private').content),compression='gzip')
    except BlobNotFoundError:return None
    return new_state(files,frames)

def public_files(files):return [{k:v for k,v in f.items() if not k.startswith('_')} for f in files]

def delete_blobs(files,include_manifest=None):
    if not BLOB:return
    paths=[p for f in files for p in (f.get('_source_path'),f.get('_frame_path')) if p]
    if include_manifest:paths.append(manifest_path(include_manifest))
    if paths:BLOB.delete(paths)

def destroy(sid,remote=False):
    session=SESSIONS.pop(sid,None)
    files=list(session['files']) if session else []
    if remote and not files:
        loaded=load_remote(sid)
        files=list(loaded['files']) if loaded else []
        if loaded:loaded['dataset'].close()
    if session:
        with session['lock']:
            session['dataset'].close(); session['files'].clear(); session['frames'].clear()
    if remote:delete_blobs(files,sid)

@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await asyncio.sleep(60)
            for sid,s in list(SESSIONS.items()):
                if time.monotonic()-s['touched']>TTL: destroy(sid)
    task=asyncio.create_task(cleanup())
    yield
    task.cancel()
    for sid in list(SESSIONS):destroy(sid)

app=FastAPI(title='Pharma Sales Intelligence',lifespan=lifespan)

@app.middleware('http')
async def local_origin(request:Request,call_next):
    origin=request.headers.get('origin')
    allowed={'http://localhost:3000','http://127.0.0.1:3000',*[x.strip() for x in os.getenv('ALLOWED_ORIGINS','').split(',') if x.strip()]}
    if origin and origin not in allowed:
        return Response('Origin not allowed',status_code=403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response

class Query(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filters:dict[str,list[str]]=Field(default_factory=dict)
    exclude_partial:bool=False
    buckets:tuple[int,int,int]=(180,365,548)
    search:str=Field(default='',max_length=200)
    sort:str='date'
    descending:bool=True
    page:int=Field(default=0,ge=0)
    size:int=Field(default=50,ge=1,le=250)

class Comparison(Query):
    years:tuple[str,str]

@app.post('/api/sessions/{sid}/comparison')
def compare(sid:str,q:Comparison):
    s=session(sid)
    with s['lock']:
        d=s['dataset']
        if not s['files']:raise HTTPException(409,'No dataset loaded')
        if q.years[0]==q.years[1]:raise HTTPException(422,'Choose two different fiscal years.')
        try:
            filters={k:v for k,v in q.filters.items() if k not in ('fiscal_year','year')}
            where,params=d.where(filters,q.exclude_partial)
            base=where+(' AND ' if where else ' WHERE ')
            dates=[]
            for year in q.years:
                dates.append({r['day'] for r in d.query("SELECT DISTINCT strftime(date,'%m-%d') AS day FROM sales"+base+'fiscal_year = ?',params+[year])})
            shared=sorted(dates[0]&dates[1])
            if not shared:return {'years':q.years,'days':0,'values':[],'trend':[]}
            clause=base+"fiscal_year = ? AND strftime(date,'%m-%d') IN ("+','.join('?' for _ in shared)+')'
            values=[];trend=[]
            for year in q.years:
                row=d.query('SELECT '+d.measures()+' FROM sales'+clause,params+[year]+shared)[0]
                values.append(dict(row,name=year))
                trend+= [dict(r,year=year) for r in d.query("SELECT strftime(date,'%m-%d') AS name,sum(net)/100.0 net FROM sales"+clause+' GROUP BY 1 ORDER BY 1',params+[year]+shared)]
            return {'years':q.years,'days':len(shared),'values':values,'trend':trend,'variance':{k:values[1][k]-values[0][k] for k in ['net','quantity','discount','customers','brands','therapies']}}
        except ValueError as e:raise HTTPException(422,str(e))

@app.post('/api/sessions/{sid}/snapshot')
def snapshot(sid:str,q:Query):
    s=session(sid)
    with s['lock']:
        if not s['files']:raise HTTPException(409,'No dataset loaded')
        try:
            return {'metadata':metadata(s),'filters':q.filters,'generated':time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime()),'pages':{p:s['dataset'].analytics(p,q.filters,q.exclude_partial,q.buckets) for p in ['overview','trends','products','customers','geography','commercial','supply-chain','pharma-risk','tax']}}
        except ValueError as e:raise HTTPException(422,str(e))

def session(sid):
    s=SESSIONS.get(sid) or load_remote(sid)
    if not s:raise HTTPException(404,'Session expired. Please upload your workbook again.')
    SESSIONS[sid]=s;s['_sid']=sid
    s['touched']=time.monotonic()
    return s

def metadata(s):return s['dataset'].metadata() | {'files':public_files(s['files'])}

@app.get('/api/health')
def health():return {'status':'ok'}

@app.post('/api/sessions')
def create():
    sid=uuid.uuid4().hex+uuid.uuid4().hex
    SESSIONS[sid]=new_state();SESSIONS[sid]['_sid']=sid;persist(sid,SESSIONS[sid])
    return {'id':sid}

@app.get('/api/schema')
@app.get('/api/sessions/{sid}/schema')
def schema(sid:str=''):return {'required':[FIELDS[k][0] for k in REQUIRED],'recommended':[FIELDS[k][0] for k in RECOMMENDED],'optional':[v[0] for k,v in FIELDS.items() if k not in REQUIRED+RECOMMENDED],'aliases':FIELDS}

class BlobFile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pathname:str=Field(max_length=500)
    filename:str=Field(min_length=1,max_length=255)
    size:int=Field(ge=1,le=MAX_UPLOAD)

def add_file(s,data,filename,replace=False,source_path=None):
    duplicate=next((f for f in s['files'] if f['hash']==hashlib.sha256(data).hexdigest()),None)
    if duplicate and not replace:raise HTTPException(409,'This file has already been loaded. Remove it first or choose Replace.')
    try: frame,info=ingest(data,filename)
    except ValueError as e:raise HTTPException(422,str(e))
    except Exception as e:raise HTTPException(422,'Workbook could not be processed. Check that sheets contain ordinary tabular XLSX data.') from e
    count=sum(len(f) for k,f in s['frames'].items() if not duplicate or k!=duplicate['id'])+len(frame)
    if count>600000:raise HTTPException(413,'Session limit is 600,000 rows. Remove a file before adding more.')
    old=[duplicate] if duplicate else []
    if BLOB:
        if not source_path:
            source_path=f"sessions/{s['_sid']}/uploads/{uuid.uuid4().hex}.xlsx"
            BLOB.put(source_path,data,access='private',content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        packed=io.BytesIO();frame.to_pickle(packed,compression='gzip')
        frame_path=f"sessions/{s['_sid']}/frames/{info['id']}.pkl.gz"
        BLOB.put(frame_path,packed.getvalue(),access='private',content_type='application/octet-stream')
        info|={'_source_path':source_path,'_frame_path':frame_path}
    frames=s['frames'].copy()
    if duplicate:frames.pop(duplicate['id'])
    frames[info['id']]=frame
    dataset=Dataset(list(frames.values()))
    s['dataset'].close();s['dataset']=dataset;s['frames']=frames
    s['files']=[f for f in s['files'] if not duplicate or f['id']!=duplicate['id']]+[info]
    persist(s['_sid'],s);delete_blobs(old)
    return metadata(s)

@app.post('/api/sessions/{sid}/files')
def upload(sid:str,file:UploadFile,replace:bool=False):
    s=session(sid)
    data=file.file.read(MAX_UPLOAD+1)
    if len(data)>MAX_UPLOAD:raise HTTPException(413,'Workbook exceeds the 100 MB upload limit.')
    with s['lock']:
        return add_file(s,data,file.filename or '',replace)

@app.post('/api/sessions/{sid}/blob-files')
def upload_blob(sid:str,file:BlobFile,replace:bool=False):
    if not BLOB:raise HTTPException(503,'Private upload storage is not configured.')
    prefix=f'sessions/{sid}/uploads/'
    if not file.pathname.startswith(prefix) or not file.pathname.lower().endswith('.xlsx'):raise HTTPException(400,'Invalid upload path.')
    s=session(sid)
    try:data=BLOB.get(file.pathname,access='private',use_cache=False).content
    except BlobNotFoundError:raise HTTPException(404,'Uploaded workbook was not found.')
    if len(data)!=file.size:raise HTTPException(400,'Uploaded workbook size does not match.')
    try:
        with s['lock']:return add_file(s,data,file.filename,replace,file.pathname)
    except Exception:
        BLOB.delete(file.pathname)
        raise

@app.get('/api/sessions/{sid}/metadata')
def meta(sid:str):
    s=session(sid)
    with s['lock']:return metadata(s)

@app.get('/api/sessions/{sid}/quality')
def quality(sid:str):
    s=session(sid)
    with s['lock']:return s['dataset'].quality(s['files']) if s['files'] else {'issues':[],'rows':0,'processed':0,'rejected':0}

@app.post('/api/sessions/{sid}/analytics/{page}')
def analytics(sid:str,page:str,q:Query):
    if page not in ('overview','trends','products','customers','geography','commercial','supply-chain','pharma-risk','tax','explorer'):raise HTTPException(404,'Unknown dashboard page')
    s=session(sid)
    with s['lock']:
        if not s['files']:raise HTTPException(409,'No dataset loaded')
        if not 0<q.buckets[0]<q.buckets[1]<q.buckets[2]:raise HTTPException(422,'Shelf-life thresholds must increase and be positive.')
        try:
            if page=='explorer':return s['dataset'].explorer(q.filters,q.search,q.sort,q.descending,q.page,q.size)
            return s['dataset'].analytics(page,q.filters,q.exclude_partial,q.buckets)
        except ValueError as e:raise HTTPException(422,str(e))

@app.post('/api/sessions/{sid}/export/csv')
def export_csv(sid:str,q:Query):
    s=session(sid)
    with s['lock']:
        if not s['files']:raise HTTPException(409,'No dataset loaded')
        try: rows=s['dataset'].explorer(q.filters,q.search,q.sort,q.descending,0,len(s['dataset'].df))['rows']
        except ValueError as e:raise HTTPException(422,str(e))
    output=io.StringIO()
    if rows:
        writer=csv.DictWriter(output,fieldnames=rows[0].keys());writer.writeheader()
        for row in rows:
            writer.writerow({k:"'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for k,v in row.items()})
    return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="filtered-sales.csv"'})

@app.delete('/api/sessions/{sid}/files/{fid}')
def remove(sid:str,fid:str):
    s=session(sid)
    with s['lock']:
        if fid not in s['frames']:raise HTTPException(404,'File not found')
        removed=next(f for f in s['files'] if f['id']==fid)
        s['frames'].pop(fid);s['files']=[f for f in s['files'] if f['id']!=fid]
        s['dataset'].close();s['dataset']=Dataset(list(s['frames'].values()))
        result=metadata(s);persist(sid,s);delete_blobs([removed])
    if not s['files']:destroy(sid,remote=True)
    return result

@app.delete('/api/sessions/{sid}')
def clear(sid:str):destroy(sid,remote=True);return {'cleared':True}

@app.get('/api/cleanup')
def cleanup(request:Request):
    secret=os.getenv('CRON_SECRET')
    if not secret or request.headers.get('authorization')!=f'Bearer {secret}':raise HTTPException(401,'Unauthorized')
    if not BLOB:return {'cleared':0}
    cutoff=datetime.now(timezone.utc).timestamp()-REMOTE_TTL;cleared=0
    for item in BLOB.iter_objects(prefix='sessions/'):
        if item.pathname.endswith('/manifest.json') and item.uploaded_at.timestamp()<cutoff:
            destroy(item.pathname.split('/')[1],remote=True);cleared+=1
    return {'cleared':cleared}
