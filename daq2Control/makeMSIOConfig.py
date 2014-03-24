#! /usr/bin/env python
import os
from daq2MSIOConfigurator import daq2MSIOConfigurator
from daq2Utils import getConfig, printWarningWithWait, printError

def addConfiguratorOption(parser):
	parser.add_option("--useGevb2g", default=False, action="store_true",
		              dest="useGevb2g",
		              help="Use gevb2g for event building (instead of EvB)")
	parser.add_option("--fragmentDir", default='', action="store",
		              type="string", dest="fragmentDir",
		              help=("Use config fragments from a directory other than "
		                    "the default"))
	parser.add_option("-v", "--verbose", default=1, action="store",
		              type='int', dest="verbose",
		              help=("Set the verbose level, [default: %default "
		              		"(semi-quiet)]"))
	parser.add_option("-o", "--output", default='', action="store",
		              type='string', dest="output",
		              help="Where to put the output file")

def getMSIOConfig(string=""):
	"""Extract number of streams, readout units, builder units, and RMS from strings such as
	8x1x2 or 16s8fx2x4_RMS_0.5 (i.e 8,1,2,None in the first case, 16,2,4,0.5 in the second)
	"""
	try:
		nClie, nServ = tuple([int(x) for x in string.split('x')])
		return nClie, nServ
	except:
		print "There was an error?"



def main(options, args):
	nClients, nServers = getMSIOConfig(args[0])

	if len(options.fragmentDir) == 0:
		options.fragmentDir = ('/nfshome0/stiegerb/Workspace/'
		                       'daq2val/daq2Control/config_fragments/')
	configurator = daq2MSIOConfigurator(options.fragmentDir,
		                                verbose=options.verbose)

	configurator.evbns = 'msio'
	if options.useGevb2g: configurator.evbns = 'gevb2g'

	## Construct output name
	output = args[0]
	if not options.useGevb2g:
		output += '_msio'
	else:
		output += '_gevb2g'
	output+='_ibv'
	output+='.xml'

	if len(options.output)>0:
		name, ext = os.path.splitext(options.output)
		if not os.path.dirname(name) == '':
			try:
				os.makedirs(os.path.dirname(name))
			except OSError as e:
				if not 'File exists' in str(e):
					raise e

		if ext == '.xml':
			# Take exactly what's given in the option
			output = options.output
		elif ext == '':
			output = os.path.join(name, output)

	configurator.makeMSIOConfig(nClients, nServers, output)

	return True

if __name__ == "__main__":
	from optparse import OptionParser
	usage = """
	%prog [options] topology
	where topology is in the format of nClients x nServers,
	e.g. 4x2

	Examples:
	%prog --useGevb2g 4x4
	%prog 2x4 --fragmentDir fragments/ -o 2x4_special.xml
	"""
	parser = OptionParser()
	parser.usage = usage
	addConfiguratorOption(parser)
	(options, args) = parser.parse_args()

	if len(args) > 0:
		if main(options, args):
			exit(0)
		else:
			printError("Something went wrong.")

	parser.print_help()
	exit(-1)

