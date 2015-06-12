import sys
import os
import re
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

with open( "service.pid", "w" ) as f:
	f.write( str(os.getpid()) )

if sys.argv[1:]:
    port = int(sys.argv[1])
else:
    port = 8900

ip = os.environ['WELDER_SITE_URL']
m = re.match( r'^.+//([^:]+)', ip )
if m:
	ip = m.group(1)

html = ""
html += "<h1>This is a web service running on port: "+port+"</h1>\n"
html += "<a href='http://"+ip+":"+port+"'>Go to it now</a>\n"

with open( "../results/index.html", "w" ) as f:
	f.write( html )

class Handler(BaseHTTPRequestHandler):
	def do_GET(self):
		self.send_response(200)
		self.send_header('Content-type','text/html')
		self.end_headers()
		self.wfile.write( "The service is up" )


httpd = HTTPServer( ('0.0.0.0', port), Handler )

sa = httpd.socket.getsockname()
print "Serving HTTP on", sa[0], "port", sa[1], "..."
httpd.serve_forever()