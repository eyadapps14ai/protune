import sys,unittest,tempfile,io,json,importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class WSGITests(unittest.TestCase):
 def test_adapter(self):
  with tempfile.TemporaryDirectory() as folder:
   server.DB=Path(folder)/'test.sqlite';server.init();wsgi=importlib.import_module('wsgi')
   results=[]
   env={'REQUEST_METHOD':'GET','PATH_INFO':'/api/config','wsgi.input':io.BytesIO(b'')}
   payload=b''.join(wsgi.application(env,lambda status,headers:results.append((status,headers))))
   self.assertEqual(results[0][0],'200 OK');self.assertEqual(json.loads(payload)['businessName'],'Protune Auto Services')
   env['PATH_INFO']='/';body=b''.join(wsgi.application(env,lambda *args:None));self.assertIn(b'Protune',body)
   env['REQUEST_METHOD']='DELETE';results=[];wsgi.application(env,lambda status,headers:results.append(status));self.assertTrue(results[0].startswith('405'))
