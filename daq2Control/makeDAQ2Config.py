#! /usr/bin/env python
import os
from daq2Configurator import daq2Configurator
from daq2Utils import getConfig, printWarningWithWait, printError

MAXNEFEDS = 16

def addConfiguratorOption(parser):
	parser.add_option("--useEvB", default=False, action="store_true",
		              dest="useEvB",
		              help=("Use EvB for event building (instead of gevb2g "
		              		"(default))"))
	parser.add_option("--useGevb2g", default=False, action="store_true",
		              dest="useGevb2g",
		              help="Use gevb2g for event building (instead of EvB)")
	parser.add_option("--useIBV", default=False, action="store_true",
		              dest="useIBV",
		              help=("Use IBV protocol for builder network peer "
		              		"transport (default)"))
	parser.add_option("--useUDAPL", default=False, action="store_true",
		              dest="useUDAPL",
		              help=("Use UDAPL protocol for builder network peer "
		              		"transport"))
	parser.add_option("--useGTPe", default=False, action="store_true",
		              dest="useGTPe",
		              help=("Use the GTPe for triggering at a certain rate. "
		              		"Implies 'frl_gtpe_trigger' or 'efed_slink_gtpe' "
		              		"for --ferolMode"))
	parser.add_option("--useEFEDs", default=False, action="store_true",
		              dest="useEFEDs",
		              help=("Use the FED emulators to generate events. "
		              	    "Implies --useGTPe and 'efed_slink_gtpe' for "
		              	    "--ferolMode"))

	parser.add_option("--setCWND", default=-1, action="store", type='int',
		              dest="setCWND",
		              help=("Set the TCP_CWND_FEDX parameter in the FEROL "
		              		"config [default: take from config fragment]"))
	# parser.add_option("--setSeed", default=False, action="store_true",
	# 	              dest="setSeed",
	# 	              help=("Set a unique seed for the random number "
	# 	              	    "generators in each FRL"))
	parser.add_option("--setCorrelatedSeed", default=False,
		              action="store_true", dest="setCorrelatedSeed",
		              help=("Set the same random number generator seed for "
		              	    "each FRL"))
	parser.add_option("--disablePauseFrame", default=False,
		              action="store_true", dest="disablePauseFrame",
		              help=("Set the ENA_PAUSE_FRAME parameter in the FEROL "
		              		"config to 'false' [default: take from config "
		              		"fragment]"))
	parser.add_option("--enablePauseFrame", default=False,
		              action="store_true", dest="enablePauseFrame",
		              help=("Set the ENA_PAUSE_FRAME parameter in the FEROL "
		              		"config to 'true'"))

	parser.add_option("-m", "--ferolMode", default='', action="store",
		              type="string", dest="ferolMode",
		              help=("Set ferol\operation mode, can be either "
		              		"'ferol_emulator', 'frl_autotrigger', "
		              		"'frl_gtpe_trigger', or 'efed_slink_gtpe'"))
	parser.add_option("-r", "--ferolRack", default=1, action="store",
		              type='int', dest="ferolRack",
		              help=("Which ferol rack to use (1,2, or 3) [default: "
		              	    "%default]. Choose 0 to use all three racks."))

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

def main(options, args):
	nstreams, nrus, nbus, _, strperfrl = getConfig(args[0])
	nferols = nstreams//strperfrl

	if len(options.fragmentDir) == 0:
		options.fragmentDir = ('/nfshome0/stiegerb/Workspace/'
		                       'daq2val/daq2Control/config_fragments/')
	configurator = daq2Configurator(options.fragmentDir,
		                            verbose=options.verbose)

	configurator.evbns = ('gevb2g' if options.useGevb2g and not
			                          options.useEvB else 'evb')
	configurator.ptprot = ('udapl' if options.useUDAPL  and not
			                          options.useIBV else 'ibv')

	## in case both are true, they will be enabled
	configurator.enablePauseFrame = options.enablePauseFrame
	configurator.disablePauseFrame = options.disablePauseFrame
	configurator.setCWND = options.setCWND ## -1 doesn't do anything
	# configurator.setSeed = options.setSeed
	configurator.setCorrelatedSeed = options.setCorrelatedSeed
	configurator.ferolRack = options.ferolRack
	if options.ferolRack not in [0, 1, 2, 3, 13]:
		printError("Unknown ferolRack: %d" %(options.ferolRack))
		exit(-1)

	if options.useEFEDs: options.useGTPe = True ## need GTPe for eFEDs
	configurator.useGTPe           = options.useGTPe
	configurator.useEFEDs          = options.useEFEDs

	## Some checks:
	if configurator.evbns == 'evb' and nbus < 4:
		printWarningWithWait(("Are you sure you want to run with only"
			                  "%d BUs and the EvB?"%nbus), waittime=3)
	if configurator.evbns == 'gevb2g'and nbus > 3:
		printWarningWithWait(("Are you sure you want to run with"
			                  "%d BUs and the gevb2g?"%nbus), waittime=3)
	if options.useEFEDs and nstreams > MAXNEFEDS:
		printError(("There are more streams (%d) than eFEDs available"
			        "(%d)!" %(nstreams, MAXNEFEDS)))
		exit(-1)

	configurator.operation_mode = (
		             options.ferolMode if len(options.ferolMode)>0 else
		             'ferol_emulator')
	## automatically use frl_gtpe_trigger mode when running with GTPe
	if options.useGTPe and options.ferolMode == '':
		configurator.operation_mode = 'frl_gtpe_trigger'
		if options.useEFEDs:
		    ## automatically use efed_slink_gtpe mode when running
		    ## with GTPe/EFEDs
			configurator.operation_mode = 'efed_slink_gtpe'

	## Construct output name
	output = args[0]
	if configurator.evbns == 'evb':    output += '_evb'
	if configurator.evbns == 'gevb2g': output += '_gevb2g'
	if configurator.ptprot == 'udapl': output += '_udapl'
	if configurator.ptprot == 'ibv':   output += '_ibv'
	if configurator.operation_mode == 'efed_slink_gtpe':
		output += '_efeds'
	if configurator.operation_mode == 'frl_gtpe_trigger':
		output += '_gtpe'
	if configurator.operation_mode == 'frl_autotrigger':
		output += '_frlAT'
	if configurator.setCorrelatedSeed:
		output += '_corr'
	output += ({0:'', 1:'_COL', 2:'_COL2', 3:'_COL3',
		        13:'_COL13'}[options.ferolRack])
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

	configurator.makeConfig(nferols,strperfrl,nrus,nbus,output)

	return True

if __name__ == "__main__":
	from optparse import OptionParser
	usage = """
	%prog [options] topology
	where topology is in the format of nStreams x nFerols x nRUs x nBUs,
	e.g. 16s8fx1x4

	Examples:
	%prog --useUDAPL --useGevb2g 24s12fx2x4 -o 24s12fx2x4_custom.xml
	%prog --setCWND 135000 --disablePauseFrame 32s16fx2x4
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

