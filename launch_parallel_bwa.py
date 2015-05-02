import os
import urlparse
import urllib
import httplib
import ssl
import json
import re
from urllib2 import HTTPError
from httplib import BadStatusLine

# This will become the welder api
def expand_vars(s, level=1):
	state = "str"
	n = []
	cv = ''
	stack = inspect.currentframe()
	for i in range(level):
		stack = stack.f_back
	var = dict(globals().items() + stack.f_locals.items())
	i = 0
	while i < len(s):
		if state == "str":
			if i + 1 < len(s) and s[i] == "$" and s[i + 1] == "{" :
				state = "var"
				cv = ''
				i += 1
			else:
				n.append(s[i])
		elif state == "var":
			if(s[i] == "}"):
				parts = cv.split(".")
				co = None
				for part in parts:
					if not co:
						co = var[part]
					else:
						co = getattr(co, part)
				n.append(str(co))
				state = "str"
			else:
				cv += s[i]
		i+=1
	return "".join( n )


def http(url, params={}, data="", action="GET", headers={}, progressCallback=None, toFilename=None, retrys=0, retryDelay=5, returnHeaders=False):
	attempts = 0
	while attempts <= retrys:
		try:
			parsed = urlparse.urlparse(url)
			if url.startswith("https://"):
				# WARNING: This does not do any checking of the SSL certificate
				h = httplib.HTTPSConnection(parsed.netloc)
			else:
				h = httplib.HTTPConnection(parsed.netloc)

			# The URL may have a query string which is combined with the params
			if parsed.query:
				inlineQueryAsDict = urlparse.parse_qs(parsed.query)

				# FLATTEN because parse_qs annoyingly returns a list for each value
				for k in inlineQueryAsDict:
					inlineQueryAsDict[k] = inlineQueryAsDict[k][0]

				# UNION the sent in params with the query string
				params = dict(params.items() + inlineQueryAsDict.items())

			headers["Content-Length"] = str(len(data))
			headers["User-Agent"] = "fake browser"
			if data and data != "" and ("Content-Type" not in headers) and not(action == "GET" or action == "DELETE"):
				raise HTTPError(url, 0, "Trying to send data without Content-Type to url:" + url, None, None)

			paramString = ""
			if params:
				paramString = "?"+urllib.urlencode(params).encode('utf-8')

			try:
				escapePath = urllib.quote(parsed.path).encode('utf-8')
				h.request(action, escapePath + paramString, data, headers)
				resp = h.getresponse()
			except ssl.SSLError as e:
				raise HTTPError(url, 406, "SSL failed: " + url + ", " + str(e), None, None)
			except BadStatusLine as e:
				raise HTTPError(url, 404, "URL returned bad status:" + url + ", " + str(e), None, None)
			except Exception as e:
				raise HTTPError(url, 0, "Can not reach url: " + url + ", " + str(e), None, None)

#			if resp.status != 200:
#				raise HTTPError(url, resp.status, "Return code not 200", None, None)

			readData = ""
			f = None
			try:
				if toFilename and resp.status == 200:
					try:
						os.makedirs('/'.join(toFilename.split('/')[:-1]))
					except:
						pass
					f = open(toFilename, "wb")

				totalSize = int( resp.getheader("content-length", 0))
				blockSize = 1024 * 1024
				count = 0
				lengthRead = 0
				while True:
					chunk = resp.read(blockSize)
					if chunk and progressCallback:
						lengthRead += len(chunk)
						progressCallback(url, lengthRead, totalSize)
					if not chunk:
						break
					if f:
						f.write(chunk)
					else:
						readData += chunk

					count += 1
			except Exception as e:

				raise HTTPError(url, resp.status, "Bad read or write: " + url + " " + str(e), None, None)
			finally:
				if f is not None:
					f.close()

			if resp.status != 200:
				raise HTTPError(url, resp.status, readData, None, None)

			if returnHeaders:
				replyHeaders = {}
				for k, v in resp.getheaders():
					replyHeaders[k.lower()] = v
				return readData, replyHeaders
			else:
				return readData

		except Exception as e:
			if attempts >= retrys:
				raise e
			attempts += 1
			if retryDelay:
				time.sleep(retryDelay)

	# We should never get here, but in case we throw an exception
	raise HTTPError(url, 0, "http fatal: " + url, None, None)

def welder_run_task_add( task_object ):
	key = os.environ['WELDER_KEY']
	run_id = os.environ['WELDER_RUN_ID']
	project = os.environ['WELDER_PROJECT']
	url = os.environ['WELDER_URL'] + "/api/v1/projects/"+project+"/runs/"+run_id+"/tasks"
	ret = http( url, data=json.dumps(task_object), action="POST", headers={'Content-Type':'application/json','welder-auth':key} )
	return json.loads(ret)['taskFolder']



"""
params is expected to be like:
{
	"reference_genome": "$DATASETS/reference_genomes/bwa-0.7.10-ecoli.tar.gz",
	"fastq_files[]": [
		"$DATASETS/from_sequencer/1_CACGAT_L007_R1_001.fastq",
		"$DATASETS/from_sequencer/1_CACGAT_L007_R2_001.fastq"
	]
}
"""


params = {}
with open( "params.json" ) as f:
	params = json.loads( f.read() )

task_folders = {}
for file_path in params['fastq_files[]']:
	file_folders, file_name = os.path.split( file_path )

	task_folders[file_path] = welder_run_task_add({
		"name": "bwa-"+file_name,
		"inputs": {
			"reference_genome": params['reference_genome'],
			"fastq": file_path
		},
		"command": 'echo "bwa aln -B '+params['barcode_length']+' -f ./outputs/out.sai reference_genome fastq"; echo 1 > ./outputs/out.sai',
		"container_image": "bwa_and_sam/0",
		"requirements": {
			"cpus": 1,
			"mem": 512
		}
	})

# ADD the SAM step. Depends on either one or two of the fastq files depending
# on if the file names are paired. Without metadata, we have to go on
# pattern matching of the file names which is a bit tricky

# BUILD a dict of _R1_ and _R2_ files
pairs = [{},{}]
for file_path in params['fastq_files[]']:
	match = re.match( r'^(.*/)([^/]+)_R(\d)_([^/]+)$', file_path )
	if match:
		# Illumina format, check for paired files
		r_index = int(match.group(3))-1
		if r_index == 0:
			pairs[0][file_path] = match.group(1)+match.group(2)+'_R2_'+match.group(4)
		else:
			pairs[1][file_path] = match.group(1)+match.group(2)+'_R1_'+match.group(4)
	else:
		# Not Illumina format, assume samse
		pairs[0][file_path] = ""

# LOOP through the R1's (pairs[0])
for r1_file_path, r2_file_path in pairs[0].items():
	r1_base_path, r1_file_name = os.path.split( r1_file_path )
	if r2_file_path in pairs[1]:
		# The mate exists, do a sampe
		r2_base_path, r2_file_name = os.path.split( r2_file_path )
		sai1 = os.path.join(task_folders[r1_file_path],'outputs/out.sai'),
		sai2 = os.path.join(task_folders[r2_file_path],'outputs/out.sai'),
		inputs = {
			"reference_genome": params['reference_genome'],
			"sai1": "$TASKS/bwa-"+r1_file_name+"/outputs/out.sai",
			"sai2": "$TASKS/bwa-"+r2_file_name+"/outputs/out.sai",
			"fastq1": r1_file_path,
			"fastq2": r2_file_path
		}
		cmd = "bwa sampe -f ./outputs/out.sam reference_genome sai1 sai2 fastq1 fastq2"
	else:
		# No mate exists, do a samse
		sai1 = os.path.join(task_folders[r1_file_path],'outputs/out.sai'),
		inputs = {
			"reference_genome": params['reference_genome'],
			"sai1": "$TASKS/bwa-"+r1_file_name+"/outputs/out.sai",
			"fastq1": r1_file_path,
		}
		cmd = "bwa samse -f ./outputs/out.sam reference_genome sai1 fastq1"

	welder_run_task_add({
		"name": "sam-"+r1_file_name,
		"inputs": inputs,
		"command": 'echo "'+cmd+'"',
		"container_image": "bwa_and_sam/0",
		"requirements": {
			"cpus": 1,
			"mem": 512
		}
	})


