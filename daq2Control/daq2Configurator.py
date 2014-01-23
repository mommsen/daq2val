import subprocess, re
from copy import deepcopy

from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement
from xml.etree.ElementTree import QName as QN
from xml.parsers.expat import ExpatError

from daq2Utils import printError

######################################################################
def elementFromFile(filename):
	"""
	Parses a .xml file and returns a xml.etree.ElementTree.Element object.
	Raises a RuntimeError if the parsing failed.
	"""
	element = None
	with open(filename, 'r') as file:
		text = file.read()
		try:
			element = ElementTree.XML(text)
		except ExpatError as e:
			printError('Error parsing xml file %s:\n%s' % (filename, str(e)) )
			raise RuntimeError('Error parsing xml file %s' % filename)
		file.close()
	return element
def addFragmentFromFile(target, filename, index=-1):
	element = elementFromFile(filename)
	if index<0: target.append(element)
	else:       target.insert(index, element)
def split_list(alist, wanted_parts=1):
	length = len(alist)
	return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts] for i in range(wanted_parts) ]

######################################################################
FEDIDS    = [901 + n for n in range(32)]
SOURCEIPS = ['dvferol-c2f32-28-%02d.dvfbs2v0.cms' % (n+1) for n in range(16)]
FEROL_OPERATION_MODES = {'ferol_emulator'  :('FEROL_EMULATOR_MODE', None),
                         'frl_autotrigger' :('FRL_EMULATOR_MODE',  'FRL_AUTO_TRIGGER_MODE'),
                         'frl_gtpe_trigger':('FRL_EMULATOR_MODE',  'FRL_GTPE_TRIGGER_MODE'),
                         'efed_slink_gtpe' :('SLINK_MODE',         'FRL_GTPE_TRIGGER_MODE')}

######################################################################
class daq2Configurator(object):
	'''
---------------------------------------------------------------------
  class daq2Configurator

---------------------------------------------------------------------
'''
	def __init__(self, fragmentdir, verbose=5):
		self.verbose     = verbose
		self.fragmentdir = fragmentdir
		self.soapencns      = "http://schemas.xmlsoap.org/soap/encoding/"

		## These should be passed as options
		self.enablePauseFrame  = True
		self.disablePauseFrame = False
		self.setCWND = -1
		self.evbns          = 'gevb2g' ## 'gevb2g' or 'EvB'
		self.ptprot         = 'ibv' ## or 'ibv' or 'udapl'
		self.operation_mode = 'ferol_emulator'

		## These should be passes as arguments
		self.nrus              = 1
		self.nbus              = 2
		self.nferols           = 8
		self.streams_per_ferol = 2

	def makeSkeleton(self):
		fragmentname = 'skeleton.xml'
		self.config = elementFromFile(self.fragmentdir+fragmentname)
		self.xdaqns = re.match(r'\{(.*?)\}Partition', self.config.tag).group(1) ## Extract namespace

	def addI2OProtocol(self):
		i2ons = "http://xdaq.web.cern.ch/xdaq/xsd/2004/I2OConfiguration-30"
		prot = Element(QN(i2ons, 'protocol').text)

		## Add RUs:
		ru_starting_tid = 22
		for n in xrange(self.nrus):
			prot.append(Element(QN(i2ons, 'target').text, {'class':'%s::RU'%self.evbns , 'instance':"%d"%n, "tid":"%d"%(ru_starting_tid+n)}))
		## Add BUs:
		bu_starting_tid = 26
		for n in xrange(self.nbus):
			prot.append(Element(QN(i2ons, 'target').text, {'class':'%s::BU'%self.evbns , 'instance':"%d"%n, "tid":"%d"%(bu_starting_tid+2*n)}))
		## Add EVM:
		if self.evbns == 'gevb2g':
			prot.append(Element(QN(i2ons, 'target').text, {'class':'%s::EVM'%self.evbns , 'instance':"0", "tid":"39"}))

		self.config.append(prot)

	def setPropertyInApp(self, context, classname, prop_name, prop_value):
		for app in context.findall(QN(self.xdaqns, 'Application').text):
			if not app.attrib['class'] == classname: continue ## find correct application
			try:
				properties = app[0] ## Assume here that there is only one element, which is the properties
				if not 'properties' in properties.tag:
					raise RuntimeError('Could not identify properties of %s application in %s context.'%(app.attrib['class'], context.attrib['url']))
				appns = re.match(r'\{(.*?)\}properties', properties.tag).group(1) ## Extract namespace
			except IndexError: ## i.e. app[0] didn't work
				raise RuntimeError('Application %s in context %s does not have properties.'%(app.attrib['class'], context.attrib['url']))

			prop = app.find(QN(appns,'properties').text+'/'+QN(appns,prop_name).text)
			try:
				prop.text = str(prop_value)
			except AttributeError:
				raise KeyError('Property %s of application %s in context %s not found.'%(prop_name, app.attrib['class'], context.attrib['url']))
			break

		else:
			raise RuntimeError('Application %s not found in context %s.'%(classname, context.attrib['url']))
	def removePropertyInApp(self, context, classname, prop_name):
		for app in context.findall(QN(self.xdaqns, 'Application').text):
			if not app.attrib['class'] == classname: continue ## find correct application
			try:
				properties = app[0] ## Assume here that there is only one element, which is the properties
				if not 'properties' in properties.tag:
					raise RuntimeError('Could not identify properties of %s application in %s context.'%(app.attrib['class'], context.attrib['url']))
				appns = re.match(r'\{(.*?)\}properties', properties.tag).group(1) ## Extract namespace
			except IndexError: ## i.e. app[0] didn't work
				raise RuntimeError('Application %s in context %s does not have properties.'%(app.attrib['class'], context.attrib['url']))

			prop = app.find(QN(appns,'properties').text+'/'+QN(appns,prop_name).text)
			try:
				properties.remove(prop)
			except AttributeError:
				raise KeyError('Property %s of application %s in context %s not found.'%(prop_name, app.attrib['class'], context.attrib['url']))
			break

		else:
			raise RuntimeError('Application %s not found in context %s.'%(classname, context.attrib['url']))

	def makeFerolController(self, slotNumber, fedId0, fedId1, sourceIp, nStreams=1):
		fragmentname = 'FerolController.xml'
		ferol = elementFromFile(self.fragmentdir+fragmentname)
		classname = 'ferol::FerolController'
		self.setPropertyInApp(ferol, classname, 'slotNumber',      slotNumber)
		self.setPropertyInApp(ferol, classname, 'expectedFedId_0', fedId0)
		self.setPropertyInApp(ferol, classname, 'expectedFedId_1', fedId1)
		self.setPropertyInApp(ferol, classname, 'SourceIP',        sourceIp)

		if nStreams == 1:
			self.setPropertyInApp(ferol, classname, 'enableStream0', 'true')
			self.setPropertyInApp(ferol, classname, 'enableStream1', 'false')
		if nStreams == 2:
			self.setPropertyInApp(ferol, classname, 'enableStream0', 'true')
			self.setPropertyInApp(ferol, classname, 'enableStream1', 'true')

		if self.disablePauseFrame: self.setPropertyInApp(ferol, classname, 'ENA_PAUSE_FRAME', 'false')
		if self.enablePauseFrame:  self.setPropertyInApp(ferol, classname, 'ENA_PAUSE_FRAME', 'true')
		if self.setCWND >= 0:      self.setPropertyInApp(ferol, classname, 'TCP_CWND_FED0', self.setCWND)
		if self.setCWND >= 0:      self.setPropertyInApp(ferol, classname, 'TCP_CWND_FED1', self.setCWND)

		try:
			self.setPropertyInApp(ferol, classname, 'OperationMode',  FEROL_OPERATION_MODES[self.operation_mode][0])
			if FEROL_OPERATION_MODES[self.operation_mode][1] is not None:
				self.setPropertyInApp(ferol, classname, 'FrlTriggerMode', FEROL_OPERATION_MODES[self.operation_mode][1])
			else:
				self.removePropertyInApp(ferol, classname, 'FrlTriggerMode')
		except KeyError as e:
			printError('Unknown ferol operation mode "%s"'%self.operation_mode, instance=self)
			raise RuntimeError('Unknown ferol operation mode')


		ferol.set('url', ferol.get('url')%(slotNumber-1, slotNumber-1))

		return ferol
	def addFerolControllers(self, nferols, streams_per_ferol=1):
		for n in xrange(nferols):
			self.config.append(self.makeFerolController(slotNumber=n+1, fedId0=FEDIDS[2*n], fedId1=FEDIDS[2*n+1], sourceIp=SOURCEIPS[n], nStreams=streams_per_ferol))

	def makeRU(self, index):
		fragmentname = 'RU/%s/RU.xml'%self.evbns
		ru_element = elementFromFile(self.fragmentdir+fragmentname)

		## Add policy
		addFragmentFromFile(target=ru_element, filename=self.fragmentdir+'/RU/%s/RU_policy_%s.xml'%(self.evbns,self.ptprot), index=0)
		## Add builder network endpoint
		ru_element.insert(3,Element(QN(self.xdaqns, 'Endpoint').text, {'protocol':'%s'%self.ptprot , 'service':"i2o", "hostname":"RU%d_I2O_HOST_NAME"%(index), "port":"RU%d_I2O_PORT"%(index), "network":"infini"}))
		## Add builder network pt application
		addFragmentFromFile(target=ru_element, filename=self.fragmentdir+'/RU/%s/RU_%s_application.xml'%(self.evbns,self.ptprot), index=4) ## add after the two endpoints
		## Add corresponding module
		module = Element(QN(self.xdaqns, 'Module').text)
		module.text = "/opt/xdaq/lib/libpt%s.so"%self.ptprot
		ru_element.insert(5,module)

		## Add frl routing
		frl_routing_element = ru_element.find(QN(self.xdaqns,'Application').text +'/'+ QN("urn:xdaq-application:pt::frl::Application",'properties').text +'/'+ QN("urn:xdaq-application:pt::frl::Application",'frlRouting').text)
		frl_routing_element.attrib[QN(self.soapencns, 'arrayType').text] = "xsd:ur-type[%d]"%(self.nferols/self.nrus)
		item_element = elementFromFile(self.fragmentdir+'/RU/%s/RU_frl_routing.xml'%self.evbns)
		item_element.find('className').text = "%s::RU"%self.evbns
		item_element.find('instance').text = "%d"%index

		frl_to_add = split_list(range(self.nferols*self.streams_per_ferol), self.nrus)[index]
		for n,frl in enumerate(frl_to_add):
			item_to_add = deepcopy(item_element)
			item_to_add.attrib[QN(self.soapencns, 'position').text] = '[%d]'%n
			item_to_add.find('fedid').text = str(FEDIDS[frl])
			frl_routing_element.append(item_to_add)

		## Set instance and url
		for app in ru_element.findall(QN(self.xdaqns, 'Application').text):
			if app.attrib['class'] != "%s::RU"%self.evbns: continue
			app.set('instance', str(index))
			break
		ru_element.set('url', ru_element.get('url')%(index, index))

		return ru_element
	def addRUs(self, nrus):
		for n in xrange(nrus):
			self.config.append(self.makeRU(n))
	def makeEVM(self):
		index = 0
		fragmentname = 'EVM/EVM.xml'
		evm_element = elementFromFile(self.fragmentdir+fragmentname)

		## Add policy
		addFragmentFromFile(target=evm_element, filename=self.fragmentdir+'/EVM/EVM_policy_%s.xml'%(self.ptprot), index=0)
		## Add builder network endpoint
		evm_element.insert(3,Element(QN(self.xdaqns, 'Endpoint').text, {'protocol':'%s'%self.ptprot , 'service':"i2o", "hostname":"EVM%d_I2O_HOST_NAME"%(index), "port":"EVM%d_I2O_PORT"%(index), "network":"infini"}))
		## Add builder network pt application
		addFragmentFromFile(target=evm_element, filename=self.fragmentdir+'/EVM/EVM_%s_application.xml'%(self.ptprot), index=4) ## add after the two endpoints
		## Add corresponding module
		module = Element(QN(self.xdaqns, 'Module').text)
		module.text = "/opt/xdaq/lib/libpt%s.so"%self.ptprot
		evm_element.insert(5,module)

		## Set instance and url
		for app in evm_element.findall(QN(self.xdaqns, 'Application').text):
			if app.attrib['class'] != "%s::EVM"%self.evbns: continue
			app.set('instance', str(index))
			break
		evm_element.set('url', evm_element.get('url')%(index, index))

		return evm_element
	def addEVM(self):
		self.config.append(self.makeEVM())
	def makeBU(self, index):
		fragmentname = 'BU/%s/BU.xml'%self.evbns
		bu_element = elementFromFile(self.fragmentdir+fragmentname)

		## Add policy
		addFragmentFromFile(target=bu_element, filename=self.fragmentdir+'/BU/%s/BU_policy_%s.xml'%(self.evbns,self.ptprot), index=0)
		## Add builder network endpoint
		bu_element.insert(3,Element(QN(self.xdaqns, 'Endpoint').text, {'protocol':'%s'%self.ptprot , 'service':"i2o", "hostname":"BU%d_I2O_HOST_NAME"%(index), "port":"BU%d_I2O_PORT"%(index), "network":"infini"}))
		## Add builder network pt application
		addFragmentFromFile(target=bu_element, filename=self.fragmentdir+'/BU/%s/BU_%s_application.xml'%(self.evbns,self.ptprot), index=4) ## add after the two endpoints
		## Add corresponding module
		module = Element(QN(self.xdaqns, 'Module').text)
		module.text = "/opt/xdaq/lib/libpt%s.so"%self.ptprot
		bu_element.insert(5,module)

		## Set instance and url
		for app in bu_element.findall(QN(self.xdaqns, 'Application').text):
			if app.attrib['class'] != "%s::BU"%self.evbns: continue
			app.set('instance', str(index))
			break
		bu_element.set('url', bu_element.get('url')%(index, index))

		return bu_element
	def addBUs(self, nbus):
		for n in xrange(nbus):
			self.config.append(self.makeBU(n))

	def writeConfig(self, destination):
		with open(destination, 'w') as file:
			file.write(ElementTree.tostring(self.config))
			file.close()
		subprocess.call(['xmllint', '--format', '--nsclean', destination, '-o', destination])
		with open(destination, 'r') as oldfile:
			lines = oldfile.readlines()
			lines.remove('<?xml version="1.0"?>\n')
			with open(destination+'temp', 'w') as newfile:
				for line in lines:
					newfile.write(line)
		subprocess.call(['mv', '-f', destination+'temp', destination])




	def makeConfig(self, nferols=8, streams_per_ferol=2, nrus=1, nbus=2, destination='configuration.template.xml'):
		self.nrus              = nrus
		self.nbus              = nbus
		self.nferols           = nferols
		self.streams_per_ferol = streams_per_ferol

		##
		self.makeSkeleton()
		self.addI2OProtocol()
		self.addFerolControllers(nferols=nferols, streams_per_ferol=streams_per_ferol)
		self.addRUs(nrus=nrus)
		self.addEVM()
		self.addBUs(nbus=nbus)
		self.writeConfig(destination)


