############################################################
# Program is part of PySAR v2.0                            #
# Copyright(c) 2017, Heresh Fattahi, Zhang Yunjun          #
# Author:  Heresh Fattahi, Zhang Yunjun, 2017              #
############################################################


import os, sys, glob
import h5py
import numpy as np
from pysar.utils import readfile, datetime as ptime, utils as ut
from pysar.objects import ifgramDatasetNames, geometryDatasetNames

dataType = np.float32

########################################################################################
class ifgramStack:
    '''
    IfgramStack object for a set of InSAR pairs from the same platform and track.

    Example:
        from pysar.objects.ifgramStack import ifgramStack
        pairsDict = {('20160524','20160530'):ifgramObj1,
                     ('20160524','20160605'):ifgramObj2,
                     ('20160524','20160611'):ifgramObj3,
                     ('20160530','20160605'):ifgramObj4,
                     ...
                     }
        stackObj = ifgramStack(pairsDict=pairsDict)
        stackObj.save2h5(outputFile='ifgramStack.h5', box=(200,500,300,600))
    '''

    def __init__(self, name='ifgramStack', pairsDict=None):
        self.name = name
        self.pairsDict = pairsDict

    def get_size(self, box=None):
        self.numIfgram = len(self.pairsDict)
        ifgramObj = [v for v in self.pairsDict.values()][0]
        self.length, ifgramObj.width = ifgramObj.get_size()
        if box:
            self.length = box[3] - box[1]
            self.width = box[2] - box[0]
        else:
            self.length = ifgramObj.length
            self.width = ifgramObj.width
        return self.numIfgram, self.length, self.width

    def get_metadata(self):
        ifgramObj = [v for v in self.pairsDict.values()][0]
        self.metadata = ifgramObj.get_metadata()
        return self.metadata

    def get_dataset_data_type(self, dsName):
        ifgramObj = [v for v in self.pairsDict.values()][0]
        dsFile = ifgramObj.datasetDict[dsName]
        metadata = readfile.read_attribute(dsFile)
        dsDataType = dataType
        if 'DATA_TYPE' in metadata.keys():
            dsDataType = readfile.dataTypeDict[metadata['DATA_TYPE'].lower()]
        return dsDataType

    def save2h5(self, outputFile='ifgramStack.h5', access_mode='w', box=None):
        '''Save/write an ifgramStack object into an HDF5 file with the structure below:

        /ifgramStack           Root level group name
            Attributes         Dictionary for metadata
            /date              2D array of string  in size of (m, 2   ) in YYYYMMDD format for master and slave date
            /bperp             1D array of float32 in size of (m,     ) in meter.
            /dropIfgram        1D array of bool    in size of (m,     ).
            /unwrapPhase       3D array of float32 in size of (m, l, w) in radian.
            /coherence         3D array of float32 in size of (m, l, w).
            /connectComponent  3D array of int16   in size of (m, l, w).           (optional)
            /wrapPhase         3D array of float32 in size of (m, l, w) in radian. (optional)
            /rangeOffset       3D array of float32 in size of (m, l, w).           (optional)
            /azimuthOffset     3D array of float32 in size of (m, l, w).           (optional)

        Parameters: outputFile : string
                        Name of the HDF5 file for the InSAR stack
                    access_mode : string
                        Access mode of output File, e.g. w, r+
                    box : tuple
                        Subset range in (x0, y0, x1, y1)
        Returns:    outputFile
        '''

        self.outputFile = outputFile
        f = h5py.File(self.outputFile, access_mode)
        print('create HDF5 file {} with {} mode'.format(self.outputFile, access_mode))

        groupName = self.name
        group = f.create_group(groupName)
        print('create group   /{}'.format(groupName))

        self.pairs = [pair for pair in self.pairsDict.keys()]
        self.dsNames = list(self.pairsDict[self.pairs[0]].datasetDict.keys())
        maxDigit = max([len(i) for i in self.dsNames])
        self.get_size(box)

        self.bperp = np.zeros(self.numIfgram)
        ###############################
        # 3D datasets containing unwrapPhase, coherence, connectComponent, wrapPhase, etc.
        for dsName in self.dsNames:
            #dsDataType = self.get_dataset_data_type(dsName)
            dsDataType = dataType
            if dsName in ['connectComponent']:
                dsDataType = np.bool_
            dsShape = (self.numIfgram, self.length, self.width)
            print('create dataset /{g}/{d:<{w}} of {t} in size of {s}'.format(g=groupName, d=dsName, \
                                                                              w=maxDigit, t=dsDataType, s=dsShape))
            ds = group.create_dataset(dsName, shape=dsShape, maxshape=(None, dsShape[1], dsShape[2]),\
                                      dtype=dsDataType, chunks=True)

            progBar = ptime.progress_bar(maxValue=self.numIfgram)
            for i in range(self.numIfgram):
                ifgramObj = self.pairsDict[self.pairs[i]]
                data = ifgramObj.read(dsName, box=box)[0]
                ds[i,:,:] = data
                self.bperp[i] = ifgramObj.get_perp_baseline()
                progBar.update(i+1, suffix='{}-{}'.format(self.pairs[i][0],self.pairs[i][1]))
            progBar.close()

        ###############################
        # 2D dataset containing master and slave dates of all pairs
        dsDateName = 'date'
        print('create dataset /{}/{}'.format(groupName, dsDateName))
        dsDate = group.create_dataset(dsDateName, data=np.array(self.pairs, dtype=np.string_))

        ###############################
        # 1D dataset containing perpendicular baseline of all pairs
        # practice resizable matrix here for update mode
        dsBperpName = 'bperp'
        print('create dataset /{}/{}'.format(groupName, dsBperpName))
        if dsBperpName not in group.keys():
            dsBperp = group.create_dataset(dsBperpName, shape=(self.numIfgram,), maxshape=(None,), dtype=dataType)
        else:
            dsBperp = group.get(dsBperpName)
            dsBperp.resize(self.numIfgram, axis=0)
        dsBperp[:] = self.bperp

        ###############################
        # 1D dataset containing bool value of dropping the interferograms or not
        dsDateName = 'dropIfgram'
        print('create dataset /{}/{}'.format(groupName, dsDateName))
        dsDate = group.create_dataset(dsDateName, data=np.ones((self.numIfgram), dtype=np.bool_))

        ###############################
        # Attributes
        self.get_metadata()
        self.metadata = ut.subset_attribute(self.metadata, box)
        for key,value in self.metadata.items():
            group.attrs[key] = value

        f.close()
        print('Finished writing to {}'.format(self.outputFile))
        return self.outputFile


########################################################################################
class ifgram:
    """
    Ifgram object for a single InSAR pair of interferogram. It includes dataset name (family) of:
        'unwrapPhase','coherence','connectComponent','wrapPhase','iono','rangeOffset','azimuthOffset', etc.

    Example:
        from pysar.objects.ifgramStack import ifgram
        datasetDict = {'unwrapPhase'     :'$PROJECT_DIR/merged/interferograms/20151220_20160206/filt_fine.unw',
                       'coherence'       :'$PROJECT_DIR/merged/interferograms/20151220_20160206/filt_fine.cor',
                       'connectComponent':'$PROJECT_DIR/merged/interferograms/20151220_20160206/filt_fine.unw.conncomp',
                       'wrapPhase'       :'$PROJECT_DIR/merged/interferograms/20151220_20160206/filt_fine.int',
                       ...
                      }
        ifgramObj = ifgram(dates=('20160524','20160530'), datasetDict=datasetDict)
        data, atr = ifgramObj.read('unwrapPhase')
    """
    def __init__(self, name='ifgram', dates=None, datasetDict={}, metadata=None):
        self.name = name
        self.masterDate, self.slaveDate = dates
        self.datasetDict = datasetDict

        self.platform = None
        self.track = None
        self.processor = None
        # platform, track and processor can get values from metadat if they exist   
        if metadata is not None:
            for key , value in metadata.items():
                setattr(self, key, value)

    def read(self, family, box=None):
        self.file = self.datasetDict[family]
        data, metadata = readfile.read(self.file, box=box)
        return data, metadata

    def get_size(self):
        self.file = self.datasetDict[ifgramDatasetNames[0]]
        metadata = readfile.read_attribute(self.file)
        self.length = int(metadata['LENGTH'])
        self.width = int(metadata['WIDTH'])
        return self.length, self.width

    def get_perp_baseline(self):
        self.file = self.datasetDict[ifgramDatasetNames[0]]
        metadata = readfile.read_attribute(self.file)
        self.bperp_top = float(metadata['P_BASELINE_TOP_HDR'])
        self.bperp_bottom = float(metadata['P_BASELINE_BOTTOM_HDR'])
        self.bperp = (self.bperp_top + self.bperp_bottom) / 2.0
        return self.bperp

    def get_metadata(self, family=ifgramDatasetNames[0]):
        self.file = self.datasetDict[family]
        self.metadata = readfile.read_attribute(self.file)
        self.length = int(self.metadata['LENGTH'])
        self.width = int(self.metadata['WIDTH'])

        if self.processor is None:
            ext = self.file.split('.')[-1]
            if os.path.exists(self.file+'.xml'):
                self.processor = 'isce' 
            elif os.path.exists(self.file+'.rsc'):
                self.processor = 'roipac'
            elif os.path.exists(self.file+'.par'):
                self.processor = 'gamma'
            elif ext == 'grd':
                self.processor = 'gmtsar'
            #what for DORIS/SNAP
            elif 'PROCESSOR' in self.metadata.keys():
                self.processor = self.metadata['PROCESSOR']               
            else:
                self.processor = 'isce'
        self.metadata['PROCESSOR'] = self.processor

        if self.track:
            self.metadata['TRACK'] = self.track

        if self.platform:
            self.metadata['PLATFORM'] = self.platform

        return self.metadata


########################################################################################
class geometry:
    '''
    Geometry object for Lat, Lon, Heigt, Incidence, Heading, Bperp, ... from the same platform and track.

    Example:
        from pysar.utils import readfile
        from pysar.utils.insarobj import geometry
        datasetDict = {'height'        :'$PROJECT_DIR/merged/geom_master/hgt.rdr',
                       'latitude'      :'$PROJECT_DIR/merged/geom_master/lat.rdr',
                       'longitude'     :'$PROJECT_DIR/merged/geom_master/lon.rdr',
                       'incidenceAngle':'$PROJECT_DIR/merged/geom_master/los.rdr',
                       'heandingAngle' :'$PROJECT_DIR/merged/geom_master/los.rdr',
                       'shadowMask'    :'$PROJECT_DIR/merged/geom_master/shadowMask.rdr',
                       ...
                      }
        metadata = readfile.read_attribute('$PROJECT_DIR/merged/interferograms/20160629_20160723/filt_fine.unw')
        geomObj = geometry(processor='isce', datasetDict=datasetDict, metadata=metadata)
        geomObj.save2h5(outputFile='geometryRadar.h5', access_mode='w', box=(200,500,300,600))
    '''

    def __init__(self, name='geometry', processor=None, datasetDict={}, ifgramMetadata=None):
        self.name = name
        self.processor = processor
        self.datasetDict = datasetDict
        self.ifgramMetadata = ifgramMetadata

    def read(self, family, box=None):
        self.file = self.datasetDict[family]
        data, metadata = readfile.read(self.file, epoch=family, box=box)
        return data, metadata

    def get_slantRangeDistance(self, box=None):
        if not self.ifgramMetadata or 'Y_FIRST' in self.ifgramMetadata.keys():
            return None
        data = ut.range_distance(self.ifgramMetadata, dimension=2, printMsg=False)
        if box is not None:
            data = data[box[1]:box[3],box[0]:box[2]]
        return data

    def get_incidenceAngle(self, box=None):
        if not self.ifgramMetadata or 'Y_FIRST' in self.ifgramMetadata.keys():
            return None
        data = ut.incidence_angle(self.ifgramMetadata, dimension=2, printMsg=False)
        if box is not None:
            data = data[box[1]:box[3],box[0]:box[2]]
        return data

    def get_size(self, box=None):
        self.file = self.datasetDict[geometryDatasetNames[0]]
        metadata = readfile.read_attribute(self.file)
        if box:
            length = box[3] - box[1]
            width = box[2] - box[0]
        else:
            length = int(metadata['LENGTH'])
            width = int(metadata['WIDTH'])
        return length, width

    def get_metadata(self, family=geometryDatasetNames[0]):
        self.file = self.datasetDict[family]
        self.metadata = readfile.read_attribute(self.file)
        self.length = int(self.metadata['LENGTH'])
        self.width = int(self.metadata['WIDTH'])
        if self.processor is None:
            ext = self.file.split('.')[-1]
            if 'PROCESSOR' in self.metadata.keys():
                self.processor = self.metadata['PROCESSOR']
            elif os.path.exists(self.file+'.xml'):
                self.processor = 'isce' 
            elif os.path.exists(self.file+'.rsc'):
                self.processor = 'roipac'
            elif os.path.exists(self.file+'.par'):
                self.processor = 'gamma'
            elif ext == 'grd':
                self.processor = 'gmtsar'
            #what for DORIS/SNAP
            else:
                self.processor = 'isce'
        self.metadata['PROCESSOR'] = self.processor
        return self.metadata


    def save2h5(self, outputFile='geometryRadar.h5', access_mode='w', box=None):
        '''
        /geometry                    Root level group name
            Attributes               Dictionary for metadata. 'X/Y_FIRST/STEP' attribute for geocoded.
            /height                  2D array of float32 in size of (l, w   ) in meter.
            /latitude (azimuthCoord) 2D array of float32 in size of (l, w   ) in degree.
            /longitude (rangeCoord)  2D array of float32 in size of (l, w   ) in degree.
            /incidenceAngle          2D array of float32 in size of (l, w   ) in degree.
            /slantRangeDistance      2D array of float32 in size of (l, w   ) in meter.
            /headingAngle            2D array of float32 in size of (l, w   ) in degree. (optional)
            /shadowMask              2D array of bool    in size of (l, w   ).           (optional)
            /waterMask               2D array of bool    in size of (l, w   ).           (optional)
            /bperp                   3D array of float32 in size of (n, l, w) in meter   (optional)
            ...
        '''
        if len(self.datasetDict) == 0:
            print('No dataset file path in the object, skip HDF5 file writing.')
            return None

        self.outputFile = outputFile
        f = h5py.File(self.outputFile, access_mode)
        print('create HDF5 file {} with {} mode'.format(self.outputFile, access_mode))

        groupName = self.name
        group = f.create_group(groupName)
        print('create group   /{}'.format(groupName))

        self.dsNames = list(self.datasetDict.keys())
        maxDigit = max([len(i) for i in self.dsNames])
        length, width = self.get_size(box)

        ###############################
        # 2D datasets containing height, latitude, incidenceAngle, shadowMask, etc.
        for dsName in self.dsNames:
            #dsDataType = self.get_dataset_data_type(dsName)
            dsDataType = dataType
            if dsName.lower().endswith('mask'):
                dsDataType = np.bool_
            dsShape = (length, width)
            print('create dataset /{g}/{d:<{w}} of {t} in size of {s}'.format(g=groupName, d=dsName, w=maxDigit, t=dsDataType, s=dsShape))
            ds = group.create_dataset(dsName, shape=dsShape, dtype=dsDataType, chunks=True)
            data = self.read(family=dsName, box=box)[0]
            ds[:] = data

            #progBar = ptime.progress_bar(maxValue=self.numIfgram)
            #for i in range(self.numIfgram):
            #    ifgramObj = self.pairsDict[self.pairs[i]]
            #    data = ifgramObj.read(dsName, box=box)[0]
            #    ds[i,:,:] = data
            #    self.bperp[i] = ifgramObj.get_perp_baseline()
            #    progBar.update(i+1, suffix='{}-{}'.format(self.pairs[i][0],self.pairs[i][1]))
            #progBar.close()

        dsName = 'incidenceAngle'
        if dsName not in self.dsNames:
            data = self.get_incidenceAngle(box=box)
            if data is not None:
                print('create dataset /{}/{} of {} in size of {}'.format(groupName, dsName, dataType, dsShape))
                ds = group.create_dataset(dsName, data=data, dtype=dataType, chunks=True)

        dsName = 'slantRangeDistance'
        if dsName not in self.dsNames:
            data = self.get_slantRangeDistance(box=box)
            if data is not None:
                print('create dataset /{}/{} of {} in size of {}'.format(groupName, dsName, dataType, dsShape))
                ds = group.create_dataset(dsName, data=data, dtype=dataType, chunks=True)

        ###############################
        # Attributes
        self.get_metadata()
        self.metadata = ut.subset_attribute(self.metadata, box)
        for key,value in self.metadata.items():
            group.attrs[key] = value

        f.close()
        print('Finished writing to {}'.format(self.outputFile))
        return self.outputFile


########################################################################################
class platformTrack:

    def __init__(self, name='platformTrack'): #, pairDict = None):
        self.pairs = None
         
    def getPairs(self, pairDict, platTrack):
        pairs = pairDict.keys()
        self.pairs = {}
        for pair in pairs:
            if pairDict[pair].platform_track == platTrack:
                self.pairs[pair]=pairDict[pair]

    def getSize_geometry(self, dsName):
        pairs = self.pairs.keys()
        pairs2 = []
        width = []
        length = []
        files = []
        for pair in pairs:
            self.pairs[pair].get_metadata(dsName)
            if self.pairs[pair].length != 0 and self.pairs[pair].file not in files:
                files.append(self.pairs[pair].file)
                pairs2.append(pair)
                width.append(self.pairs[pair].width)
                length.append(self.pairs[pair].length)

        length = median(length)
        width  = median(width)
        return pairs2, length, width
 
    def getSize(self): 
        pairs = self.pairs.keys()
        self.numPairs = len(pairs)
        width = []
        length = []
        for pair in pairs:
            length.append(self.pairs[pair].length)
            width.append(self.pairs[pair].width)
        self.length = median(length)
        self.width  = median(width)

    def getDatasetNames(self): 
        # extract the name of the datasets which are actually the keys of 
        # observations, quality and geometry dictionaries.

        pairs = [pair for pair in self.pairs.keys()]
        # Assuming all pairs of a given platform-track have the same observations 
        # let's extract the keys of the observations of the first pair.
         
        if self.pairs[pairs[0]].observationsDict is not None: 
            self.dsetObservationNames = [k for k in self.pairs[pairs[0]].observationsDict.keys()]
        else:
            self.dsetObservationNames = []

        # Assuming all pairs of a given platform-track have the same quality files
        # let's extract the keys of the quality dictionary of the first pair. 
        if self.pairs[pairs[0]].qualityDict is not None:
            self.dsetQualityNames = [k for k in self.pairs[pairs[0]].qualityDict.keys()]                
        else:
            self.dsetQualityNames = []

        ##################
        # Despite the observation and quality files, the geometry may not exist
        # for all pairs. Therfore we need to look at all pairs and get possible 
        # dataset names.
        self.dsetGeometryNames = []
        for pair in pairs:
            if self.pairs[pair].geometryDict  is not None:
                keys = [k for k in self.pairs[pair].geometryDict.keys()]       
                self.dsetGeometryNames = list(set(self.dsetGeometryNames) | set(keys))
