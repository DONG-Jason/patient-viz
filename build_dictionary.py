#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Mon Oct 13 11:44:00 2014

@author: joschi
@author: razavian
"""
from __future__ import print_function
import time
import datetime
import shelve
from datetime import datetime,timedelta
import sys
import csv
#import simplejson as json
import json
import os.path

import util

debugOutput = False

class EntryCreator(object):
    def __init__(self):
        self._baseTypes = {}
        self._codeTables = {}
        self._unknown = None

    def baseType(self, name):
        def wrapper(cls):
            obj = cls()
            if not isinstance(obj, TypeBase):
                raise TypeError("{0} is not a {1}".format(cls.__name__, TypeBase.__name__))
            self._baseTypes[name] = obj
            return cls
        return wrapper

    def codeType(self, name, code):
        def wrapper(cls):
            obj = cls()
            if not isinstance(obj, TypeCode):
                raise TypeError("{0} is not a {1}".format(cls.__name__, TypeCode.__name__))
            self._baseTypes[name].addCodeType(code, obj)
            return cls
        return wrapper

    def unknownType(self):
        def wrapper(cls):
            obj = cls()
            if not isinstance(obj, TypeBase):
                raise TypeError("{0} is not a {1}".format(cls.__name__, TypeBase.__name__))
            self._unknown = obj
        return wrapper

    def createEntry(self, dict, type, id, onlyAddMapped=False):
        if not id:
            entry = self.createRootEntry(type)
        else:
            baseType = self._baseTypes.get(type, self._unknown)
            symbols = self._codeTables.get(type, {})
            entry = baseType.create(symbols, type, id)
        if type not in dict:
            dict[type] = {}
        if onlyAddMapped and 'unmapped' in entry and entry['unmapped']:
            return
        dict[type][id] = entry
        pid = entry['parent']
        if pid not in dict[type]:
            self.createEntry(dict, type, pid, False)
        if 'alias' in entry:
            aid = entry['alias']
            if aid not in dict[type]:
                self.createEntry(dict, type, aid, True)

    def createRootEntry(self, type):
        baseType = self._baseTypes.get(type, self._unknown)
        name = baseType.name()
        if name == UNKNOWN:
            name += " " + type
        desc = baseType.desc()
        if desc == UNKNOWN:
            desc += " " + type
        res = toEntry("", "", name, desc)
        res["color"] = baseType.color()
        flags = baseType.flags()
        if len(flags.keys()):
            res["flags"] = flags
        return res

    def init(self, settings):
    	global globalSymbolsFile
    	global icd9File
    	global pntFile
    	global ccs_diag_file
    	global ccs_proc_file
    	global productFile
    	global packageFile
    	globalSymbolsFile = settings['filename']
    	icd9File = settings['icd9']
    	pntFile = settings['pnt']
    	ccs_diag_file = settings['ccs_diag']
    	ccs_proc_file = settings['ccs_proc']
    	productFile = settings['ndc_prod']
    	packageFile = settings['ndc_package']
    	for k in self._baseTypes.keys():
            self._codeTables[k] = self._baseTypes[k].init()

dictionary = EntryCreator()

class TypeBase(object):
    def __init__(self):
        self._codeTypes = {}
    def name(self):
        raise NotImplementedError()
    def desc(self):
        return self.name()
    def color(self):
        raise NotImplementedError()
    def flags(self):
        return {}
    def addCodeType(self, code, codeType):
        self._codeTypes[code] = codeType
    def init(self):
        res = {}
        for code in self._codeTypes.keys():
            res[code] = self._codeTypes[code].init()
        return res
    def create(self, symbols, type, id):
        candidate = None
        for k in self._codeTypes.keys():
            can = self._codeTypes[k].create(symbols[k], type, id)
            if "unmapped" in can and can["unmapped"]:
                continue
            if candidate is not None:
                candidate = None
                if debugOutput:
                    print("ambiguous type {0} != {1}".format(repr(candidate), repr(can), file=sys.stderr))
                break
            candidate = can
        if candidate is None:
            return createUnknownEntry({}, type, id)
        return candidate

class TypeCode(object):
    def init(self):
        raise NotImplementedError()
    def create(self, symbols, type, id):
        raise NotImplementedError

### provider ###
@dictionary.baseType("provider")
class TypeProvider(TypeBase):
    def name(self):
        return "Provider"
    def color(self):
        return "#e6ab02"

@dictionary.codeType("provider", "pnt")
class PntProviderCode(TypeCode):
    def create(self, symbols, type, id):
        pid = id[2:4] if len(id) >= 4 else ""
        if id in symbols:
            return toEntry(id, pid, symbols[id], symbols[id])
        if len(id) == 2:
            return createUnknownEntry(symbols, type, id, pid)
        return toEntry(id, pid, id, "Provider Number: {0}".format(id))
    def init(self):
        res = {}
        if not os.path.isfile(getFile(pntFile)):
            return res
        with open(getFile(pntFile), 'r') as pnt:
            for line in pnt.readlines():
                l = line.strip()
                if len(l) < 10 or not l[0].isdigit() or not l[1].isdigit() or not l[5].isdigit() or not l[6].isdigit():
                    continue
                fromPN = int(l[0:2])
                toPN = int(l[5:7])
                desc = l[9:].strip()
                for pn in xrange(fromPN, toPN + 1):
                    res[("00" + str(pn))[-2:]] = desc
        return res

### physician ###
@dictionary.baseType("physician")
class TypePhysician(TypeBase):
    def name(self):
        return "Physician"
    def color(self):
        return "#fccde5"

@dictionary.codeType("physician", "cms")
class CmsPhysicianCode(TypeCode):
    def create(self, symbols, type, id):
        pid = ""
        return createUnknownEntry(symbols, type, id, pid)
    def init(self):
        return {}

### prescribed ###
@dictionary.baseType("prescribed")
class TypePrescribed(TypeBase):
    def name(self):
        return "Prescribed Medication"
    def color(self):
        return "#eb9adb"

@dictionary.codeType("prescribed", "ndc")
class NdcPrescribedCode(TypeCode):
    def create(self, symbols, type, id):
        pid = id[:-2] if len(id) == 11 else ""
        if id in symbols:
            l = symbols[id]
            return toEntry(id, pid, l["nonp"], l["nonp"]+" ["+l["desc"]+"] ("+l["prop"]+") "+l["subst"]+" - "+l["pharm"]+" - "+l["pType"], l["alias"] if "alias" in l else None)
        return createUnknownEntry(symbols, type, id, pid)
    def init(self):
        prescribeLookup = {}
        if not os.path.isfile(getFile(productFile)):
            return prescribeLookup
        uidLookup = {}
        with open(getFile(productFile), 'r') as prFile:
            for row in csv.DictReader(prFile, delimiter='\t', quoting=csv.QUOTE_NONE):
                uid = row['PRODUCTID'].strip()
                fullndc = row['PRODUCTNDC'].strip()
                ndcparts = fullndc.split('-')
                if len(ndcparts) != 2:
                    print("invalid NDC (2):" + fullndc + "  " + uid, file=sys.stderr)
                    continue
                normndc = ""
                if len(ndcparts[0]) == 4 and len(ndcparts[1]) == 4:
                    normndc = "0" + ndcparts[0] + ndcparts[1]
                elif len(ndcparts[0]) == 5 and len(ndcparts[1]) == 3:
                    normndc = ndcparts[0] + "0" + ndcparts[1]
                elif len(ndcparts[0]) == 5 and len(ndcparts[1]) == 4:
                    normndc = ndcparts[0] + ndcparts[1]
                else:
                    print("invalid split NDC (2):" + fullndc + "  " + uid, file=sys.stderr)
                    continue
                ndc = ndcparts[0] + ndcparts[1]
                ptn = row['PRODUCTTYPENAME'].strip()
                prop = row['PROPRIETARYNAME'].strip()
                nonp = row['NONPROPRIETARYNAME'].strip()
                subst = row['SUBSTANCENAME'].strip() if row['SUBSTANCENAME'] is not None else ""
                pharm = row['PHARM_CLASSES'].strip() if row['PHARM_CLASSES'] is not None else ""
                if uid in uidLookup:
                    print("warning duplicate uid: " + uid, file=sys.stderr)
                uidLookup[uid] = {
                    "pType": ptn,
                    "prop": prop,
                    "nonp": nonp,
                    "subst": subst,
                    "pharm": pharm
                }
                desc = nonp + " " + ptn
                l = uidLookup[uid]
                if ndc in prescribeLookup or normndc in prescribeLookup:
                    continue
                obj = {
                    "desc": desc,
                    "pType": l["pType"],
                    "prop": l["prop"],
                    "nonp": l["nonp"],
                    "subst": l["subst"],
                    "pharm": l["pharm"],
                    "alias": normndc
                }
                prescribeLookup[ndc] = obj
                prescribeLookup[normndc] = obj
                prescribeLookup[fullndc] = obj
        if not os.path.isfile(getFile(packageFile)):
            return prescribeLookup
        with open(getFile(packageFile), 'r') as paFile:
            for row in csv.DictReader(paFile, delimiter='\t', quoting=csv.QUOTE_NONE):
                uid = row['PRODUCTID'].strip()
                fullndc = row['NDCPACKAGECODE'].strip()
                ndcparts = fullndc.split('-')
                if len(ndcparts) != 3:
                    print("invalid NDC (3):" + fullndc + "  " + uid, file=sys.stderr)
                    continue
                normndc = ""
                if len(ndcparts[0]) == 4 and len(ndcparts[1]) == 4 and len(ndcparts[2]) == 2:
                    normndc = "0" + ndcparts[0] + ndcparts[1] + ndcparts[2]
                elif len(ndcparts[0]) == 5 and len(ndcparts[1]) == 3 and len(ndcparts[2]) == 2:
                    normndc = ndcparts[0] + "0" + ndcparts[1] + ndcparts[2]
                elif len(ndcparts[0]) == 5 and len(ndcparts[1]) == 4 and len(ndcparts[2]) == 1:
                    normndc = ndcparts[0] + ndcparts[1] + "0" + ndcparts[2]
                elif len(ndcparts[0]) == 5 and len(ndcparts[1]) == 4 and len(ndcparts[2]) == 2:
                    normndc = ndcparts[0] + ndcparts[1] + ndcparts[2]
                else:
                    print("invalid split NDC (3):" + fullndc + "  " + uid, file=sys.stderr)
                    continue
                ndc = ndcparts[0] + ndcparts[1] + ndcparts[2]
                desc = row['PACKAGEDESCRIPTION'].strip()
                if uid not in uidLookup:
                    #print("warning missing uid: " + uid, file=sys.stderr) // not that important since the non-packaged version is already added
                    continue
                l = uidLookup[uid]
                if ndc in prescribeLookup:
                    desc = prescribeLookup[ndc]["desc"] + " or " + desc
                obj = {
                    "desc": desc,
                    "pType": l["pType"],
                    "prop": l["prop"],
                    "nonp": l["nonp"],
                    "subst": l["subst"],
                    "pharm": l["pharm"],
                    "alias": normndc
                }
                prescribeLookup[ndc] = obj
                prescribeLookup[normndc] = obj
                prescribeLookup[fullndc] = obj
        return prescribeLookup

### lab-test ###
@dictionary.baseType("lab-test")
class TypeLabtest(TypeBase):
    def name(self):
        return "Laboratory Test"
    def color(self):
        return "#80b1d3"
    def flags(self):
        return {
            "L": {
                "color": "#fb8072"
            },
            "H": {
                "color": "#fb8072"
            },
        }

@dictionary.codeType("lab-test", "loinc")
class LoincLabtestCode(TypeCode):
    def create(self, symbols, type, id):
        pid = "" # find parent id
        if id in symbols:
            return toEntry(id, pid, symbols[id], symbols[id])
        return createUnknownEntry(symbols, type, id, pid)
    def init(self):
        return getGlobalSymbols()

### diagnosis ###
@dictionary.baseType("diagnosis")
class TypeDiagnosis(TypeBase):
    def name(self):
        return "Condition"
    def color(self):
        return "#4daf4a"

@dictionary.codeType("diagnosis", "icd9")
class LoincLabtestCode(TypeCode):
    def __init__(self):
        self._parents = {}
    def create(self, symbols, type, id):
        prox_id = id
        pid = ""
        while len(prox_id) >= 3:
            pid = self._parents[prox_id] if prox_id in self._parents else pid
            if prox_id in symbols:
                return toEntry(id, pid, symbols[prox_id], symbols[prox_id], id.replace(".", ""))
            prox_id = prox_id[:-1]
        return createUnknownEntry(symbols, type, id, pid)
    def init(self):
        codes = getGlobalSymbols()
        codes.update(getICD9())
        self._parents = readCCS(getFile(ccs_diag_file), codes)
        return codes

### procedure ###
@dictionary.baseType("procedure")
class TypeDiagnosis(TypeBase):
    def name(self):
        return "Procedure"
    def color(self):
        return "#ff7f00"

@dictionary.codeType("procedure", "icd9")
class LoincLabtestCode(TypeCode):
    def __init__(self):
        self._parents = {}
    def create(self, symbols, type, id):
        prox_id = id
        pid = ""
        while len(prox_id) >= 3:
            pid = self._parents[prox_id] if prox_id in self._parents else pid
            if prox_id in symbols:
                return toEntry(id, pid, symbols[prox_id], symbols[prox_id], id.replace(".", ""))
            prox_id = prox_id[:-1]
        return createUnknownEntry(symbols, type, id, pid)
    def init(self):
        codes = getGlobalSymbols()
        codes.update(getICD9())
        self._parents = readCCS(getFile(ccs_proc_file), codes)
        return codes

### unknown ###
UNKNOWN = "UNKNOWN"

@dictionary.unknownType()
class TypeUnknown(TypeBase):
    def name(self):
        return UNKNOWN
    def color(self):
        return "red"
    def init(self):
        raise NotImplementedError()
    def create(self, symbols, type, id):
        return createUnknownEntry(symbols, type, id)

def createUnknownEntry(_, type, id, pid = ""):
    # TODO remove: can be seen by attribute unmapped
    #if debugOutput:
    #    print("unknown entry; type: " + type + " id: " + id, file=sys.stderr)
    res = toEntry(id, pid, id, type + " " + id)
    res["unmapped"] = True
    return res

def toEntry(id, pid, name, desc, alias=None):
    res = {
        "id": id,
        "parent": pid,
        "name": name,
        "desc": desc
    }
    if alias is not None and alias != id:
        res["alias"] = alias
    return res

### icd9 ###

globalICD9 = {}

def getICD9():
    global globalICD9
    if not len(globalICD9.keys()):
        globalICD9 = initICD9()
    return globalICD9.copy()

def initICD9():
    codes = {}
    if not os.path.isfile(getFile(icd9File)):
        return codes
    with open(getFile(icd9File), 'r') as file:
        lastCode = ""
        for line in file:
            if len(line.strip()) < 2:
                lastCode = ""
                continue
            if not line[1].isdigit():
                if line[0] == ' ' and lastCode != "":
                    noDot = lastCode.replace(".", "")
                    codes[lastCode] = codes[lastCode] + " " + line.strip().rstrip('- ').rstrip()
                    codes[noDot] = codes[noDot] + " " + line.strip().rstrip('- ').rstrip()
                continue
            spl = line.split(None, 1)
            if len(spl) == 2:
                lastCode = spl[0].strip()
                noDot = lastCode.replace(".", "")
                codes[lastCode] = spl[1].rstrip().rstrip('- ').rstrip()
                codes[noDot] = spl[1].rstrip().rstrip('- ').rstrip()
            else:
                if line[0] != '(':
                    print("invalid ICD9 line: '" + line.rstrip() + "'", file=sys.stderr)
    return codes

### ccs ###

def readCCS(ccsFile, codes):
    parents = {}
    if not os.path.isfile(ccsFile):
        return codes
    with open(ccsFile, 'r') as file:
        cur = ""
        for line in file:
            if len(line) < 1:
                continue
            if not line[0].isdigit():
                if line[0] == ' ' and cur != "":
                    nums = line.split()
                    for n in nums:
                        parents[n] = cur
                continue
            spl = line.split(None, 1)
            if len(spl) == 2:
                par = spl[0].rstrip('0123456789').rstrip('.')
                cur = "HIERARCHY." + spl[0]
                parents[cur] = "HIERARCHY." + par if len(par) > 0 else ""
                codes[cur] = spl[1].rstrip('0123456789 \t\n\r')
            else:
                print("invalid CCS line: '" + line.rstrip() + "'", file=sys.stderr)
    return parents

### general lookup table ###

globalSymbols = {}

def getGlobalSymbols():
    global globalSymbols
    if not len(globalSymbols.keys()):
        globalSymbols = initGlobalSymbols()
    return globalSymbols.copy()

def initGlobalSymbols():
    codes_dict = {}
    if not os.path.isfile(getFile(globalSymbolsFile)):
        return codes_dict
    with open(getFile(globalSymbolsFile), 'r') as file:
        lines = file.readlines()
    for i in range(len(lines)):
        codeList = lines[i].split('#')[0].strip('\n');
        label = lines[i].split('#')[1].strip('\n')
        for code in codeList.split(" "):
            if code != '':
                codes_dict[code] = label
    return codes_dict

### filling dictionary ###

def extractEntries(dict, patient):
    for event in patient['events']:
        dictionary.createEntry(dict, event['group'], event['id'])

def loadOldDict(file):
    dict = {}
    if file == '-' or not os.path.isfile(file):
        return dict
    with open(file, 'r') as input:
        dict = json.loads(input.read())
    return dict

def enrichDict(file, mid):
    dict = loadOldDict(file)
    if mid == '-':
        patient = json.loads(sys.stdin.read())
    else:
        with open(mid, 'r') as pfile:
            patient = json.loads(pfile.read())
    extractEntries(dict, patient)
    with util.OutWrapper(file) as out:
        print(json.dumps(dict, indent=2), file=out)

### argument API

path_correction = './'
icd9File = 'code/icd9/ucod.txt'
ccs_diag_file = 'code/ccs/multi_diag.txt'
ccs_proc_file = 'code/ccs/multi_proc.txt'
productFile = 'code/ndc/product.txt'
packageFile = 'code/ndc/package.txt'
pntFile = 'code/pnt/pnt.txt'
globalSymbolsFile = 'code/icd9/code_names.txt'
globalMid = '2507387001'

def setPathCorrection(pc):
    global path_correction
    path_correction = pc

def getFile(file):
    res = os.path.join(path_correction, file)
    if debugOutput:
        print("exists: {0} file: {1}".format(repr(os.path.isfile(res)), repr(os.path.abspath(res))), file=sys.stderr)
    return res

def readConfig(settings, file):
    if file == '-':
        return
    config = {}
    if debugOutput:
        print("config exists: {0} file: {1}".format(repr(os.path.isfile(file)), repr(os.path.abspath(file))), file=sys.stderr)
    if os.path.isfile(file):
        with open(file, 'r') as input:
            config = json.loads(input.read())
    settings.update(config)
    if set(settings.keys()) - set(config.keys()):
        with open(file, 'w') as output:
            print(json.dumps(settings, indent=2), file=output)

def usage():
    print("{0}: [--debug] -p <file> -c <config> -o <output> [-h|--help] [--lookup <id...>]".format(sys.argv[0]), file=sys.stderr)
    print("--debug: prints debug information", file=sys.stderr)
    print("-p <file>: specify patient json file. '-' uses standard in", file=sys.stderr)
    print("-c <config>: specify config file. '-' uses default settings", file=sys.stderr)
    print("-o <output>: specify output file. '-' uses standard out", file=sys.stderr)
    print("--lookup <id...>: lookup mode. translates ids in shorthand notation '${group_id}__${type_id}'. '-' uses standard in with ids separated by spaces", file=sys.stderr)
    print("-h|--help: prints this help.", file=sys.stderr)
    sys.exit(1)

defaultSettings = {
    'filename': globalSymbolsFile,
    'ndc_prod': productFile,
    'ndc_package': packageFile,
    'icd9': icd9File,
    'pnt': pntFile,
    'ccs_diag': ccs_diag_file,
    'ccs_proc': ccs_proc_file,
}

def interpretArgs():
    global debugOutput
    settings = defaultSettings
    info = {
        'mid': globalMid,
        'output': '-'
    }
    lookupMode = False
    args = sys.argv[:]
    args.pop(0);
    while args:
        val = args.pop(0)
        if val == '-h' or val == '--help':
            usage()
        elif val == '-p':
            if not args:
                print('-p requires argument', file=sys.stderr)
                usage()
            info['mid'] = args.pop(0)
        elif val == '-c':
            if not args:
                print('-c requires argument', file=sys.stderr)
                usage()
            readConfig(settings, args.pop(0))
        elif val == '-o':
            if not args:
                print('-o requires argument', file=sys.stderr)
                usage()
            info['output'] = args.pop(0)
        elif val == '--lookup':
            lookupMode = True
            break
        elif val == '--debug':
            debugOutput = True
        else:
            print('illegal argument '+val, file=sys.stderr)
            usage()
    return (settings, info, lookupMode, args)

if __name__ == '__main__':
    (settings, info, lookupMode, rest) = interpretArgs()
    dictionary.init(settings)
    if lookupMode:
        dict = {}

        def addEntry(e):
            spl = e.split('__', 1)
            if len(spl) != 2:
                print("shorthand format is '${group_id}__${type_id}': " + e, file=sys.stderr)
                sys.exit(1)
            dictionary.createEntry(dict, spl[0].strip(), spl[1].strip())

        for e in rest:
            if e == "-":
                for eid in sys.stdin.read().split(" "):
                    if len(eid) > 0 and eid != "id" and eid != "outcome" and eid != "test":
                        addEntry(eid)
            else:
                addEntry(e)

        file = info['output']
        with util.OutWrapper(file) as out:
            print(json.dumps(dict, indent=2), file=out)
    else:
        enrichDict(info['output'], info['mid'])
