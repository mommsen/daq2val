import os
import sys
import subprocess
import re
import time
from copy import deepcopy
from pprint import pprint

from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement
from xml.etree.ElementTree import QName as QN
from xml.parsers.expat import ExpatError

from daq2Utils import printError, printProgress
from daq2FEDConfiguration import daq2ProdFEDConfiguration, FRLNode, RUNode
from daq2Configurator import elementFromFile, addFragmentFromFile
from daq2Configurator import RU_STARTING_TID, BU_STARTING_TID
from daq2Configurator import FEROL_OPERATION_MODES

######################################################################
from daq2Configurator import daq2Configurator
class daq2ProdConfigurator(daq2Configurator):
	'''
---------------------------------------------------------------------
  class daq2ProdConfigurator

---------------------------------------------------------------------
'''
	def __init__(self, fragmentdir, hwInfo, canonical=False, canonlength=8,
		         dry=False, verbose=5):
		super(daq2ProdConfigurator, self).__init__(fragmentdir,
			                                       verbose=verbose)

		self.hwInfo = hwInfo
		# self.symbMap = symbMap ## can get this info also from hwInfo?

		self.canonical = canonical
		self.canonlength = canonlength
		self.dry = dry

		## Counters
		self.haveEVM = False
		self.ruindex = 0
		self.ferolindex = 0
		self.allRUs = []
		self.allFEROLs = []


	def makeFEROLConfig(self, ferol):
		self.makeSkeleton()
		self.config.append(self.makeFerolController(ferol))
		isevm = (ferol.ruindex==self.allRUs[0].index)
		self.addRUContextWithGEEndpoint(ferol.ruindex, isEVM=isevm)
		outputname = 'FEROLCONTROLLER%d.xml' % ferol.index
		self.writeConfig(os.path.join(self.outPutDir,outputname))
	def makeEVMConfig(self, ru):
		self.makeSkeleton()
		ru_instances = [r.index for r in self.allRUs[1:]]
		self.addI2OProtocol(rus_to_add=ru_instances,
			                evminst=self.allRUs[0].index)

		## add the EVM
		self.config.append(self.makeRU(ru, isEVM=True))
		for index in ru_instances:
			self.addRUContextWithIBEndpoint(index)
		for index in xrange(self.nbus):
			self.addBUContextWithIBEndpoint(index)

		outputname = 'RU%d.xml' % ru.index
		self.writeConfig(os.path.join(self.outPutDir,outputname))
	def makeRUConfig(self, ru):
		self.makeSkeleton()
		self.addI2OProtocol(rus_to_add=[ru.index],
			                evminst=self.allRUs[0].index)

		self.config.append(self.makeRU(ru))
		self.addRUContextWithIBEndpoint(self.allRUs[0].index, isEVM=True)
		for index in xrange(self.nbus):
			self.addBUContextWithIBEndpoint(index)
		outputname = 'RU%d.xml' % ru.index
		self.writeConfig(os.path.join(self.outPutDir,outputname))
	def makeBUConfig(self, buindex):
		self.makeSkeleton()
		## no RU, only one BU
		self.addI2OProtocol(rus_to_add=[], bus_to_add=[buindex],
			                evminst=self.allRUs[0].index)
		self.config.append(self.makeBU(buindex))
		self.addRUContextWithIBEndpoint(self.allRUs[0].index, isEVM=True)
		outputname = 'BU%d.xml' % buindex
		self.writeConfig(os.path.join(self.outPutDir,outputname))
	def makeFullConfig(self):
		self.makeSkeleton()
		ru_instances = [r.index for r in self.allRUs[1:]]
		self.addI2OProtocol(rus_to_add=ru_instances)

		for ferol in self.allFEROLs:
			self.config.append(self.makeFerolController(ferol))

		## add the EVM
		for ru in self.allRUs:
			isevm = False
			if ru.index == 0: isevm = True
			self.config.append(self.makeRU(ru, isEVM=isevm))

		for index in xrange(self.nbus):
			self.config.append(self.makeBU(index))

		outputname = 'full.xml'
		self.writeConfig(os.path.join(self.outPutDir,outputname))

	def assignFEROLsToRUs(self, rus, ferols):
		ferols_gen = (f for f in ferols if f.nstreams > 0)
		ferols_rest = [f for f in ferols if f.nstreams == 0]
		rus_gen = (r for r in rus)

		## First make an EVM
		if not self.haveEVM:
			evm = rus_gen.next()
			evm_frl = ferols_gen.next()
			evm_frl.ruindex = evm.index
			evm_frl.runame = evm.hostname
			evm_frl.nstreams = 1
			evm_frl.fedIds = (evm_frl.fedIds[0], None)
			evm.addFRL(evm_frl)
			self.haveEVM = True

		try:
			for n,f in enumerate(ferols_gen):
				if n%8==0: ru = rus_gen.next()
				f.ruindex = ru.index
				f.runame  = ru.hostname
				ru.addFRL(f)

		except StopIteration:
			print f
			printError('Running out of RUs for %s'%
				        self.hwInfo.ge_host_cabling[rus[0].hostname], self)

		if self.verbose>5:
			for f in ferols_rest:
				print 'unused FEROL:', f
			for r in rus_gen:
				print 'unused RU:', r
	def makeConfigs(self, geswitches):
		for switchname in geswitches:
			# get a list of frlpcs, ferols, and rus from the hwInfo
			frlpcs = self.hwInfo.getListOfFRLPCs(switchname)
			runames = self.hwInfo.getAllRUs(switchname)

			## Number the RUs
			RUs_onswitch = []
			for runame in runames:
				runode = RUNode(self.ruindex, hostname=runame)
				self.allRUs.append(runode)
				RUs_onswitch.append(runode)
				self.ruindex += 1
			if len(RUs_onswitch) == 0: continue

			FEROLs_onswitch = []
			for frlpc in frlpcs:
				for ferol in self.hwInfo.getFEROLs(frlpc,
					         haveFEDIDs=self.canonlength/8):
					ferol.index = self.ferolindex
					self.allFEROLs.append(ferol)
					FEROLs_onswitch.append(ferol)
					self.ferolindex += 1
			if len(FEROLs_onswitch) == 0: continue

			## Assign FEROLs to RUs
			self.assignFEROLsToRUs(RUs_onswitch, FEROLs_onswitch)

		## Remove unused RUs
		usedRUs = []
		for r in self.allRUs:
			if len(r.getFedIds()) != 0:
				usedRUs.append(r)
		self.allRUs = usedRUs

		## Remove unused FEROLs
		usedFEROLs = []
		for f in self.allFEROLs:
			if f.ruindex >= 0:
				usedFEROLs.append(f)
		self.allFEROLs = usedFEROLs

		## Now make sure the EVM has index and instance 0!
		oldevmindex = self.allRUs[0].index
		## And make sure the FEROL sending to the evm sends to 0
		self.allRUs[0].index = 0
		for ferol in self.allFEROLs:
			if ferol.ruindex == oldevmindex:
				ferol.ruindex = 0

		if self.verbose>5:
			print 70*'-'
			for f in self.allFEROLs:
				print f

		if self.verbose>1:
			print 70*'-'
			for r in self.allRUs:
				print r, r.getFedIds()
			print 70*'-'


		if self.dry: return

		for n,ferol in enumerate(self.allFEROLs):
			printProgress(n,len(self.allFEROLs),customstr='FEROLs: ')
			self.makeFEROLConfig(ferol)
		print ''

		self.makeEVMConfig(self.allRUs[0])

		for n,ru in enumerate(self.allRUs[1:]):
			printProgress(n,len(self.allRUs)-1,customstr='RUs: ')
			self.makeRUConfig(ru)
		print ''

		for n in xrange(self.nbus):
			printProgress(n,self.nbus,customstr='BUs: ')
			self.makeBUConfig(n)
		print ''

		self.makeFullConfig()

		if self.verbose>0:
			print 70*'-'
			print ' Wrote configs to %s' % self.outPutDir
			print 70*'-'

	def printSetup(self, filename):
		with open(filename, 'w') as outfile:
			outfile.write(115*'-'+'\n')
			nfeds = len([i for r in self.allRUs for i in r.getFedIds()])
			outfile.write("%d FEDs, %d FEROLs, %d RUs, %d BUs" % (
				           nfeds, len(self.allFEROLs),
				           len(self.allRUs), self.nbus))
			outfile.write('\n')
			outfile.write(115*'-'+'\n')
			for r in self.allRUs:
				outfile.write("%-22s"%str(r))
				outfile.write("%2d FEROLs, "%len(r.frls))
				outfile.write("%2d FEDs: "%len(r.getFedIds()))
				fedstr = '%4d '*len(r.getFedIds())
				fedstr = fedstr % tuple([int(i) for i in r.getFedIds()])
				outfile.write(fedstr)
				outfile.write('\n')
			outfile.write(115*'-'+'\n')
			for f in self.allFEROLs:
				outfile.write(str(f))
				outfile.write('\n')
			outfile.write(115*'-'+'\n')

			outfile.write('\n\n')
			outfile.close()


