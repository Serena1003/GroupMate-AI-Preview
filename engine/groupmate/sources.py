"""Teacher-private source extraction; extracted text never implies a verified case."""
import base64
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from .domain import DomainError,identifier

MAX_BYTES=20*1024*1024
class Sources:
    def __init__(self,app):self.app=app
    def get(self,token,source_id):
        with self.app.lock:
            value=self.app._get(source_id);self.app._teacher(token,value['owner'])
            if value.get('type')!='SOURCE_DOCUMENT':raise DomainError('SOURCE_REQUIRED')
            return value
    def list(self,token):
        with self.app.lock:
            actor=self.app._teacher(token)
            return [{k:s[k] for k in ['id','filename','status','sha256','at','page_range','character_count']} for s in self.app._all('source') if s['owner']==actor['actor_id']]
    def upload(self,token,filename,encoded,first=1,last=1):
        with self.app.lock:actor=self.app._teacher(token)
        if not isinstance(filename,str) or len(filename)>240 or not isinstance(encoded,str) or len(encoded)>MAX_BYTES*4//3+8:raise DomainError('SOURCE_SIZE_OR_NAME')
        try:raw=base64.b64decode(encoded,validate=True)
        except (ValueError,TypeError):raise DomainError('SOURCE_BASE64_INVALID')
        if not raw or len(raw)>MAX_BYTES:raise DomainError('SOURCE_SIZE_INVALID')
        suffix=Path(filename).suffix.lower();pages=[]
        if type(first) is not int or type(last) is not int or not 1<=first<=last<=10000 or last-first>99:raise DomainError('SOURCE_PAGE_RANGE')
        try:
            if suffix=='.pdf':
                executable=shutil.which('pdftotext')
                if not executable:raise DomainError('PDF_PARSER_UNAVAILABLE')
                if not raw.startswith(b'%PDF-'):raise DomainError('PDF_PARSE_FAILED')
                with tempfile.TemporaryDirectory(prefix='groupmate-source-') as folder:
                    path=Path(folder)/'source.pdf';path.write_bytes(raw)
                    result=subprocess.run([executable,'-f',str(first),'-l',str(last),'-layout',str(path),'-'],capture_output=True,timeout=20)
                if result.returncode:raise DomainError('PDF_PARSE_FAILED')
                text=result.stdout.decode('utf-8');parts=text.split('\f')
                if parts and not parts[-1].strip():parts.pop()
                pages=[(first+i,t.strip()) for i,t in enumerate(parts)]
            elif suffix in ['.txt','.md','.csv']:
                pages=[(None,raw.decode('utf-8-sig'))]
            elif suffix=='.docx':
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    info=archive.getinfo('word/document.xml')
                    if info.file_size>2*1024*1024:raise DomainError('SOURCE_TEXT_TOO_LARGE')
                    tree=ET.fromstring(archive.read(info))
                ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                pages=[(None,'\n'.join(''.join(p.itertext()) for p in tree.iter(ns+'p')))]
            else:raise DomainError('SOURCE_FORMAT_UNSUPPORTED')
        except (UnicodeError,zipfile.BadZipFile,KeyError,ET.ParseError,subprocess.TimeoutExpired,OSError):raise DomainError('SOURCE_PARSE_FAILED')
        if not any(text.strip() for _,text in pages):raise DomainError('SOURCE_NO_EXTRACTABLE_TEXT')
        if sum(len(t) for _,t in pages)>160000:raise DomainError('SOURCE_TEXT_TOO_LARGE_SELECT_FEWER_PAGES')
        value={'id':identifier('source'),'type':'SOURCE_DOCUMENT','owner':actor['actor_id'],'filename':Path(filename).name,'sha256':hashlib.sha256(raw).hexdigest(),'status':'TEXT_EXTRACTED_NOT_CASE_VERIFIED','page_range':[first,last] if suffix=='.pdf' else None,'at':self.app.clock(),'character_count':sum(len(t) for _,t in pages),'spans':[{'span_id':identifier('span'),'pdf_page':page,'text':text} for page,text in pages]}
        with self.app.transaction():self.app._put(value,'source')
        return value
    def search(self,token,query):
        with self.app.lock:self.app._teacher(token)
        if not isinstance(query,str) or not 2<=len(query.strip())<=300:raise DomainError('SEARCH_QUERY_INVALID')
        # Fixed public endpoint; user-provided URLs are not fetched server-side.
        url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query)
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'GroupMate-Classroom/0.3'}),timeout=12) as response:data=response.read(512000)
            root=ET.fromstring(data)
            items=[]
            for node in root.findall('./channel/item')[:8]:
                link=node.findtext('link','')
                if urllib.parse.urlparse(link).scheme not in ['http','https']:continue
                items.append({'title':node.findtext('title',''),'url':link,'snippet':node.findtext('description',''),'status':'SEARCH_SNIPPET_NOT_FULLTEXT_VERIFIED'})
            if not items:raise DomainError('SEARCH_NO_RESULTS')
            return {'query':query,'items':items,'retrieved_at':self.app.clock(),'limitations':['仅搜索摘要；尚未读取或核验案例全文。请选择来源并上传/粘贴合法可用材料。']}
        except DomainError:raise
        except Exception:raise DomainError('SEARCH_UNAVAILABLE_USE_LINKS_OR_UPLOAD')
