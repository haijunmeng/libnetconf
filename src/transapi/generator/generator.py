#!/usr/bin/python
# vim set fileencoding=utf-8
#
# @file generator.py
# @author David Kupka <dkupka@cesnet.cz>
# @brief Libnetconf transapi generator.
#
# Copyright (c) 2011, CESNET, z.s.p.o.
# All rights reserved.
#
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name of the CESNET, z.s.p.o. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#

import libxml2
import argparse
import shutil
import re
import os
import subprocess
import tempfile

transapi_version = 3

target_dir = './'

RNGLIB='/usr/local/share/libnetconf/rnglib/'
XSLTDIR='/usr/local/share/libnetconf/xslt/'

# Find pyang and use it to convert model to YIN
def convert_to_yin(input_file_name, search_path):
	# convert model to YIN using pyang
	yin_data = subprocess.check_output(['pyang', '-p', search_path, '-f', 'yin', input_file_name])
	model = libxml2.parseMemory(yin_data, len(yin_data))
	# infer name of file from input file name
	(yin_file_name, ext) = os.path.splitext(os.path.abspath(input_file_name))
	yin_file_name+='.yin'
	# if the original model was not yin store converted yin
	if yin_file_name != input_file_name:
		yin_file = open(yin_file_name, 'w')
		yin_file.write(str(model))
		yin_file.close()

	return(model)
	
def generate_validators(yin_model_path, augment_models_paths, search_path):
	(yin_file_name, ext) = os.path.splitext(os.path.basename(yin_model_path))
	#create temporary file fof DSDL schema
	(dsdl_schema_fd,dsdl_schema_name) = tempfile.mkstemp(prefix='dsdl', suffix='.dsdl')
	(xslt_tmp_fd,xslt_tmp_name) = tempfile.mkstemp(prefix='schxsl')
	(xslt_tmp_inout_fd,xslt_tmp_inout_name) = tempfile.mkstemp()
	#generate DSDL schema from YIN schema files
	subprocess.check_call(['pyang', '-p', search_path, '-f', 'dsdl', '--dsdl-no-documentation', '--dsdl-no-dublin-core', '-o', os.path.abspath(dsdl_schema_name), yin_model_path ] + augment_models_paths)
	#generate RNG files from DSDL
	subprocess.check_call(['xsltproc', '--output', yin_file_name+'-data.rng', '--stringparam', 'basename', './'+yin_file_name, '--stringparam', 'target', 'data', '--stringparam', 'schema-dir', RNGLIB, os.path.join(XSLTDIR, 'gen-relaxng.xsl'), os.path.abspath(dsdl_schema_name)])
	subprocess.check_call(['xsltproc', '--output', yin_file_name+'-gdefs.rng', '--stringparam', 'gdefs-only', '1', os.path.join(XSLTDIR, 'gen-relaxng.xsl'), os.path.abspath(dsdl_schema_name)])
	#generate schematrom files form DSDL
	subprocess.check_call(['xsltproc', '--output', os.path.abspath(xslt_tmp_name), '--stringparam', 'target', 'data', os.path.join(XSLTDIR, 'gen-schematron.xsl'), os.path.abspath(dsdl_schema_name)])
	subprocess.check_call(['xsltproc', os.path.join(XSLTDIR, 'iso_abstract_expand.xsl'), os.path.abspath(xslt_tmp_name)], stdout=xslt_tmp_inout_fd)
	subprocess.check_call(['xsltproc', '-o', os.path.basename(yin_model_path)+'-schematron.xsl', os.path.join(XSLTDIR, 'iso_svrl_for_xslt1.xsl')], stdin=xslt_tmp_inout_fd)
	#close
	os.close(dsdl_schema_fd)
	os.close(xslt_tmp_fd)
	os.close(xslt_tmp_inout_fd)
	#and remove temporary files
	os.remove(os.path.abspath(dsdl_schema_name))
	os.remove(os.path.abspath(xslt_tmp_name))
	os.remove(os.path.abspath(xslt_tmp_inout_name))
	return(None)

# Use configure.in.template and replace all variables with text
def generate_configure_in(replace, template_dir):
	inf = open (template_dir+'/configure.in', 'r')
	outf = open (target_dir+'/configure.in', 'w')

	conf_in = inf.read()
	for pattern, value in replace.items():
		conf_in = conf_in.replace(pattern, value)

	outf.write(conf_in)
	inf.close()
	outf.close()

# Copy source files for autotools
def copy_template_files(name, template_dir):
	shutil.copy2(template_dir+'/install-sh', target_dir+'/install-sh')
	shutil.copy2(template_dir+'/config.guess', target_dir+'/config.guess')
	shutil.copy2(template_dir+'/config.sub', target_dir+'/config.sub')
	shutil.copy2(template_dir+'/ltmain.sh', target_dir+'/ltmain.sh')
	shutil.copy2(template_dir+'/Makefile.in', target_dir+'/Makefile.in')

def separate_paths_and_namespaces(defs):
	paths = []
	namespaces = []
	if not defs is None:
		for d in defs:
			d = d.rstrip()
			# skip empty lines and lines starting with '#' (bash/python style single line comments)
			if len(d) == 0 or d[0] == '#':
				continue

			# path definition
			if re.match(r'(/([\w]+:)?[\w]+)+', d):
				paths.append(d)
			elif re.match(r'[\w]+=.+', d):
				namespaces.append(d.split('='))
			else:
				raise ValueError('Line '+d+' is not valid namespace definition nor XPath.')

	return (paths,namespaces)

# 
def generate_callbacks_file(name, defs, model):
	# Create or rewrite .c file, will be generated
	outf = open(target_dir+'/'+name+'.c', 'w')

	content = ''
	# License and description
	content += '/*\n'
	content += ' * This is automaticaly generated callbacks file\n'
	content += ' * It contains 3 parts: Configuration callbacks, RPC callbacks and state data callbacks.\n'
	content += ' * Do NOT alter function signatures or any structures unless you know exactly what you are doing.\n'
	content += ' */\n\n'
	# Include header files
	content += '#include <stdlib.h>\n'
	content += '#include <libxml/tree.h>\n'
	content += '#include <libnetconf_xml.h>\n'
	content += '\n'
	# transAPI version
	content += '/* transAPI version which must be compatible with libnetconf */\n'
	content += 'int transapi_version = '+str(transapi_version)+';\n\n'
	content += '/* Signal to libnetconf that configuration data were modified by any callback.\n'
	content += ' * 0 - data not modified\n'
	content += ' * 1 - data have been modified\n'
	content += ' */\n'
	content += 'int config_modified = 0;\n\n'
	# init and close functions 
	content += generate_init_callback()
	content += generate_close_callback()
	# Add get state data callback
	content += generate_state_callback()
	# Config callbacks part
	(paths, namespaces) = separate_paths_and_namespaces(defs)
	content += generate_config_callbacks(name, paths, namespaces)
	if not (model is None):
		content += generate_rpc_callbacks(model)

	# Write to file
	outf.write(content)
	outf.close()

def generate_init_callback():
	content = '';
	content += '/**\n'
	content += ' * @brief Initialize plugin after loaded and before any other functions are called.\n'
	content += ' *\n'
	content += ' * @param[out] running\tCurrent configuration of managed device.\n\n'
	content += ' * @return EXIT_SUCCESS or EXIT_FAILURE\n'
	content += ' */\n'
	content += 'int transapi_init(xmlDocPtr * running)\n'
	content += '{\n\treturn EXIT_SUCCESS;\n}\n\n'

	return (content)
    
def generate_close_callback():
	content = ''
	content += '/**\n'
	content += ' * @brief Free all resources allocated on plugin runtime and prepare plugin for removal.\n'
	content += ' */\n' 
	content += 'void transapi_close(void)\n'
	content += '{\n\treturn;\n}\n\n'

	return (content)

def generate_state_callback():
	content = ''
	# function for retrieving state data from device
	content += '/**\n'
	content += ' * @brief Retrieve state data from device and return them as XML document\n'
	content += ' *\n'
	content += ' * @param model\tDevice data model. libxml2 xmlDocPtr.\n'
	content += ' * @param running\tRunning datastore content. libxml2 xmlDocPtr.\n'
	content += ' * @param[out] err  Double poiter to error structure. Fill error when some occurs.\n'
	content += ' * @return State data as libxml2 xmlDocPtr or NULL in case of error.\n'
	content += ' */\n'
	content += 'xmlDocPtr get_state_data (xmlDocPtr model, xmlDocPtr running, struct nc_err **err)\n'
	content += '{\n\treturn(NULL);\n}\n'

	return(content)

def generate_config_callbacks(name, paths, namespaces):
	if paths is None:
		raise ValueError('At least one path is required.')

	content = ''
	callbacks = '\t.callbacks = {'
	funcs_count = 0

	# prefix to uri mapping 
	content += '/*\n'
	content += ' * Mapping prefixes with namespaces.\n'
	content += ' * Do NOT modify this structure!\n'
	content += ' */\n'
	namespace = 'char * namespace_mapping[] = {'
	for ns in namespaces:
		namespace += '"'+ns[0]+'", "'+ns[1]+'", '

	content += namespace +'NULL, NULL};\n'
	content += '\n'

	# Add description and instructions
	content += '/*\n'
	content += '* CONFIGURATION callbacks\n'
	content += '* Here follows set of callback functions run every time some change in associated part of running datastore occurs.\n'
	content += '* You can safely modify the bodies of all function as well as add new functions for better lucidity of code.\n'
	content += '*/\n\n'
	# generate callback function for every given sensitive path
	for path in paths:
		func_name = 'callback'+re.sub(r'[^\w]', '_', path)
		# first entry in callbacks without coma
		if funcs_count != 0:
			callbacks += ','

		# single entry per generated function
		callbacks += '\n\t\t{.path = "'+path+'", .func = '+func_name+'}'

		# generate function with default doxygen documentation
		content += '/**\n'
		content += ' * @brief This callback will be run when node in path '+path+' changes\n'
		content += ' *\n'
		content += ' * @param[in] data\tDouble pointer to void. Its passed to every callback. You can share data using it.\n'
		content += ' * @param[in] op\tObserved change in path. XMLDIFF_OP type.\n'
		content += ' * @param[in] node\tModified node. if op == XMLDIFF_REM its copy of node removed.\n'
		content += ' * @param[out] error\tIf callback fails, it can return libnetconf error structure with a failure description.\n'
		content += ' *\n'
		content += ' * @return EXIT_SUCCESS or EXIT_FAILURE\n'
		content += ' */\n'
		content += '/* !DO NOT ALTER FUNCTION SIGNATURE! */\n'
		content += 'int '+func_name+' (void ** data, XMLDIFF_OP op, xmlNodePtr node, struct nc_err** error)\n{\n\treturn EXIT_SUCCESS;\n}\n\n'
		funcs_count += 1

	# in the end of file write strucure connecting paths in XML data with callback function
	content += '/*\n'
	content += '* Structure transapi_config_callbacks provide mapping between callback and path in configuration datastore.\n'
	content += '* It is used by libnetconf library to decide which callbacks will be run.\n'
	content += '* DO NOT alter this structure\n'
	content += '*/\n'
	content += 'struct transapi_data_callbacks clbks =  {\n'
	content += '\t.callbacks_count = '+str(funcs_count)+',\n'
	content += '\t.data = NULL,\n'
	content += callbacks+'\n\t}\n'
	content += '};\n\n'

	return(content);

def generate_rpc_callbacks(doc):
	content = ''
	callbacks = ''

	# Add description and instructions
	content += '/*\n'
	content += '* RPC callbacks\n'
	content += '* Here follows set of callback functions run every time RPC specific for this device arrives.\n'
	content += '* You can safely modify the bodies of all function as well as add new functions for better lucidity of code.\n'
	content += '* Every function takes array of inputs as an argument. On few first lines they are assigned to named variables. Avoid accessing the array directly.\n'
	content += '* If input was not set in RPC message argument in set to NULL.\n'
	content += '*/\n\n'

	# create xpath context
	ctxt = doc.xpathNewContext()
	ctxt.xpathRegisterNs('yang', 'urn:ietf:params:xml:ns:yang:yin:1')

	# find all RPC defined in data model
	rpcs = ctxt.xpathEval('//yang:rpc')

	# for every RPC
	for rpc in rpcs:
		rpc_name = rpc.prop('name')
		# create callback function
		rpc_function = 'nc_reply * rpc_'+re.sub(r'[^\w]', '_', rpc_name)+' (xmlNodePtr input[])\n{\n'
		# find all defined inputs
		rpc_input = ctxt.xpathEval('//yang:rpc[@name="'+rpc.prop('name')+'"]/yang:input/*')
		arg_order = '{'
		for inp in rpc_input:
			# assign inputs to named variables
			rpc_function += '\txmlNodePtr '+re.sub(r'[^\w]', '_', inp.prop('name'))+' = input['+str(rpc_input.index(inp))+'];\n'
			if not inp is rpc_input[0]:
				arg_order += ', '
			arg_order += '"'+inp.prop('name')+'"'

		arg_order += '}'
		rpc_function += '\n\treturn NULL; \n}\n'
		content += rpc_function

		if not rpc is rpcs[0]:
			callbacks += ','
		# add connection between callback and RPC message and order of arguments passed to the callback
		callbacks += '\n\t\t{.name="'+rpc_name+'", .func=rpc_'+re.sub(r'[^\w]', '_', rpc_name)+', .arg_count='+str(len(rpc_input))+', .arg_order='+arg_order+'}'

	content += '/*\n'
	content += '* Structure transapi_rpc_callbacks provide mapping between callbacks and RPC messages.\n'
	content += '* It is used by libnetconf library to decide which callbacks will be run when RPC arrives.\n'
	content += '* DO NOT alter this structure\n'
	content += '*/\n'
	content += 'struct transapi_rpc_callbacks rpc_clbks = {\n'
	content += '\t.callbacks_count = '+str(len(rpcs))+',\n'
	content += '\t.callbacks = {'+callbacks+'\n\t}'
	content += '\n};\n\n'

	return(content)

# Try to find template directory, if none of known candidates found raise exception
def find_templates():
	known_paths = ['/usr/share/libnetconf/templates/', '/usr/local/share/libnetconf/templates/', './templates/', './']

	for path in known_paths:
		if os.path.isdir(path):
			if os.path.exists(path+'install-sh') and os.path.exists(path+'Makefile.in') and \
					os.path.exists(path+'config.guess') and os.path.exists(path+'config.sub') and \
					os.path.exists(path+'ltmain.sh'):
				return(path)
	
	raise Exception('Template directory not found. Use --template-dir parameter to specify its location.')

# "main" starts here
# create argument parser
parser = argparse.ArgumentParser(description='libnetconf tool. Use it for converting YANG model to YIN model, generate validation schemas from model and generate files for libnetconf transapi callbacks module.')
parser.add_argument('--model', required=True, type=argparse.FileType('r'), help='File holding data model.')
parser.add_argument('--augment-models', nargs='*', type=argparse.FileType('r'), action='append', help='Specify augment models.')
parser.add_argument('--search-path', default='.', help='pyang search path.')

#create subparsers
subparsers = parser.add_subparsers(dest='subcommand')

# convert to implement YANG -> YIN conversion
parser_convert = subparsers.add_parser('convert')
#parser_convert.add_argument('--model', required=True, type=argparse.FileType('r'), help='File holding data model.')
#parser_convert.add_argument('--augment-models', nargs='*', type=argparse.FileType('r'), action='append', help='Specify augment models.')

# validation to implement validation schema generation
parser_validation = subparsers.add_parser('validation')
#parser_validation.add_argument('--model', required=True, type=argparse.FileType('r'), help='File holding data model.')
#parser_validation.add_argument('--augment-models', nargs='*', type=argparse.FileType('r'), action='append', help='Specify augment models.')

# transapi to implement transapi module files generation
parser_transapi = subparsers.add_parser('transapi')
parser_transapi.add_argument('--name', help='Name of module with callbacks. If not supplied name of module in data model will be used.')
#parser_transapi.add_argument('--model', required=True, type=argparse.FileType('r'), help='File holding data model. YIN and YANG formats are acceptable.')
#parser_transapi.add_argument('--augment-models', nargs='*', type=argparse.FileType('r'), action='append', help='Specify augment models.')
parser_transapi.add_argument('--paths', type=argparse.FileType('r'), help='File holding list of sensitive paths in configuration XML.')
parser_transapi.add_argument('--template-dir', default=None, help='Path to the directory with teplate files')

# add common model option
try:
	augment_models = []
	augment_models_paths = []
	args = parser.parse_args()

	# process model and find module name
	# whatever type the model is try to convert it to YIN
	model = convert_to_yin(args.model.name, args.search_path)
	(model_name, ext) = os.path.splitext(os.path.abspath(args.model.name))

	if args.name is None:
		(module_name,ext) = os.path.splitext(os.path.basename(args.model.name))
	else:
		module_name = args.name
		
	if not args.augment_models is None:
		for l in args.augment_models:
			for augment_model in l:
				augment_models.append(convert_to_yin(augment_model.name, args.search_path))
				(augment_model_name, ext) = os.path.splitext(os.path.abspath(augment_model.name))
				augment_models_paths.append(augment_model_name+'.yin')

	# when subcommand is 'validation' or 'transapi'
	if args.subcommand != 'convert':
		generate_validators(model_name+'.yin', augment_models_paths, args.search_path)
		
	if args.subcommand == 'transapi':
		# if --template-dir not specified try to find it
		# Would be nicer to call this function in 'default' part of parsing argument
		# --template-dir but then it gets called before trying to find and parse argument :(
		if args.template_dir is None:
			args.template_dir = find_templates()
		# store paterns and text for replacing in configure.in
		r = {'$$PROJECTNAME$$' : module_name}
		# prepare output directory
		target_dir = './'+module_name
		if not os.path.exists(target_dir):
			os.makedirs(target_dir)
	
		#generate configure.in
		generate_configure_in (r, args.template_dir)
		#copy files for autotools (Makefile.in, ...)
		copy_template_files(module_name, args.template_dir)
		#generate callbacks code
		generate_callbacks_file(module_name, args.paths, model)
except ValueError as e:
	print (e)
except IOError as e:
	print(e[1]+'('+str(e[0])+'): '+e.filename)
except libxml2.libxmlError as e:
	print('Can not parse data model: '+e.msg)
except subprocess.CalledProcessError as e:
	print("Command '%s' returned %d!" % (' '.join(e.cmd), e.returncode))
except KeyboardInterrupt:
	print('Killed by user!')
#except Exception as e:
#	print('Some unspecified error occured! '+str(e))

os.sys.exit(0)

