#! /usr/bin/env python
import daq2Utils as utils
from daq2Config import daq2Config
from daq2Control import separator
from daq2SymbolMap import daq2SymbolMap
from daq2Utils import sleep, printError, printWarningWithWait, loadMonitoringItemsFromURL, getParam

def printApplicationState(host, classname, instance, statename, dry=False):
	## Special case until stateName is added to the application infospace in the FerolController
	if dry: return True
	if host.type == 'FEROLCONTROLLER':
		url = 'http://%s:%d/urn:xdaq-application:lid=109' % (host.host, host.port)
		items = loadMonitoringItemsFromURL(url)
		state = items['stateName']
		if not state == statename:
			stdout.write('\n')
			printError('Application %s, instance %d, on host %s:%-d, did not return state "%s", instead was "%s".' %(classname, instance, host.host, host.port, statename, state))
			return False
		return True

	## Normal case
	state = getParam(host.host, host.port, classname, instance, 'stateName', 'xsd:string')
	state = state.strip('\n') ## remove trailing newlines
	if not state == statename:
		stdout.write('\n')
		printError('Application %s, instance %d, on host %s:%-d, did not return state "%s", instead was "%s".' %(classname, instance, host.host, host.port, statename, state))
		return False
	return True


if __name__ == "__main__":
	from optparse import OptionParser
	parser = OptionParser()
	parser.add_option("-v", "--verbose", default=0, action="store", type='int', dest="verbose", help="Set the verbose level, [default: %default (quiet)]")
	(options, args) = parser.parse_args()

	to_be_printed = ['d2s::GTPeController', 'd2s::FEDEmulator', 'tts::FMMController', 'ferol::FerolController', 'evb::EVM', 'evb::RU', 'evb::BU']

	d2SM  = daq2SymbolMap()
	d2Cfg = daq2Config(args[0], verbose=options.verbose)
	d2Cfg.fillFromSymbolMap(d2SM)

	for host in d2Cfg.hosts:
		# print host.name
		for app,inst in host.applications:
			if not app in to_be_printed: continue
			## Get State
			state = 'UNKNOWN'
			if host.type == 'FEROLCONTROLLER': ## Special case for FEROLCONTROLLER
				url = 'http://%s:%d/urn:xdaq-application:lid=109' % (host.host, host.port)
				items = loadMonitoringItemsFromURL(url)
				state = items['stateName']
			else:
				state = getParam(host.host, host.port, app, inst, 'stateName', 'xsd:string')
				state = state.strip('\n') ## remove trailing newlines
			print'%-17s %-25s(%2d) %-20s' % (host.name, app, inst, state)

	exit(0)

