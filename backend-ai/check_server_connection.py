"""Check configured API access without exposing key values or upstream URLs."""
import re
import server_credentials
from joolan_client import Client,ExportError

if __name__=='__main__':
 key,enseigne=server_credentials.credentials();client=Client('https://go.joolan.com',enseigne,key)
 try:
  records=client.query('SELECT 1 AS connection_test')
  print('Read-only query connection:',bool(records),flush=True)
  records=client.query('SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_KEY FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION')
  print('Live schema metadata fields:',len(records),flush=True)
 except Exception as error:
  message=str(error).replace(key,'[hidden]')
  message=re.sub(r'https?://\S+','[upstream URL hidden]',message)
  print('Connection check:',type(error).__name__,'HTTP',getattr(error,'http_status','unknown'),message[:600],flush=True)
 finally:client.close()
