"""Read server-only Joolan settings without executing env-file contents."""
import os
from pathlib import Path

ENV_FILE=Path(__file__).resolve().parent/'.env'

def settings(path=None,environ=None):
    values={};path=Path(path or ENV_FILE);environ=os.environ if environ is None else environ
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            if line.startswith('export '):line=line[7:].strip()
            if '=' not in line:continue
            name,value=line.split('=',1);name=name.strip();value=value.strip()
            if name not in ('JOOLAN_API_KEY','JOOLAN_ENSEIGNE'):continue
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
            else:value=value.split(' #',1)[0].rstrip()
            values[name]=value
    return {name:environ.get(name,values.get(name,default)).strip() for name,default in
            [('JOOLAN_API_KEY',''),('JOOLAN_ENSEIGNE','legend73')]}

def credentials():
    value=settings();key=value['JOOLAN_API_KEY']
    if not key or key.lower() in ('your_key_here','replace_me','paste_key_here'):
        raise ValueError('Set JOOLAN_API_KEY in backend-ai/.env, then retry. Keep the key out of the browser and chat.')
    return key,value['JOOLAN_ENSEIGNE']

def configured():
    try:credentials();return True
    except ValueError:return False
