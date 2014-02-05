#! /usr/bin/env python
from daq2Configurator import daq2Configurator
from daq2Utils import getConfig, printWarningWithWait, printError

MAXNEFEDS = 16

if __name__ == "__main__":
	from optparse import OptionParser
	usage = """
	%prog [options] topology
	where topology is in the format of nStreams x nFerols x nRUs x nBUs, e.g. 16s8fx1x4

	Examples:
	%prog --useIBV --useEvB 24s12fx2x4 -o 24s12fx2x4_evb_ibv.xml
	%prog --setCWND 135000 --disablePauseFrame 32s16fx2x4
	"""
	parser = OptionParser()
	parser.usage = usage
	parser.add_option("--useEvB",            default=False, action="store_true",             dest="useEvB",            help="Use EvB for event building (instead of gevb2g (default))")
	parser.add_option("--useGevb2g",         default=False, action="store_true",             dest="useGevb2g",         help="Use gevb2g for event building (instead of EvB)")
	parser.add_option("--useIBV",            default=False, action="store_true",             dest="useIBV",            help="Use IBV protocol for builder network peer transport")
	parser.add_option("--useUDAPL",          default=False, action="store_true",             dest="useUDAPL",          help="Use UDAPL protocol for builder network peer transport (default)")
	parser.add_option("--useGTPe",           default=False, action="store_true",             dest="useGTPe",           help="Use the GTPe for triggering at a certain rate. Implies 'frl_gtpe_trigger' or 'efed_slink_gtpe' for --ferolMode")
	parser.add_option("--useEFEDs",          default=False, action="store_true",             dest="useEFEDs",          help="Use the FED emulators to generate events. Implies --useGTPe and 'efed_slink_gtpe' for --ferolMode")

	parser.add_option("--setCWND",           default=-1,    action="store",      type='int', dest="setCWND",           help="Set the TCP_CWND_FEDX parameter in the FEROL config [default: take from config fragment]")
	parser.add_option("--disablePauseFrame", default=False, action="store_true",             dest="disablePauseFrame", help="Set the ENA_PAUSE_FRAME parameter in the FEROL config to 'false' [default: take from config fragment]")
	parser.add_option("--enablePauseFrame",  default=False, action="store_true",             dest="enablePauseFrame",  help="Set the ENA_PAUSE_FRAME parameter in the FEROL config to 'true'")

	parser.add_option("-m", "--ferolMode",   default='', action="store", type="string", dest="ferolMode",   help="Set ferol operation mode, can be either 'ferol_emulator', 'frl_autotrigger', 'frl_gtpe_trigger', or 'efed_slink_gtpe'")
	parser.add_option("-r", "--ferolRack",   default=1,  action="store", type='int',    dest="ferolRack",   help="Which ferol rack to use (1,2, or 3) [default: %default]. Choose 0 to use all three racks.")

	parser.add_option("--fragmentDir",       default='', action="store", type="string", dest="fragmentDir", help="Use config fragments from a directory other than the default")
	parser.add_option("-v", "--verbose",     default=1,  action="store", type='int',    dest="verbose",     help="Set the verbose level, [default: %default (semi-quiet)]")
	parser.add_option("-o", "--output",      default='', action="store", type='string', dest="output", help="Where to put the output file")

	(options, args) = parser.parse_args()
	if len(args) > 0:
		nstreams, nrus, nbus, _, strperfrl = getConfig(args[0])
		nferols = nstreams//strperfrl

		if len(options.fragmentDir) == 0:
			options.fragmentDir = '/nfshome0/stiegerb/Workspace/daq2val/daq2Control/config_fragments/'
		configurator = daq2Configurator(options.fragmentDir, verbose=options.verbose)

		configurator.evbns             = 'evb' if options.useEvB and not options.useGevb2g else 'gevb2g'
		configurator.ptprot            = 'ibv' if options.useIBV and not options.useUDAPL  else 'udapl'

		configurator.enablePauseFrame  = options.enablePauseFrame
		configurator.disablePauseFrame = options.disablePauseFrame ## in case both are true, they will be enabled
		configurator.setCWND           = options.setCWND ## -1 doesn't do anything
		configurator.ferolRack         = options.ferolRack

		if options.useEFEDs: options.useGTPe = True ## need GTPe for eFEDs
		configurator.useGTPe           = options.useGTPe
		configurator.useEFEDs          = options.useEFEDs

		## Some checks:
		if configurator.evbns == 'evb' and nbus < 4:
			printWarningWithWait("Are you sure you want to run with only %d BUs and the EvB?"%nbus, waittime=3)
		if configurator.evbns == 'gevb2g'and nbus > 3:
			printWarningWithWait("Are you sure you want to run with %d BUs and the gevb2g?"%nbus, waittime=3)
		if options.useEFEDs and nstreams > MAXNEFEDS:
			printError("There are more streams (%d) than eFEDs available (%d)!" %(nstreams, MAXNEFEDS))
			exit(-1)

		configurator.operation_mode    = options.ferolMode if len(options.ferolMode)>0 else 'ferol_emulator'
		if options.useGTPe and options.ferolMode == '': ## automatically use frl_gtpe_trigger mode when running with GTPe
			configurator.operation_mode = 'frl_gtpe_trigger'
			if options.useEFEDs:  ## automatically use efed_slink_gtpe mode when running with GTPe/EFEDs
				configurator.operation_mode = 'efed_slink_gtpe'

		output = args[0]
		if configurator.evbns == 'evb':    output+='_evb'
		if configurator.evbns == 'gevb2g': output+='_gevb2g'
		if configurator.ptprot == 'udapl': output+='_udapl'
		if configurator.ptprot == 'ibv':   output+='_ibv'
		if configurator.operation_mode == 'efed_slink_gtpe':  output+='_efeds'
		if configurator.operation_mode == 'frl_gtpe_trigger': output+='_gtpe'
		if configurator.operation_mode == 'frl_autotrigger':  output+='_frlAT'
		output+='.xml'

		if len(options.output)>0:
			output = options.output

		configurator.makeConfig(nferols,strperfrl,nrus,nbus,output)

		exit(0)

	parser.print_help()
	exit(-1)


