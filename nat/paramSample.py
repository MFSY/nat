# -*- coding: utf-8 -*-
"""
Created on Tue Aug 15 17:14:30 2017

@author: oreilly
"""

from warnings import warn

from .modelingParameter import NumericalVariable, ParamDescTrace, ValuesSimple, \
    getParameterTypeIDFromName, getParameterTypeNameFromID

from .annotationSearch import ParameterGetter
from .zoteroWrap import ZoteroWrap
from .ageResolver import AgeResolver
from quantities import Quantity

class ParamSample:
    
    def __init__(self, searcher, libraryId=None, libraryType=None, apiKey=None):
        
        self.searcher = searcher
        self.sampleDF = searcher.search()
        if not libraryId is None and not libraryType is None and not apiKey is None:
            self.zotWrap = ZoteroWrap()
            self.zotWrap.loadCachedDB(libraryId, libraryType, apiKey)
        else:
            self.zotWrap = None
            
        self.ageUnit = "day"
        
        # For the conversion of age categories (e.g., adult) to 
        # numerical values. "min" species the lower bound of the interval.
        # For example, rats are adult from 5 months up to their dead (around 2-3.5 years)
        # setting this parametes to min, 5 months will be attributed as numerical
        # value for the age "adult" in rats.
        self.ageTypeValue = "min"
            
    def setZoteroLib(self, libraryId, libraryType, apiKey):
        self.zotWrap = ZoteroWrap()
        self.zotWrap.loadCachedDB(libraryId, libraryType, apiKey)    



    def rescaleUnit(self, unit, rescaleStereo=True):
        
        def rescale2DStereo(paramID, thicknessValue, thicknessUnit, desiredUnit):
            density = paramGetter.getParam(paramID)
            thickness = Quantity(thicknessValue, thicknessUnit)
            return (density/thickness).rescale(desiredUnit)        
        
        
        paramGetter = ParameterGetter(pathDB=self.searcher.pathDB)
        for param, annot, (index, row) in zip(self.sampleDF["obj_parameter"], 
                                              self.sampleDF["obj_annotation"], 
                                              self.sampleDF.iterrows()):
                                                  
            if param.unit == unit:
                continue
                                                  
            try:
                param = param.rescale(unit)
            except ValueError:
            
                if rescaleStereo:
                    thicknessInstanceId = [param.instanceId for param in annot.experimentProperties 
                                            if getParameterTypeNameFromID(param.paramTypeId) == "slice_thickness"]
         
                    if len(thicknessInstanceId) == 1:
                        thicknessParameter = paramGetter.getParam(thicknessInstanceId[0])
                        if len(thicknessParameter.values) == 1:
                            param = rescale2DStereo(param.id, thicknessValue=thicknessParameter.values[0], 
                                                    thicknessUnit=thicknessParameter.unit, 
                                                    desiredUnit=unit)
                            self.sampleDF.loc[index, "obj_parameter"] = param   
                            self.sampleDF.loc[index, "Values"]        = param.valuesText()   
                            self.sampleDF.loc[index, "Unit"]          = param.unit                   
                            continue
                
                warn("The annotation with the parameter ID " + row["Parameter instance ID"] + 
                     " cannot be rescaled from unit " + 
                     str(param.unit) + " to unit " + str(unit) + ". Dropping this record.")
                del row
                continue                

            if Quantity(1, param.unit) != Quantity(1, unit):
                warn("The annotation with the parameter ID " + row["Parameter instance ID"] + 
                     " cannot be rescaled from unit " + 
                     str(param.unit) + " to unit " + str(unit) + ". Dropping this record.")
                del row
                continue                            
                
            self.sampleDF.loc[index, "obj_parameter"] = param   
            self.sampleDF.loc[index, "Values"]        = param.valuesText()   
            self.sampleDF.loc[index, "Unit"]          = param.unit   




    def reformatAsNumericalTraces(self, indepVarName = None, indepVarId = None):
        if not indepVarName is None:
            if not indepVarId is None:
                if getParameterTypeNameFromID(indepVarId) != indepVarName:
                    raise ValueError("Parameters indepVarName and indepVarId "
                                    + "passed to ParamSample.reformatAsNumericalTraces() are incompatible.")
            else:
                indepVarId = getParameterTypeIDFromName(indepVarName)
        else:
            if indepVarId is None:
                raise ValueError("At least one of the attribute indepVarName and indepVarId "
                                    + "passed to ParamSample.reformatAsNumericalTraces() most not be None.")
            indepVarName = getParameterTypeNameFromID(indepVarId)
                

        for noRow, row in self.sampleDF.iterrows():
        
            if row["Result type"] == "pointValue":
                indepVar = row[indepVarName]
                depVar   = row["obj_parameter"].description.depVar
                indepVar = NumericalVariable(typeId = indepVarId, 
                                             values = ValuesSimple([float(indepVar)], unit=str(indepVar.dimensionality)))
                row["obj_parameter"].description = ParamDescTrace(depVar, [indepVar])
                row["Result type"] = "numericalTrace"


        
    def preprocess(self, steps):
        for step in steps:
            getattr(self, "preprocess_" + step)()
        
    
    def preprocess_species(self):
        speciesId = []
        species   = []
        for noRow, row in self.sampleDF.iterrows():
            tags =row["Species"]
            if len(tags) > 1 :
                warn("The annotation with the parameter ID " + row["Parameter instance ID"] + 
                     " is associated with more than one species (" + 
                     str([tag.name for tag in tags]) 
                     + "). The species cannot be automatically attributed unambiguously. " +
                     "Skipping this record.")
                del row
                continue
                
            speciesId.append(tags[0].id)
            species.append(tags[0].name)
            
        self.sampleDF["SpeciesId"] = speciesId
        self.sampleDF["Species"]   = species


    def preprocess_age(self):    
        if not "SpeciesId" in self.sampleDF:
            self.preprocess_species()
            
        ageCategoryIds = []
        ageCategories  = []
        numericalAges  = []
        for noRow, row in self.sampleDF.iterrows():
            
            # First check if an experimental property with age as been attributed to the record            
            ageExpProp = [expProp.instanceId for expProp in row["obj_annotation"].experimentProperties if expProp.paramTypeId == 'BBP-002001']
            if len(ageExpProp) > 1 :
                warn("The annotation with the parameter ID " + row["Parameter instance ID"] + 
                     " is associated with more than one species age experimental properties." + 
                     +" The age cannot be automatically attributed unambiguously. " +
                     "Skipping this record.")
                del row
                continue   
            
            if len(ageExpProp) == 1 :
                getter = ParameterGetter(pathDB=self.searcher.pathDB)
                
                ageParam = getter.getParam(ageExpProp[0])
                
                ageCategoryIds.append(None)
                ageCategories.append(None)        
                numericalAges.append(Quantity(ageParam.means[0], ageParam.unit).rescale(self.ageUnit))

            # No experimental property attributed. Check to use a age category if one has been attributed.
            else:
                tags = row["AgeCategories"]
                if len(tags) > 1 :
                    warn("The annotation with the parameter ID " + row["Parameter instance ID"] + 
                         " is associated with more than one age categories (" + 
                         str([tag.name for tag in tags]) 
                         + "). The age cannot be automatically attributed unambiguously. " +
                         "Skipping this record.")
                    del row
                    continue  
                    
                if len(tags) == 0:
                    ageCategoryIds.append(None)
                    ageCategories.append(None)
                    numericalAges.append(None)
                    continue
                
                ageCategoryIds.append(tags[0].id)
                ageCategories.append(tags[0].name)
                age = AgeResolver.resolve_fromIDs(row["SpeciesId"], tags[0].id, unit=self.ageUnit, 
                                                  typeValue=self.ageTypeValue) 
                numericalAges.append(age)

        self.sampleDF["AgeCategoryId"] = ageCategoryIds
        self.sampleDF["AgeCategory"]   = ageCategories
        self.sampleDF["age"]           = numericalAges

    
    def preprocess_ref(self):    
        if self.zotWrap is None:
            raise ValueError("To add references to the sample, you need first to set " +
                             "the Zotero library by calling LitSample.setZoteroLib()")

        self.sampleDF["ref"] = [self.zotWrap.getInTextCitationFromID(annot.pubId) 
                                           for annot in self.sampleDF["obj_annotation"]]
    