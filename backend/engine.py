import io, json, hashlib, zipfile, uuid, calendar
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, date
import pandas as pd
import numpy as np
import openpyxl
import duckdb
from functools import lru_cache
try: from backend.schema import *
except ImportError: from schema import *

CENT = Decimal('0.01')
TOLERANCE = Decimal('0.02')

def number(value):
    if value is None or str(value).strip() == '': return None
    try:
        text = str(value).strip().replace(',', '')
        if text.startswith('(') and text.endswith(')'): text = '-' + text[1:-1]
        result = Decimal(text)
        return result if result.is_finite() and abs(result) < Decimal('1e15') else None
    except InvalidOperation: return None

def date_value(value):
    if isinstance(value, (date, datetime)): return pd.Timestamp(value)
    if isinstance(value, (float,int)) and 1 < value < 100000:
        return pd.Timestamp(openpyxl.utils.datetime.from_excel(value))
    for fmt in ('%d-%m-%Y','%Y-%m-%d','%d/%m/%Y','%Y-%m-%d %H:%M:%S'):
        try: return pd.Timestamp(datetime.strptime(str(value).strip(),fmt))
        except (ValueError,TypeError): pass
    return pd.NaT

def ingest(data, filename):
    if not filename.lower().endswith('.xlsx'): raise ValueError('Only .xlsx workbooks are supported.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > 800_000_000: raise ValueError('Workbook expands beyond the 800 MB processing limit.')
        book = openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    except (zipfile.BadZipFile,KeyError, OSError) as e: raise ValueError('This is not a readable XLSX workbook.') from e
    file_id = uuid.uuid4().hex
    frames, sheets, issues = [], [], []
    def issue(kind, count, field='', examples=None):
        if count: issues.append({'kind':kind,'count':int(count),'field':field,'examples':examples or []})
    for sheet in book:
        rows = sheet.iter_rows(values_only=True)
        raw_headers = next(rows, ())
        headers = [ALIASES.get(normalized(h), 'source:' + str(h)) for h in raw_headers]
        missing = [k for k in REQUIRED if k not in headers]
        if missing:
            sheets.append({'name':sheet.title,'status':'Skipped','reason':'Missing required fields: ' + ', '.join(LABELS[k] for k in missing)})
            continue
        if len(headers) != len(set(headers)):
            sheets.append({'name':sheet.title,'status':'Rejected','reason':'Multiple headings map to the same field.'}); continue
        values = [r for r in rows if any(v is not None for v in r)]
        frame = pd.DataFrame(values,columns=headers)
        frame['_source_row'] = np.arange(2,len(frame)+2)
        frame['_source_sheet'] = sheet.title
        frames.append(frame)
        sheets.append({'name':sheet.title,'status':'Imported','rows':len(frame)})
    book.close()
    if not frames: raise ValueError('Dataset cannot be analyzed. ' + '; '.join(s['name'] + ': ' + s['reason'] for s in sheets))
    df = pd.concat(frames,ignore_index=True)
    present = set(df.columns)
    processed = len(df)
    # Workbook-local date cache is released after ingestion; repeated date strings are common.
    parse_date = lru_cache(maxsize=10000)(date_value)
    for c in REQUIRED + RECOMMENDED:
        if c not in present: issue('Recommended field unavailable',processed,LABELS[c])
    reject = pd.Series(False,index=df.index)
    for c in present:
        if c in NUMBERS:
            original = df[c].copy()
            df[c] = original.map(number)
            bad = df[c].isna()
            issue('Missing or invalid numeric values',bad.sum(),LABELS[c])
            if c in REQUIRED: reject |= bad
        elif c in DATES:
            df[c] = df[c].map(parse_date)
            issue('Missing or invalid dates',df[c].isna().sum(),LABELS[c])
            if c == 'date': reject |= df[c].isna()
        else:
            df[c] = df[c].map(lambda v: None if pd.isna(v) or str(v).strip()=='' else str(v).strip())
            if c in FIELDS: issue('Missing values',df[c].isna().sum(),LABELS[c])
            if c in REQUIRED: reject |= df[c].isna()
    issue('Required values missing; rows rejected',reject.sum())
    df = df.loc[~reject].copy()
    if df.empty: raise ValueError('Dataset cannot be analyzed: every transaction has missing or invalid required values.')
    issue('Potential duplicate records',df.duplicated(subset=[c for c in present if not c.startswith('_')]).sum())
    issue('Repeated invoice IDs (may represent legitimate line items)',df['invoice'].duplicated().sum(),'Invoice Number')
    def relation(title, cols, fn):
        if not all(c in present for c in cols): return
        bad = []
        for idx, values in zip(df.index,df[cols].itertuples(index=False,name=None)):
            if any(v is None for v in values): continue
            if abs(fn(*values).quantize(CENT,rounding=ROUND_HALF_UP)) > TOLERANCE: bad.append(idx)
        issue(title,len(bad),examples=df.loc[bad[:5],['_source_sheet','_source_row','invoice']].to_dict('records'))
    relation('Gross sales formula mismatch',['gross','quantity','rate_before'],lambda g,q,r:g-q*r)
    relation('Net sales formula mismatch',['net','quantity','rate_after'],lambda n,q,r:n-q*r)
    relation('Discount formula mismatch',['discount_source','net','gross'],lambda d,n,g:d-(n-g))
    for tax in ('cgst','sgst','igst','utgst'):
        relation(tax.upper()+' formula mismatch',[tax,'net',tax+'_rate'],lambda t,n,r:t-n*r/100)
    for c in ('quantity','gross','net'):
        issue('Negative values retained for review',sum(v<0 for v in df[c]),LABELS[c])
    if {'mrp','rate_before'} <= present:
        issue('MRP below pre-discount rate',sum(a is not None and b is not None and a<b for a,b in zip(df.mrp,df.rate_before)))
    for c in NUMBERS:
        if c not in df: df[c] = None
        if c in MONEY:
            df[c] = df[c].map(lambda v: None if v is None else int((v*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))).astype('Int64')
        else: df[c] = pd.to_numeric(df[c],errors='coerce').astype(float)
    for c in DATES:
        if c not in df: df[c] = pd.NaT
    for c in FIELDS:
        if c not in df: df[c] = None
    df['year'] = df.date.dt.year.astype(str)
    fy = df.date.dt.year - (df.date.dt.month < 4).astype(int)
    df['fiscal_year'] = fy.astype(str) + '-' + ((fy+1)%100).astype(str).str.zfill(2)
    df['month'] = df.date.dt.strftime('%B')
    df['month_number'] = df.date.dt.month
    df['period'] = df.date.dt.strftime('%Y-%m')
    df['quarter'] = 'Q' + df.date.dt.quarter.astype(str)
    df['fiscal_quarter'] = 'Q' + (((df.date.dt.month-4)%12)//3+1).astype(str)
    issue('Source fiscal year disagrees with invoice date',((df.source_year.notna()) & (df.source_year != df.fiscal_year)).sum())
    pairs = {'po_days':('date','po_date'),'delivery_days':('delivery_date','order_date'),'lr_days':('lr_date','date'),'age_days':('date','mfg_date'),'shelf_days':('expiry_date','date')}
    for key,(end,start) in pairs.items():
        df[key] = (df[end]-df[start]).dt.days.astype(float)
        issue('Date sequence anomaly', (df[key]<0).sum(),key)
        if key!='shelf_days': df.loc[df[key]<0,key] = np.nan
    issue('Expiry before manufacture',(df.expiry_date < df.mfg_date).sum())
    df['discount'] = df.gross-df.net
    df['tax'] = df[['cgst','sgst','igst','utgst']].sum(axis=1,min_count=4).astype('Int64')
    df['_source_file'], df['_import_batch'] = filename,file_id
    info = {'id':file_id,'name':filename,'size':len(data),'hash':hashlib.sha256(data).hexdigest(),'rows':len(df),'sheets':sheets,'issues':issues,'processed':processed,'rejected':int(reject.sum()),'fields':sorted(present)}
    return df,info

def clean(value):
    return json.loads(json.dumps(value,default=lambda v:float(v) if isinstance(v,(Decimal,np.number)) else str(v),allow_nan=False))

class Dataset:
    def __init__(self, frames):
        self.df = pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
        self.db = duckdb.connect()
        if not self.df.empty: self.db.register('sales',self.df)
        self.cache = {}
    def close(self): self.db.close(); self.df = pd.DataFrame(); self.cache.clear()
    def where(self, filters, exclude_partial=False):
        parts,params = [],[]
        for k,values in filters.items():
            if k not in DIMENSIONS: raise ValueError('Unknown filter: '+k)
            if values:
                parts.append('"'+k+'" IN ('+','.join('?' for _ in values)+')'); params.extend(values)
        if exclude_partial and self.partial(): parts.append('period <> ?'); params.append(self.partial()['period'])
        return (' WHERE '+' AND '.join(parts) if parts else ''),params
    def query(self,sql,params=None):
        cur=self.db.execute(sql,params or [])
        return [dict(zip([c[0] for c in cur.description],r)) for r in cur.fetchall()]
    def partial(self):
        if self.df.empty:return None
        latest=self.df.date.max(); current=self.df[self.df.period==latest.strftime('%Y-%m')]
        counts=self.df.groupby('period').size(); days=self.df.groupby('period').date.nunique()
        if latest.day<calendar.monthrange(latest.year,latest.month)[1] and (len(counts)==1 or len(current)<counts.iloc[:-1].median()*.75 or current.date.nunique()<days.iloc[:-1].median()*.75):
            return {'period':latest.strftime('%Y-%m'),'last_date':latest.strftime('%d %b %Y'),'active_days':int(current.date.nunique()),'rows':len(current),'reason':'Invoice coverage ends before month-end; transaction/day coverage may be incomplete.'}
        return None
    def metadata(self):
        if self.df.empty:return {'rows':0,'options':{}}
        return {'rows':len(self.df),'start':self.df.date.min().strftime('%d %b %Y'),'end':self.df.date.max().strftime('%d %b %Y'),'options':{k:sorted(self.df[k].dropna().unique().tolist()) for k in DIMENSIONS},'partial':self.partial(),'constants':[LABELS.get(c,c) for c in FIELDS if self.df[c].nunique()==1]}
    def quality(self,files):
        issues=[dict(i,file=f['name']) for f in files for i in f['issues']]
        for c in ['product','product_group','therapy','classification','brand','mother_brand','manufacturing','storage']:
            conflicts=self.df.groupby('material')[c].nunique()
            ids=conflicts[conflicts>1].index.tolist()
            if ids:issues.append({'kind':'Material Master Conflict','field':LABELS[c],'count':len(ids),'examples':ids[:8]})
        return {'processed':sum(f['processed'] for f in files),'rejected':sum(f['rejected'] for f in files),'rows':len(self.df),'issues':issues,'tolerance':'₹0.02 per row; decimal ROUND_HALF_UP to paise. Negative discounts are source reductions; sales discount cost is gross minus net.'}
    @staticmethod
    def measures():
        return '''count(*) AS "rows", sum(net)/100.0 net, sum(gross)/100.0 gross, sum(discount)/100.0 discount,
        sum(quantity) quantity, count(distinct invoice) invoices, count(distinct customer) customers,
        count(distinct material) materials, count(distinct brand) brands, count(distinct therapy) therapies,
        count(distinct delivery_document) shipments,
        CASE WHEN count(tax)=count(*) THEN sum(tax)/100.0 END tax,
        100.0*sum(discount)/nullif(sum(gross),0) discount_pct,
        sum(net)/100.0/nullif(count(distinct invoice),0) avg_invoice,
        sum(net)/100.0/nullif(sum(quantity),0) realized_price'''
    def aggregate(self,dimension,where,params,metric='net',limit=15):
        return self.query(f'SELECT "{dimension}" AS name, {self.measures()} FROM sales {where} GROUP BY 1 ORDER BY {metric} DESC NULLS LAST LIMIT {int(limit)}',params)
    def analytics(self,page,filters,exclude_partial=False,buckets=(180,365,548)):
        key=json.dumps([page,filters,exclude_partial,buckets],sort_keys=True)
        if key in self.cache:return self.cache[key]
        where,params=self.where(filters,exclude_partial)
        kpi=self.query('SELECT '+self.measures()+' FROM sales'+where,params)[0]
        trend=self.query('SELECT period AS name, '+self.measures()+' FROM sales'+where+' GROUP BY 1 ORDER BY 1',params)
        history={r['name']:r for r in trend}
        for i,r in enumerate(trend):
            dt=datetime.strptime(r['name'],'%Y-%m'); prev=(dt.replace(day=1)-pd.Timedelta(days=1)).strftime('%Y-%m'); prior=history.get(prev)
            r['mom']=100*(r['net']/prior['net']-1) if prior and prior['net'] else None
            yoy=history.get(f'{dt.year-1}-{dt.month:02}')
            r['yoy']=100*(r['net']/yoy['net']-1) if yoy and yoy['net'] else None
            rolling=[history.get((pd.Timestamp(dt)-pd.DateOffset(months=n)).strftime('%Y-%m')) for n in (0,1,2)]
            r['rolling']=sum(t['net'] for t in rolling) if all(rolling) else None
        dimensions={'overview':['therapy','division','brand','customer_name'],'trends':[], 'products':['therapy','brand','classification','portfolio','product','mother_brand','material','therapy1','material_group'], 'customers':['customer_name','customer_group'], 'geography':['plant_name','district','city','office','group','ship_city'],'commercial':['brand','customer_name','therapy','plant_name'],'supply-chain':['manufacturing','transporter','storage'],'pharma-risk':['storage','brand'],'tax':['payment','plant_name']}.get(page,[])
        groups={d:self.aggregate(d,where,params,limit=100 if page in ('products','customers','commercial') else 15) for d in dimensions}
        distributions={}
        durations={}
        for c in ['po_days','delivery_days','lr_days','shelf_days','age_days'] if page in ('supply-chain','pharma-risk') else []:
            durations[c]=self.query(f'SELECT avg({c}) average, median({c}) median, quantile_cont({c},0.9) p90, count({c}) AS valid FROM sales'+where,params)[0]
            distributions[c]=self.query(f'SELECT floor({c}/30)*30 AS name, count(*) quantity, sum(net)/100.0 net FROM sales'+where+(' AND ' if where else ' WHERE ')+f'{c} IS NOT NULL GROUP BY 1 ORDER BY 1',params)
        extra={}
        if page=='pharma-risk':
            a,b,c=buckets
            extra['shelf']=self.query(f"SELECT CASE WHEN shelf_days<0 THEN 'Expired at sale' WHEN shelf_days<{a} THEN '< {a} days' WHEN shelf_days<={b} THEN '{a}–{b} days' WHEN shelf_days<={c} THEN '{b+1}–{c} days' WHEN shelf_days>{c} THEN '{c+1}+ days' ELSE 'Unavailable' END AS name, sum(net)/100.0 net, sum(quantity) quantity FROM sales"+where+' GROUP BY 1',params)
            extra['risk']=self.query(f"SELECT sum(CASE WHEN shelf_days<{a} THEN net END)/100.0 near_expiry, sum(CASE WHEN shelf_days<{a} THEN quantity END) near_quantity, sum(CASE WHEN lower(storage) LIKE '%refrigerat%' OR lower(storage) LIKE '%2-8%' THEN net END)/100.0 cold_revenue FROM sales"+where,params)[0]
            extra['brand_shelf']=self.query('SELECT brand AS name, avg(shelf_days) AS days, sum(net)/100.0 net FROM sales'+where+' GROUP BY 1 ORDER BY days',params)
            extra['risk']['cold_pct']=100*extra['risk']['cold_revenue']/kpi['net'] if extra['risk']['cold_revenue'] is not None and kpi['net'] else None
            extra['risk']['near_pct']=100*extra['risk']['near_expiry']/kpi['net'] if extra['risk']['near_expiry'] is not None and kpi['net'] else None
            extra['expiry_matrix']=self.query(f'SELECT brand AS name, sum(CASE WHEN shelf_days<{a} THEN net ELSE 0 END)/100.0 risk, sum(net)/100.0 net, avg(shelf_days) AS days FROM sales'+where+' GROUP BY 1 ORDER BY risk DESC',params)
        if page=='commercial':
            distributions['discount_rate']=self.query('SELECT floor(100.0*discount/nullif(gross,0)/5)*5 AS name, count(*) quantity FROM sales'+where+' GROUP BY 1 ORDER BY 1',params)
            extra['prices']=self.query('SELECT sum(mrp*quantity)/nullif(sum(quantity),0) mrp, sum(rate_before*quantity)/nullif(sum(quantity),0) AS before, sum(rate_after*quantity)/nullif(sum(quantity),0) AS after FROM sales'+where,params)[0]
            points=[r for r in groups['brand'] if r['net'] is not None and r['discount_pct'] is not None]
            if points:
                sales_median=float(np.median([r['net'] for r in points]));discount_median=float(np.median([r['discount_pct'] for r in points]))
                extra['quadrants']=[dict(r,quadrant=('High' if r['net']>=sales_median else 'Low')+' sales / '+('high' if r['discount_pct']>=discount_median else 'low')+' discount') for r in points]
                extra['thresholds']={'sales':sales_median,'discount':discount_median}
                x=np.array([r['quantity'] for r in points]);y=np.array([r['discount_pct'] for r in points])
                if len(x)>1 and np.ptp(x)>0:
                    slope,intercept=np.polyfit(x,y,1);extra['regression']=[{'name':'Trend','quantity':float(v),'discount_pct':float(slope*v+intercept)} for v in (x.min(),x.max())]
        if page=='tax':
            extra['taxes']=self.query('SELECT '+','.join(f'CASE WHEN count({t})=count(*) THEN sum({t})/100.0 END {t}' for t in ('cgst','sgst','igst','utgst'))+' FROM sales'+where,params)[0]
            extra['monthly_tax']=self.query('SELECT period AS name, '+','.join(f'sum({t})/100.0 {t}' for t in ('cgst','sgst','igst','utgst'))+' FROM sales'+where+' GROUP BY 1 ORDER BY 1',params)
            extra['plant_tax']=self.query('SELECT plant_name AS name, '+','.join(f'sum({t})/100.0 {t}' for t in ('cgst','sgst','igst','utgst'))+' FROM sales'+where+' GROUP BY 1 ORDER BY 1',params)
        if page=='trends':
            extra['yearly_months']=self.query('SELECT year, month_number, month, '+self.measures()+' FROM sales'+where+' GROUP BY 1,2,3 ORDER BY 2,1',params)
            extra['fiscal_totals']=self.query('SELECT fiscal_year AS name, '+self.measures()+' FROM sales'+where+' GROUP BY 1 ORDER BY 1',params)
        if page=='customers' and len(groups.get('customer_name',[]))==1:
            extra['customer_detail']={'ids':self.query('SELECT DISTINCT customer FROM sales'+where,params),'brand':self.aggregate('brand',where,params,limit=1),'therapy':self.aggregate('therapy',where,params,limit=1),'plant':self.aggregate('plant_name',where,params,limit=1)}
        if page=='geography':
            extra['district_therapy']=self.query('SELECT district AS name,therapy, sum(net)/100.0 net, sum(quantity) quantity,count(distinct invoice) invoices FROM sales'+where+' GROUP BY 1,2 ORDER BY 1',params)
        matrix_pair={'customers':('customer_name','therapy'),'geography':('plant_name','ship_city'),'supply-chain':('transporter','storage')}.get(page)
        if matrix_pair:
            x,y=matrix_pair
            extra['matrix']=self.query(f'SELECT "{x}" x,"{y}" y,sum(net)/100.0 net FROM sales'+where+' GROUP BY 1,2 ORDER BY net DESC LIMIT 150',params)
        insights=[]
        if trend:
            peak=max(trend,key=lambda r:r['net']); insights.append(peak['name']+' is the highest net-sales month in this selection.')
        if groups:
            d=next(iter(groups)); ranking=groups[d]
            if ranking and kpi['net']:insights.append(f"{ranking[0]['name'] or 'Unspecified'} contributes {ranking[0]['net']/kpi['net']*100:.1f}% of selected net sales.")
        result=clean({'kpis':kpi,'trend':trend,'groups':groups,'durations':durations,'distributions':distributions,'extra':extra,'insights':insights})
        if len(self.cache)>100:self.cache.clear()
        self.cache[key]=result
        return result
    def explorer(self,filters,search='',sort='date',descending=True,page=0,size=50):
        if sort not in self.df.columns:raise ValueError('Unknown sort field')
        sort=sort.replace('"','""')
        where,params=self.where(filters)
        if search:
            where+=(' AND ' if where else ' WHERE ')+"concat_ws(' ',invoice,customer_name,material,product,brand,batch) ILIKE ?"
            params.append('%'+search+'%')
        total=self.query('SELECT count(*) total FROM sales'+where,params)[0]['total']
        rows=self.query('SELECT * FROM sales'+where+f' ORDER BY "{sort}" '+('DESC' if descending else 'ASC')+' LIMIT ? OFFSET ?',params+[size,page*size])
        for row in rows:
            for c,v in list(row.items()):
                if c in MONEY+['discount','tax'] and v is not None:row[c]=v/100
                elif isinstance(v,(datetime,date)):row[c]=v.strftime('%Y-%m-%d')
                elif isinstance(v,float) and not np.isfinite(v):row[c]=None
        return {'total':total,'rows':rows}




