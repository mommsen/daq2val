import subprocess
import re, os, shlex
import time
from sys import stdout
import xml.etree.ElementTree as ET

from daq2Utils import printError, printWarningWithWait, sleep, SIZE_LIMIT_TABLE, checkMaxSize

separator = 70*'-'


######################################################################
class host(object):
	"""Baseclass for a SOAP host"""
	def __init__(self,name,index,hosttype,soaphost='undefined',soapport=-99):
		self.name  = name
		self.index = index
		self.host  = soaphost
		self.port  = soapport
		self.type  = hosttype
		self.lport = 0 # launcher port
		self.applications = [] ## should be filled with ('classname', instance) tuples
	def __str__(self):
		return '%-20s%3d at %25s:%-5d with launcher at %-5d' % (self.type, self.index, self.host, self.port, self.lport)

######################################################################
class FEROL(host):
	"""Holds additional information on FEROL configuration"""
	def __init__(self,name,index,soaphost,soapport,hosttype, enableStream0=True, enableStream1=False):
		super(FEROL, self).__init__()
		self.enableStream0 = enableStream0
		self.enableStream1 = enableStream1
	def cfgStringToBool(self, string):
		return string in ('true', 'True', '1')
	def setStreams(self, enableStream0, enableStream1):
		self.enableStream0 = self.cfgStringToBool(enableStream0)
		self.enableStream1 = self.cfgStringToBool(enableStream1)

######################################################################
class eFED(host):
	"""Holds additional information on eFED configuration"""
	def __init__(self,name,index,soaphost='undefined',soapport=-99):
		super(FEROL, self).__init__()
		streams = []
	def addStream(self, instance, fedid=900, slot=-1):
		if not hasattr(self, 'streams'): ## want to morph hosts into eFEDs, i.e. constructor might not have been called
			self.streams = []
		self.streams.append((instance, fedid, slot))
	def __len__(self):
		return len(streams)
	def __str__(self):
		text  = '%-20s%3d at %25s:%-5d with launcher at %-5d\n' % (self.type, self.index, self.host, self.port, self.lport)
		for n,(instance,fedid,slot) in enumerate(self.streams):
			text += '  stream %d at instance %2d, fedid %d, slot %d\n' % (n, instance, fedid, slot)
		return text

######################################################################
class FMM(host):
	"""Holds additional information on FMM configuration"""
	def __init__(self,name,index,soaphost='undefined',soapport=-99):
		super(FEROL, self).__init__()
		streams = []
	def addSlot(self, geoslot=0, label='', inputs='', outputs=''):
		if not hasattr(self, 'slots'): ## want to morph hosts into FMMs, i.e. constructor might not have been called
			self.slots = []
		self.slots.append((geoslot, label, inputs, outputs))
	def __len__(self):
		return len(streams)
	def __str__(self):
		text  = '%-20s%3d at %25s:%-5d with launcher at %-5d\n' % (self.type, self.index, self.host, self.port, self.lport)
		for n,(geoslot, label, inputs, outputs) in enumerate(self.slots):
			text += '  geoslot %d (%-15s) inputLabels: %-82s outputLabels: %-20s\n' % (geoslot, label, inputs, outputs)
		return text

######################################################################
from daq2SymbolMap import daq2SymbolMap
class daq2Config(object):
	'''
---------------------------------------------------------------------
  class daq2Config

 - Reads a template xdaq config.xml file and returns an object that will know the
   setup of the system.
 - Checks the config for EvB vs gevb2g cases, for GTPe, IBV/UDAPL, etc.
 - Additional checks on the config file, such as enableStream0/1,
   Event_Length_Max_bytes_FED0/1, etc.
---------------------------------------------------------------------
'''
	def __init__(self, configFile, verbose=1):
		self.verbose = verbose
		self.configfile = configFile
		self.hosts      = [] ## a list of the hosts defined in the xml config
		self.FEROLs     = []
		self.eFEROLs    = []
		self.nStreams   = 0  ## total number of streams
		self.RUs        = []
		self.BUs        = []
		self.EVM        = []
		self.eFEDs      = []
		self.GTPe       = []
		self.FMM        = []
		self._hostTypes = {'FEROLCONTROLLER' : self.FEROLs,
		                   'FEROL'           : self.eFEROLs,
		                   'RU'              : self.RUs,
		                   'BU'              : self.BUs,
		                   'EVM'             : self.EVM,
		                   'EFED'            : self.eFEDs,
		                   'GTPE'            : self.GTPe,
		                   'FMM'             : self.FMM}

		self.readXDAQConfigTemplate(configFile)
		self.useGTPe = False
		if len(self.GTPe) > 0:
			self.useGTPe = True

		self.xmlns_xc      = "http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30"
		self.xmlns_soapenc = "http://schemas.xmlsoap.org/soap/encoding/"
		self.xmlns_xsi     = "http://www.w3.org/2001/XMLSchema-instance"
		self.xmlns_ferol   = "urn:xdaq-application:ferol::FerolController"

		if self.verbose>1: self.printHosts()

	def fillFromSymbolMap(self, symbolMap):
		"""Adds the hostname and ports from a symbol map for each host"""
		for host in self.hosts:
			try:
				host.host  = symbolMap(host.name+'_SOAP_HOST_NAME')
				host.port  = symbolMap(host.name+'_SOAP_PORT')
				host.lport = symbolMap(host.name+'_LAUNCHER_PORT')
			except KeyError as e:
				printError("Didn't find host %s in symbol map." % host.name, self)
				raise e

	def printHosts(self, out=None, prepend=''):
		if out==None: out = stdout
		separator = 70*'-'
		out.write(prepend+separator+'\n')
		## Count enabled FEROL streams:
		streams = 0
		for host in self.FEROLs:
			if host.enableStream0: streams += 1
			if host.enableStream1: streams += 1

		if len(self.FEROLs) > 0: config = '%ds%dfx%dx%d' % (streams, len(self.FEROLs), len(self.RUs), len(self.BUs))
		else              : config = '%dx%dx%d'     % (len(self.eFEROLs), len(self.RUs), len(self.BUs))
		builder = 'EvB' if self.useEvB else 'gevb2g'
		ptprotocol = 'IBV' if self.useIBV else 'UDAPL'
		out.write('%s%s configuration with %s/%s\n' % (prepend, config, builder,ptprotocol))
		out.write(prepend+separator+'\n')
		for host in self.hosts:
			out.write(prepend+'%-20s at %25s:%-5d (SOAP) :%-5d (LAUNCHER), Applications:' % (host.name, host.host, host.port, host.lport))
			for app,inst in host.applications:
				if inst is not None: out.write(' %s(%d)' % (app, inst))
				else:                out.write(' %s' % app)
			out.write('\n')

			if host.__class__ == eFED:
				for n,(instance,fedid,slot) in enumerate(host.streams):
					out.write(prepend+'  stream %d at instance %2d, fedid %d, slot %d\n' % (n, instance, fedid, slot))
			if host.__class__ == FMM:
				for n,(geoslot, label, inputs, outputs) in enumerate(host.slots):
					out.write(prepend+'  geoslot %d (%-15s) inputLabels: %-82s outputLabels: %-20s\n' % (geoslot, label, inputs, outputs))
		out.write(prepend+separator+'\n')

	def setFerolParameter(self, param_name, param_value):
		partition = self.config.getroot()
		for context in partition.getiterator(ET.QName(self.xmlns_xc,'Context').text):
			if not 'FEROLCONTROLLER' in context.attrib['url']: continue
			param = context.find(ET.QName(self.xmlns_xc,'Application').text+'/'+ET.QName(self.xmlns_ferol,'properties').text+'/'+ET.QName(self.xmlns_ferol,param_name).text)
			if param is not None:
				param.text = str(param_value)
			else:
				raise KeyError('Ferol parameter '+param_name+' not found')

	def printFerolParameter(self, param_name):
		partition = self.config.getroot()
		for context in partition.getiterator(ET.QName(self.xmlns_xc,'Context').text):
			if not 'FEROLCONTROLLER' in context.attrib['url']: continue
			param = context.find(ET.QName(self.xmlns_xc,'Application').text+'/'+ET.QName(self.xmlns_ferol,'properties').text+'/'+ET.QName(self.xmlns_ferol,param_name).text)
			if param is not None:
				print context.attrib['url'], param_name, param.text
			else:
				raise KeyError('Ferol parameter '+param_name+' not found')

	def readXDAQConfigTemplate(self, configFile):
		if not os.path.exists(configFile):
			raise IOError('File '+configFile+' not found')
		self.testCase      = os.path.dirname(configFile[configFile.find('cases/')+6:])
		self.testCaseShort = os.path.dirname(configFile).split('/')[-1]
		self.config = ET.parse(configFile)
		partition = self.config.getroot()

		## Check <i2o:protocol> element for evb: or gevb2g: tags to determine which of the two we're dealing with here:
		i2o_namespace = 'http://xdaq.web.cern.ch/xdaq/xsd/2004/I2OConfiguration-30'
		i2o_protocol = partition.find("{%s}protocol" % i2o_namespace)
		if 'gevb2g::' in i2o_protocol[0].attrib['class']: ## there is something with a gevb2g tag
			if self.verbose > 2 : print "Found a gevb2g configuration"
			self.useEvB = False
			self.namespace = 'gevb2g::'
		elif 'evb::' in i2o_protocol[0].attrib['class']: ## there is something with a evb tag
			if self.verbose > 2 : print "Found an EvB configuration"
			self.useEvB = True
			self.namespace = 'evb::'
		else:
			raise RuntimeError("Couldn't determine EvB/gevb2g case!")

		maxsizes = []
		tcp_cwnd = []
		checked_ibv = False

		#### Scan <xc:Context>'s to extract configuration
		for context in partition:
			if not context.tag.endswith('Context'): continue

			## Match context url
			url = context.attrib['url']
			pattern = re.compile(r'http://([A-Z_0-9]*?)([0-9]+)_SOAP_HOST_NAME:.*')
			h,n = pattern.match(url).group(1), pattern.match(url).group(2) ## so h will be RU/BU/EVM/FEROLCONTROLLER/..., n will be 0,1,2,3,...
			try:
				if self.verbose > 2: print 'Adding', h+n
				ho = host(h+n, int(n), h)

				## Save a list of all applications and instances running in each context
				for app in context.findall("./{http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30}Application"):
					try:
						classname,instance = (str(app.attrib['class']), int(app.attrib['instance']))
					except KeyError:
						classname,instance = (str(app.attrib['class']), None)
					ho.applications.append((classname, instance))

				## For RU, check whether IVB or UDAPL (only do it once)
				if h == 'RU' and checked_ibv == False:
					self.useIBV = False
					for app in context.findall("./{http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30}Application"):
						if app.attrib['class'] == 'pt::ibv::Application':
							self.useIBV = True  ## Found IBV configuration
							if self.verbose > 2 : print "Found IBV peer transport protocol"
							break
						if app.attrib['class'] == 'pt::udapl::Application':
							self.useIBV = False ## Found UDAPL configuration
							if self.verbose > 2 : print "Found UDAPL peer transport protocol"
							break
					checked_ibv = True

				## For FEROLs, check which of the streams are enabled
				if h == 'FEROLCONTROLLER':
					for app in context.findall("./{http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30}Application"):
						if app.attrib['class'] == 'ferol::FerolController':
							frlns = '{urn:xdaq-application:ferol::FerolController}'
							prop = app.find(frlns + 'properties')
							ho.__class__ = FEROL ## Make it a FEROL
							ho.setStreams(prop.find(frlns + 'enableStream0').text, prop.find(frlns + 'enableStream1').text)
							if ho.enableStream0:
								self.nStreams += 1
								maxsizes.append(int(prop.find(frlns + 'Event_Length_Max_bytes_FED0').text))
								tcp_cwnd.append(int(prop.find(frlns + 'TCP_CWND_FED0').text))
							if ho.enableStream1:
								self.nStreams += 1
								maxsizes.append(int(prop.find(frlns + 'Event_Length_Max_bytes_FED1').text))
								tcp_cwnd.append(int(prop.find(frlns + 'TCP_CWND_FED1').text))
							break

				## For eFEDs, count the number of enabled streams and their instances
				if h == 'EFED':
					ho.__class__ = eFED ## Make it an eFED
					for app in context.findall("./{http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30}Application"):
						if app.attrib['class'] == 'd2s::FEDEmulator':
							efedns = '{urn:xdaq-application:d2s::FEDEmulator}'
							prop = app.find(efedns + 'properties')
							fedid    = int(prop.find(efedns + 'FedSourceId').text)
							slot     = int(prop.find(efedns + 'slot').text)
							instance = int(app.attrib['instance'])
							ho.addStream(instance, fedid, slot)

				## For FMM, check the different geoslots and input/output labels
				if h == 'FMM':
					ho.__class__ = FMM ## Make it an FMM
					for app in context.findall("./{http://xdaq.web.cern.ch/xdaq/xsd/2004/XMLConfiguration-30}Application"):
						if app.attrib['class'] == 'tts::FMMController':
							efedns = '{urn:xdaq-application:tts::FMMController}'
							prop = app.find(efedns + 'properties')
							fmmconfig = prop.find(efedns + 'config')
							for item in fmmconfig.findall(efedns+"item"):
								geoslot = int(item.find(efedns+'geoslot').text)
								label   = str(item.find(efedns+'label').text)
								inputs  = str(item.find(efedns+'inputLabels').text)
								outputs = str(item.find(efedns+'outputLabels').text)
								ho.addSlot(geoslot, label, inputs, outputs)

				if h == 'FEROL': ## Misnomer, eFEROLs are called FEROLS
					self.nStreams += 1

				self._hostTypes[h].append(ho)
				self.hosts.append(ho)

			except KeyError as e:
				printError('Unknown host type %s. Aborting.' % h, self)
				raise e

		if self.verbose < 1: return
		if len(maxsizes) > 0:
			## Check whether they were all filled
			if len(maxsizes) != self.nStreams:
				raise RuntimeError("Didn't find all Event_Length_Max_bytes parameter in config file?!")

			## Check they are all the same:
			size_set = set(maxsizes)
			if len(size_set) > 1:
				message = """
WARNING: You have FEROLs with different
         Event_Length_Max_bytes parameters in your config file!

 That probably shouldn't be.
"""
				printWarningWithWait(message, instance=self)

# 			## Check they are correct and alert
# 			if not checkMaxSize(maxsizes[0], self.nStreams//len(self.RUs)):
# 			# if maxsizes[0] != SIZE_LIMIT_TABLE[self.nStreams//len(self.RUs)][0]:
# 				message = """
# WARNING: Event_Length_Max_bytes for FEROLs seems to be set
#          to the wrong value in your config .xml file!

#  Is set to: %d in config. Expected value: %d
# """ % (int(maxsizes[0]), int(SIZE_LIMIT_TABLE[self.nStreams//len(self.RUs)][0]))
# 				printWarningWithWait(message, instance=self)

		if len(tcp_cwnd) > 0:
			## Check whether they were all filled
			if len(tcp_cwnd) != self.nStreams:
				raise RuntimeError("Didn't find all TCP_CWND_FEDX parameters in config file?!")

			## Check they are all the same:
			cwnd_set = set()
			for x in tcp_cwnd: cwnd_set.add(x)
			if len(cwnd_set) > 1:
				message = """
WARNING: You have FEROLs with different
         TCP_CWND_FEDX parameters in your config file!

 That probably shouldn't be.
"""
				printWarningWithWait(message, instance=self)


			## Check they are correct and alert in case:
			message = """
WARNING: TCP_CWND_FEDX for FEROLs seems to be set
         to the wrong value in your config .xml file!

 Is set to: %d in config. Expected value: %d
"""
			cwnd = cwnd_set.pop()
			if self.nStreams == len(self.FEROLs) and cwnd not in [80000, 55000]:
				printWarningWithWait(message%(cwnd, 80000), instance=self, waittime=2)
			if self.nStreams == 2*len(self.FEROLs) and cwnd not in [40000, 35000]:
				printWarningWithWait(message%(cwnd, 40000), instance=self, waittime=2)


	def writeConfig(self, destination):
		self.config.write(destination)

