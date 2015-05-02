import re
import json
import os
import welder_api

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


