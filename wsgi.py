"""WSGI adapter for deployment behind a production WSGI server and HTTPS proxy.
Run one worker with multiple threads: sessions and rate limits are process-local.
"""
from io import BytesIO
from email.message import Message
from http import HTTPStatus
import server
server.init()

def application(environ,start_response):
    method=environ.get('REQUEST_METHOD','GET')
    if method not in ('GET','POST'):
        start_response('405 Method Not Allowed',[('Content-Type','application/json'),('Allow','GET, POST')])
        return [b'{"error":"Method not allowed"}']
    try: length=int(environ.get('CONTENT_LENGTH') or 0)
    except ValueError:length=-1
    if length<0 or length>100000:
        start_response('413 Content Too Large',[('Content-Type','application/json')])
        return [b'{"error":"Request body is too large"}']
    handler=server.Handler.__new__(server.Handler)
    handler.command=method
    handler.path=environ.get('PATH_INFO','/')+('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else '')
    handler.request_version='HTTP/1.1';handler.requestline=method+' '+handler.path+' HTTP/1.1'
    handler.client_address=(environ.get('REMOTE_ADDR','unknown'),0)
    handler.headers=Message()
    for key,value in environ.items():
        if key.startswith('HTTP_'):handler.headers[key[5:].replace('_','-')]=value
    handler.headers['Content-Type']=environ.get('CONTENT_TYPE','')
    handler.headers['Content-Length']=str(length)
    handler.rfile=BytesIO(environ['wsgi.input'].read(length) if length else b'')
    handler.wfile=BytesIO()
    if method=='GET':handler.do_GET()
    else:handler.do_POST()
    head,body=handler.wfile.getvalue().split(b'\r\n\r\n',1)
    lines=head.decode('latin-1').split('\r\n')
    status=lines[0].split(' ',1)[1]
    headers=[tuple(line.split(': ',1)) for line in lines[1:] if ': ' in line]
    headers=[(k,v) for k,v in headers if k.lower() not in ('server','connection','transfer-encoding')]
    start_response(status,headers)
    return [body]
