#! /usr/bin/env python
import sys, os

months_toint = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
months_tostr = {1:"Jan", 2:"Feb", 3:"Mar", 4:"Apr", 5:"May", 6:"Jun", 7:"Jul", 8:"Aug", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dec"}

##---------------------------------------------------------------------------------
## Utilities
def checkMSIO(filename):
	with open(filename, 'r') as f:
		if '#Server(0)' in f.readline():
			return True
		else: return False
	return False
def getConfig(string):
	"""Extract number of streams, readout units, builder units, and RMS from strings such as
	8x1x2 or 16s8fx2x4_RMS_0.5 (i.e 8,1,2,None in the first case, 16,2,4,0.5 in the second)
	"""
	import re
	string = string.split('_')
	case = string[0].split('x')
	rms = None
	strperfrl = 1
	pattern = re.compile(r'([0-9]+)s([0-9]+)f')
	if pattern.match(case[0]):
		nstreams = int(pattern.match(case[0]).group(1))
		if nstreams > int(pattern.match(case[0]).group(2)): strperfrl = 2

	else: nstreams = int(case[0])
	nrus = int(case[1]) ## Introduces notation: no _ before the trailing tags
	nbus = int(case[2])

	for i in xrange(len(string)):
		if string[i] == 'RMS':
			try:
				rms = float(string[i+1])
			except ValueError, StopIteration:
				print 'RMS needs to be a floating point number'
				rms = None

	return nstreams, nrus, nbus, rms, strperfrl
def processFile(filename, config, startfragsize=256):
	from numpy import mean, std
	from logNormalTest import averageFractionSize
	f = open(filename,'r')
	if not f: raise RuntimeError, "Cannot open "+filename+"\n"

	msio = checkMSIO(filename)

	## Process .csv file first
	data_dict = {} ## store everything in this dictionary of size -> rate
	for line in f:
		if len(line.strip()) == 0 or line.strip()[0] == '#': continue
		spline = line.replace("\n","").split(",")

		rate = map(lambda x: int(float(x)), spline[1:])

		if int(spline[0]) not in data_dict.keys(): ## first time seeing this size
			data_dict[int(spline[0])] = rate
		else: ## have already a line with this size
			prev_rate = data_dict[int(spline[0])]

			## Fix different sample sizes:
			if len(rate) > len(prev_rate):
				rate = rate[:len(prev_rate)]
			if len(rate) < len(prev_rate):
				prev_rate = prev_rate[:len(rate)]
			## Add to the previous samples
			data_dict[int(spline[0])] = map(lambda a,b:a+b, prev_rate, rate)


	nstreams, nrus, nbus, rms, strperfrl = config

	## If first line in file is "#Server(0)", divide the rates by the number of BUs
	if msio:
		for size in data_dict.keys():
			newrate = [a/nbus for a in data_dict[size]]
			data_dict[size] = newrate

		## IGNORE number of RUs now:
		nrus = 1


	# LOWERLIMIT=32
	LOWERLIMIT=24
	UPPERLIMIT=16000
	if nstreams/nrus==4:  UPPERLIMIT = 64000 ## This is only true for eFEROLs!
	if nstreams/nrus==8:  UPPERLIMIT = 32000
	if nstreams/nrus==12: UPPERLIMIT = 21000
	if nstreams/nrus==16: UPPERLIMIT = 16000
	if nstreams/nrus==24: UPPERLIMIT = 10000

	data = []

	output_case = 0 ## 0 (fragsize), 1 (superfragsize), 2 (eventsize)
	checked = False

	for size in sorted(data_dict.keys()):
		if abs(mean(data_dict[size])) < 0.01 and abs(std(data_dict[size])) < 0.01: continue ## skip empty lines

		## Determine what the first item in the server.csv file stands for
		if not checked: ## only do this for the first time
			checked = True
			if   int(size)//startfragsize == 1:             output_case = 0 ## size = fragment size
			elif int(size)//startfragsize == nstreams/nrus: output_case = 1 ## size = superfragment size
			elif int(size)//startfragsize == nstreams:      output_case = 2 ## size = event size
			else:                                           output_case = 1 ## default

		## Extract event size
		eventsize = float(size)*nstreams ## default (output_case == 0)
		if output_case == 1:
			eventsize = float(size)*nrus
		if output_case == 2:
			eventsize = float(size)

		## Calculate fragment and super fragment sizes
		fragsize    = eventsize/nstreams
		sufragsize  = eventsize/nrus
		if rms is not None and rms != 0.0:
			fragsize = averageFractionSize(eventsize/nstreams, rms*eventsize/nstreams, LOWERLIMIT, UPPERLIMIT)
			sufragsize = fragsize*nstreams/nrus

		## Calculate rate
		avrate      = mean(data_dict[size])
		stdrate     = std(data_dict[size])
		throughput  = sufragsize*avrate/1e6 ## in MB/s
		throughputE = sufragsize*stdrate/1e6

		data.append((fragsize, throughput, throughputE))

	f.close()
	return data
def extractDate(filename):
	with open(filename, 'r') as f:
		for line in f:
			if line.startswith('## Testcase:'): continue
			if line.startswith('## useLogNormal'): continue
			if len(line.split(' ')) == 0: return (0,0,0)
			data = line.split(' ')
			if data[0] != '##': continue
			mon, day, year = (data[2],data[3][:-1],data[4])
			return day, mon, year
			# return int(day), int(months_toint[mon]), int(year)
		return (0,0,0)

##---------------------------------------------------------------------------------
## Plotting and printing
def printTable(filename):
	casestring = os.path.dirname(filename).split('/')[-1]
	config = getConfig(casestring)
	nstreams, nrus, nbus, rms, strperfrl = config
	data = processFile(filename, config)
	print "--------------------------------------------------------------------------------------"
	print "Case: " + casestring
	print "--------------------------------------------------------------------------------------"
	print "Superfrag. Size (B) : Fragment Size (B) : Av. Throughput (MB/s) :       Av. Rate     :"
	print "--------------------------------------------------------------------------------------"
	for	fragsize,tp,tpE in data:
		sufragsize = fragsize*nstreams/nrus
		print "             %6d :            %6d :      %6.1f +- %6.1f :  %8.1f +- %6.1f" % \
		(sufragsize, fragsize, tp, tpE, tp*1e6/sufragsize, tpE*1e6/sufragsize)

	print "--------------------------------------------------------------------------------------"
def makeMultiPlot(filelist, rangey=(0,5500), rangex=(250,17000), oname='', frag=True, nologx=False, logy=False, tag='', subtag='', legends=[], makePNGs=True, rate=100):
	from ROOT import gROOT, gStyle, TFile, TTree, gDirectory, TGraphErrors, TCanvas, TLegend, TH2D, TLatex, TPave
	from operator import itemgetter

	## Build caselist
	caselist = []
	for filename in filelist: caselist.append(os.path.dirname(filename).split('/')[-1])

	gROOT.SetBatch()
	gStyle.SetOptStat(0)

	if oname.endswith('.pdf') or oname.endswith('.png'): oname = oname[:-4]
	if len(oname)==0: ## default
		oname = 'plot_' + reduce(lambda x,y:x+'_'+y, caselist)

	canv = TCanvas(oname, "Plot", 0, 0, 1024, 768)
	canv.cd()
	if not nologx: canv.SetLogx()
	if logy: canv.SetLogy()
	canv.SetGridx()
	canv.SetGridy()
	## Cosmetics
	# canv.DrawFrame(rangex[0], rangey[0], rangex[1], rangey[1])
	axes = TH2D('axes', 'A', 100, rangex[0], rangex[1], 100, rangey[0], rangey[1])
	axes.GetYaxis().SetTitle("Av. Throughput per RU (MB/s)")
	axes.GetYaxis().SetTitleOffset(1.4)
	axes.GetXaxis().SetTitleOffset(1.2)
	axes.SetTitle("Throughput vs. Fragment Size")
	axes.GetXaxis().SetTitle("Fragment Size (bytes)")
	axes.GetXaxis().SetMoreLogLabels()
	axes.GetXaxis().SetNoExponent()
	axes.Draw()

	tl = TLatex()
	tl.SetTextFont(42)
	tl.SetNDC(1)
	if len(tag) > 0:
		width = 0.12+0.020*len(tag)
		if width > 0.9: width=0.899
		pave = TPave(0.12, 0.80, width, 0.899, 0, 'NDC')
		pave.SetFillStyle(1001)
		pave.SetFillColor(0)
		pave.Draw()
	if len(subtag) > 0:
		width2 = 0.12+0.015*len(subtag)
		if width2 > 0.9: width2=0.899
		pave2 = TPave(0.12, 0.75, width2, 0.899, 0, 'NDC')
		pave2.SetFillStyle(1001)
		pave2.SetFillColor(0)
		pave2.Draw()
	if len(tag) > 0:
		tl.SetTextSize(0.05)
		tl.DrawLatex(0.14, 0.83, tag)
	if len(subtag) > 0:
		tl.SetTextSize(0.035)
		tl.DrawLatex(0.145, 0.77, subtag)


	# if len(tag) > 0:
	# 	width = 0.019*len(tag)
	# 	print width
	# 	pave = TPaveText(0.12, 0.80, 0.12+width, 0.899, 'NDC')
	# 	pave.SetTextFont(42)
	# 	pave.SetTextSize(0.05)
	# 	pave.SetFillStyle(1001)
	# 	pave.SetFillColor(0)
	# 	pave.SetBorderSize(0)
	# 	pave.SetTextAlign(11)
	# 	pave.AddText(tag)
	# 	pave.Draw()

	# if len(subtag) > 0:
	# 	width = 0.019*len(subtag)
	# 	print width
	# 	pave2 = TPaveText(0.12, 0.75, 0.12+width, 0.799, 'NDC')
	# 	pave2.SetTextFont(42)
	# 	pave2.SetTextSize(0.035)
	# 	pave2.SetFillStyle(1001)
	# 	pave2.SetFillColor(0)
	# 	pave2.SetBorderSize(0)
	# 	pave2.SetTextAlign(11)
	# 	pave2.AddText(subtag)
	# 	pave2.Draw()

	graphs = []
	configs = set()
	for filename,case in zip(filelist,caselist):
		try:
			graphs.append(getGraph(filename))
			nstreams, nrus, nbus, rms, strperfrl = getConfig(case)
			if checkMSIO(filename): nrus = 1 ## ignore number of RUs if MSIO
			configs.add(nstreams//nrus) ## care only about Nstreams per RU
		except AttributeError:
			print "#### Couldn't get graph for ", case, "in file", filename
			return

	datepave = drawDate(filelist[0])
	datepave.Draw()

	# if args.daq1:
	# 	daq1_graph = getDAQ1Graph()

	configs = sorted(configs)
	nlegentries = len(filelist)
	# nlegentries = len(caselist) if not args.daq1 else len(caselist) + 1
	legendpos = (0.44, 0.13, 0.899, 0.20+nlegentries*0.05)
	# if args.legendPos == 'TL':
	# 	legendpos = (0.12, 0.82-nlegentries*0.05, 0.579, 0.898)
	# 	# legendpos = (0.12, 0.71-nlegentries*0.05, 0.579, 0.78)
	leg = TLegend(legendpos[0], legendpos[1], legendpos[2], legendpos[3])
	leg.SetFillStyle(1001)
	leg.SetFillColor(0)
	leg.SetTextFont(42)
	leg.SetTextSize(0.033)
	leg.SetBorderSize(0)

	colors  = [1,2,3,4,51,95]
	markers = [20,21,22,23,34,33]

	if len(legends) > 0 and len(legends) != len(filelist):
		print "Legends doesn't match with filelist, falling back to default"

	for n,graph in enumerate(graphs):
		graph.SetLineColor(colors[n])
		graph.SetMarkerColor(colors[n])
		graph.SetMarkerStyle(markers[n])

		if len(legends) == len(filelist) and len(legends)>0: ## Custom legends
			leg.AddEntry(graph, legends[n], 'P')
		else: ## Default
			leg.AddEntry(graph, caselist[n], 'P')
		# if args.daq1:
		# 	leg.AddEntry(daq1_graph, 'DAQ1 (2011)', 'P')
		graph.Draw("PL")

	# if args.daq1:
	# 	daq1_graph.Draw("PL")

	for n,streams_per_ru in enumerate(configs):
		func = getRateGraph(streams_per_ru, frag=frag, rate=rate, xmax=rangex[1])
		func.SetLineColor(colors[n])
		func.SetLineWidth(1)
		func.DrawCopy("same")
		leg.AddEntry(func, '%.0f kHz (%d streams)'% (rate, streams_per_ru), 'l')

	leg.Draw()

	for graph in graphs: graph.Draw("PL")

	canv.Print(oname + '.pdf')
	if makePNGs:  canv.Print(oname + '.png')
	# if args.makePNGs:  canv.Print(oname + '.png')
	# if args.makeCFile: canv.SaveAs(oname + '.C')
def getRateGraph(nStreams=4, frag=False, xmax=100000, rate=100):
	'''Returns a TF1 object corresponding to the average throughput at the RU
	necessary for a 100kHz rate of events of a given (super)fragment size '''
	from ROOT import TF1
	rate *= 0.001 ## convert from kHz to MHz
	if frag: rate *= nStreams
	f = TF1("Const Rate", "%f*x"%rate, 0, xmax)
	f.SetLineWidth(1)
	f.SetLineColor(1)
	f.SetLineStyle(2)
	return f
def getGraph(filename):
	casestring = os.path.dirname(filename).split('/')[-1]
	config = getConfig(casestring)
	nstreams, nrus, nbus, rms, strperfrl = config
	data = processFile(filename, config)

	from ROOT import TFile, TTree, gDirectory, TGraphErrors, TCanvas
	from array import array

	nsteps = len(data)
	g = TGraphErrors(nsteps)

	## Loop on the data
	for	n,(fragsize,tp,tpE) in enumerate(data):
		g.SetPoint(      n, fragsize, tp)
		g.SetPointError( n,       0., tpE)

	g.SetLineWidth(2)
	g.SetMarkerSize(1.7)

	return g
def drawDate(filename):
	from ROOT import TPaveText
	day,month,year = extractDate(filename)

	date_string = "%s %s %s" % (day, month, year)
	pave = TPaveText(0.005, 0.005, 0.1, 0.02, 'NDC')
	pave.SetTextFont(42)
	pave.SetTextSize(0.03)
	pave.SetFillStyle(1001)
	pave.SetFillColor(0)
	pave.SetBorderSize(0)
	pave.SetTextAlign(12)
	pave.AddText(date_string)
	return pave

##---------------------------------------------------------------------------------
## User interface
def addPlottingOptions(parser):
	# parser.usage = usage
	parser.add_argument("-o",  "--outputName", default="plot.pdf", action="store",  type=str,   dest="outputName",        help="File for plot output [default: %(default)s]")
	parser.add_argument("-t",  "--tag",        default="",         action="store",  type=str,   dest="tag",               help="Title tag in plot canvas")
	parser.add_argument("-t2", "--subtag",     default="",         action="store",  type=str,   dest="subtag",            help="Subtitle tag in plot canvas")
	parser.add_argument("--outdir",            default="",         action="store",  type=str,   dest="outdir",            help="Output directory for the plots")
	parser.add_argument('--legend',            default=[],         action="append", type=str,   dest="legend", nargs='*', help='Give a list of custom legend entries to be used')
	parser.add_argument("-r", "--rate",        default="100",      action="store",  type=float, dest="rate",              help="Rate in kHz to be displayed on the plot: [default: %(default)s kHz]")
	parser.add_argument("-q", "--quiet",       default=False,      action="store_true",         dest="quiet",             help="Do not print the tables")

	parser.add_argument("--miny",   default="0",     action="store", type=float, dest="miny",   help="Y axis range, minimum")
	parser.add_argument("--maxy",   default="5500",  action="store", type=float, dest="maxy",   help="Y axis range, maximum")
	parser.add_argument("--minx",   default="250",   action="store", type=float, dest="minx",   help="X axis range, minimum")
	parser.add_argument("--maxx",   default="17000", action="store", type=float, dest="maxx",   help="X axis range, maximum")
	parser.add_argument("--nologx", default=False,   action="store_true",          dest="nologx", help="Do not use logarithmic scale on x axis")
	parser.add_argument("--logy",   default=False,   action="store_true",          dest="logy",   help="Use logarithmic scale on y axis")

	# parser.add_argument("--legendPos", default="BR", action="store", type=str, dest="legendPos", help="Position for legend, either 'TL' (top left), 'TR' (top right), 'BL' (bottom left), 'BR'  (bottom right) [default: %(default)s]")
	# parser.add_argument("--makePNGs", default=True, action="store_true", dest="makePNGs", help="Produce also .png file")
	# parser.add_argument("--makeCFile", default=True, action="store_true", dest="makeCFile", help="Produce also .C file")

def buildFileList(inputlist):
	filelist = []
	for location in inputlist:
		if os.path.isfile(location) and os.path.splitext(location)[1] == '.csv':
			filelist.append(location)
		elif os.path.isdir(location) and 'server.csv' in os.listdir(location):
			filelist.append(location+'/server.csv')
		else: pass
	if len(filelist) < 1:
		print "No server.csv files found!"
		exit(-1)
	else: return filelist

if __name__ == "__main__":
	usage = """
	Plots event rates in .csv files as throughput per RU vs fragment size.
	Give .csv files or directories containing a 'server.csv' files as input.

	Examples:
	%(prog)s server.csv
	%(prog)s 20s10fx1x4_RMS_0.0/ 20s10fx1x4_FRL_AutoTrigger_RMS_0.0/ temp/custom.csv --tag 'FEROLs/EvB 20s10fx1x4' --legend 'FEROL AutoTrigger' 'FRL AutoTrigger' 'Custom'
	"""
	from argparse import ArgumentParser
	parser = ArgumentParser(usage)
	addPlottingOptions(parser)
	parser.add_argument("inputlist", metavar='file_or_dir', type=str, nargs='+', help='The .csv files or directories (containing .csv files) to be plotted.')
	args = parser.parse_args()

	## Argument is a csv file
	if len(args.inputlist) > 0:
		filelist = buildFileList(args.inputlist)
		if not args.quiet:
			for filename in filelist: printTable(filename)
		if args.outdir: args.outputName = args.outdir + '/' + args.outputName
		legends=[]
		if len(args.legend)>0: legends=args.legend[0]
		makeMultiPlot(filelist, rangey=(args.miny, args.maxy), rangex=(args.minx, args.maxx), tag=args.tag, subtag=args.subtag, legends=legends, frag=True, oname=args.outputName, nologx=args.nologx, logy=args.logy, rate=args.rate)
		exit(0)

	parser.print_help()
	exit(-1)
