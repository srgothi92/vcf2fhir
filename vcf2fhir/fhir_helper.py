import os
import json
import fhirclient.models.diagnosticreport as dr
import fhirclient.models.codeableconcept as concept
import fhirclient.models.meta as meta
import fhirclient.models.resource as resource
import fhirclient.models.observation as observation
import fhirclient.models.fhirreference as reference 
import fhirclient.models.fhirdate as date
import fhirclient.models.range as valRange
import fhirclient.models.medicationstatement as medication
from collections import OrderedDict
from uuid import uuid4
from .geneRefSeq import _getRefSeqByChrom
from .common import _Utilities

class _Fhir_Helper:
    def __init__(self, *args, **kwargs):
        self.report = dr.DiagnosticReport()
        self.phasedRecMap = {}   
        self.region_ids = []
        self.map_variant_ids = {}
        self.seq_ids = []
        self.obsContained = []

    def _get_no_call_components(self, no_call_filename, conv_region_filename):
        no_call_exist = False     
        if (no_call_filename and conv_region_filename):
            noCallRegion,queryRange = _Utilities.getNoCallableData(no_call_filename, conv_region_filename)
            nocallRows = len(noCallRegion.index)
            start = queryRange.at[0,"START"]
            end = queryRange.at[0,"END"]
            if not noCallRegion.empty:
                if noCallRegion['START'].iloc[0] <= queryRange['START'].iloc[0]:
                    noCallRegion['START'].iloc[0] = queryRange['START'].iloc[0]

                if noCallRegion['END'].iloc[-1] >= queryRange['END'].iloc[0]:
                    noCallRegion['END'].iloc[-1] = queryRange['END'].iloc[0]
                no_call_exist = True
        
        #component Region-studied (No call region)
        nocallComponents = []
        observation_rs_components = []
        if no_call_exist:   
            for i in range (nocallRows):
                nocallComponents.append('observation_rs_component'+str(i+4))
            for (index, i) in zip(noCallRegion.index, nocallComponents):
                i = observation.ObservationComponent()
                i.code = concept.CodeableConcept({"coding": [{ "system": "http://loinc.org","code": "TBD-noCallRegion","display": "No call region"}]})
                observation_rs_components.append(i)
        return observation_rs_components

    def _addPhaseRecords(self, record):
        if(record.samples[0].phased == False):
           return 
        sampleData = record.samples[0].data
        if(sampleData.GT != None and len(sampleData.GT.split('|')) >= 2 and sampleData.PS != None):
            self.phasedRecMap.setdefault(sampleData.PS, []).append(record)  

    def initalizeReport(self, patientID):
        patient_reference = reference.FHIRReference({"reference":"Patient/"+patientID})
        self.report.id = "dr-"+uuid4().hex[:13]
        self.report.meta = meta.Meta({"profile":["http://hl7.org/fhir/uv/genomics-reporting/StructureDefinition/genomics-report"]})
        self.report.status = "final"
        self.report.code = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"81247-9","display":"Master HL7 genetic variant reporting panel"}]})
        self.report.subject = patient_reference
        self.report.issued = date.FHIRDate(_Utilities.getFhirDate())
        self.report.contained = []

    def add_regionstudied_obv(self, no_call_filename, conv_region_filename, patientID):
        refSeq = ''
        patient_reference = reference.FHIRReference({"reference":"Patient/"+patientID})
        contained_uid = uuid4().hex[:13]
        self.region_ids.append(contained_uid)
        # Region Studied Obeservation
        observation_rs = observation.Observation()
        contained_rs = observation_rs
        contained_rs.id = "rs-"+contained_uid
        observation_rs.resource_type = "Observation"
        contained_rs.meta = meta.Meta({"profile":["http://hl7.org/fhir/uv/genomics-reporting/StructureDefinition/region-studied"]})
        observation_rs.code = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"53041-0","display":"DNA region of interest panel"}]})
        observation_rs.status = "final"
        observation_rs.category = [concept.CodeableConcept({"coding":[{"system": "http://terminology.hl7.org/CodeSystem/observation-category","code": "laboratory"}]})]
        observation_rs.subject = patient_reference

        observation_rs_component2 = observation.ObservationComponent()
        observation_rs_component2.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "92822-6","display": "Genomic coord system"}]})
        observation_rs_component2.valueCodeableConcept = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"LA30102-0","display": "1-based character counting"}]})

        observation_rs_component3 = observation.ObservationComponent()
        observation_rs_component3.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "48013-7","display": "Genomic reference sequence ID"}]})
        observation_rs_component3.valueCodeableConcept = concept.CodeableConcept({"coding":[{"system":"http://www.ncbi.nlm.nih.gov/nuccore","code":refSeq}]})
        
        observation_rs_components = self._get_no_call_components(no_call_filename, conv_region_filename)
        observation_rs.component = [observation_rs_component2,observation_rs_component3] + observation_rs_components
        # Observation structure : described-variants
        self.report.contained.append(contained_rs)

    def add_variant_obv(self, record, ref_build, patientID):        
        # collect all the record with similar position values,
        # to utilized later in phased sequence relationship
        self._addPhaseRecords(record)
        patient_reference = reference.FHIRReference({"reference":"Patient/"+patientID})
        alleles = _Utilities.getAllelicState(record)
        refSeq = _getRefSeqByChrom(ref_build, record.CHROM)
        dvuid = uuid4().hex[:13]
        self.map_variant_ids.update({ str(record.POS) : dvuid})

        observation_dv = observation.Observation()
        observation_dv.resource_type = "Observation"
        observation_dv.id = "dv-"+dvuid
        observation_dv.meta = meta.Meta({"profile":["http://hl7.org/fhir/uv/genomics-reporting/StructureDefinition/variant"]})
        observation_dv.status = "final"
        observation_dv.category = [concept.CodeableConcept({"coding":[{"system": "http://terminology.hl7.org/CodeSystem/observation-category","code": "laboratory"}]})]
        observation_dv.code = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"69548-6","display":"Genetic variant assessment"}]})
        observation_dv.subject = patient_reference
        observation_dv.valueCodeableConcept = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"LA9633-4","display":"present"}]})

        observation_dv_component1 = observation.ObservationComponent()
        observation_dv_component1.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "62374-4","display": "Human reference sequence assembly version"}]})
        observation_dv_component1.valueCodeableConcept = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "LA14029-5","display": "GRCh37"}]})

        observation_dv_component2 = observation.ObservationComponent()
        observation_dv_component2.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "48013-7","display": "Genomic reference sequence ID"}]})
        observation_dv_component2.valueCodeableConcept = concept.CodeableConcept({"coding": [{"system": "http://www.ncbi.nlm.nih.gov/nuccore","code": refSeq}]})

        observation_dv_component3 = observation.ObservationComponent()
        observation_dv_component3.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "53034-5","display": "Allelic state"}]})
        observation_dv_component3.valueCodeableConcept = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": alleles['CODE'],"display": alleles['ALLELE']}]})        

        observation_dv_component4 = observation.ObservationComponent()
        observation_dv_component4.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "69547-8","display": "Genomic Ref allele [ID]"}]})
        observation_dv_component4.valueString = record.REF

        observation_dv_component5 = observation.ObservationComponent()
        observation_dv_component5.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "69551-0","display": "Genomic Alt allele [ID]"}]})
        observation_dv_component5.valueString = record.ALT[0].sequence

        observation_dv_component6 = observation.ObservationComponent()
        observation_dv_component6.code = concept.CodeableConcept({"coding": [{"system": "http://loinc.org","code": "92822-6","display": "Genomic coord system"}]})
        observation_dv_component6.valueCodeableConcept = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"LA30102-0","display":"1-based character counting"}]})

        observation_dv_component7 = observation.ObservationComponent()
        observation_dv_component7.code = concept.CodeableConcept({"coding": [{"system": "http://hl7.org/fhir/uv/genomics-reporting/CodeSystem/tbd-codes","code": "exact-start-end","display": "Variant exact start and end"}]})
        observation_dv_component7.valueRange = valRange.Range({"low": {"value": int(record.POS)}})

        observation_dv.component =  [observation_dv_component1,observation_dv_component2,observation_dv_component3,observation_dv_component4,observation_dv_component5,observation_dv_component6,observation_dv_component7]
        self.report.contained.append(observation_dv)

    def add_phased_relationship_obv(self, patientID):
        patient_reference = reference.FHIRReference({"reference":"Patient/"+patientID})
        self.sequenceRels = _Utilities.getSequenceRelation(self.phasedRecMap)
        for index in self.sequenceRels.index:
            dvRef1 = self.map_variant_ids.get(str(self.sequenceRels.at[index,'POS1']))
            dvRef2 = self.map_variant_ids.get(str(self.sequenceRels.at[index,'POS2']))
            siduid = uuid4().hex[:13]
            self.seq_ids.append(siduid)

            observation_sid = observation.Observation()
            observation_sid.resource_type = "Observation"
            observation_sid.id = "sid-"+siduid
            observation_sid.meta = meta.Meta({"profile":["http://hl7.org/fhir/uv/genomics-reporting/StructureDefinition/sequence-phase-relationship"]})
            observation_sid.status = "final"
            observation_sid.category = [concept.CodeableConcept({"coding":[{"system": "http://terminology.hl7.org/CodeSystem/observation-category","code": "laboratory"}]})]
            observation_sid.code = concept.CodeableConcept({"coding":[{"system":"http://loinc.org","code":"82120-7","display":"Allelic phase"}]})
            observation_sid.subject = patient_reference
            observation_sid.valueCodeableConcept = concept.CodeableConcept({"coding":[{"system":"http://hl7.org/fhir/uv/genomics-reporting/CodeSystem/seq-phase-relationship","code":self.sequenceRels.at[index,'Relation'],"display":self.sequenceRels.at[index,'Relation']}]})
            self.report.contained.append(observation_sid)

    def add_report_result(self):
        reportResult = []
        for uid in self.region_ids:
            reportResult.append(reference.FHIRReference({"reference": "#rs-"+uid}))
        for pos,uid in self.map_variant_ids.items():
            reportResult.append(reference.FHIRReference({"reference": "#dv-"+uid}))
        for uid in self.seq_ids:
            reportResult.append(reference.FHIRReference({"reference": "#sid-"+uid}))
        self.report.result = reportResult
    
    def generate_final_json(self):
        response = self.report.as_json()
        od = OrderedDict() 
        od["resourceType"] = response['resourceType']
        od["id"] = response['id']
        od["meta"] = response['meta']
        od["contained"] = response['contained']
        od["status"] = response['status']
        od["code"] = response['code']
        od["subject"] = response['subject']
        od["issued"] = response['issued']
        od["result"] = response['result']

        odCodeCoding = OrderedDict()
        odCodeCoding["system"] = od["code"]["coding"][0]["system"]
        odCodeCoding["code"] = od["code"]["coding"][0]["code"]
        odCodeCoding["display"] = od["code"]["coding"][0]["display"]
        od["code"]["coding"][0] = odCodeCoding

        sidIndex = 0
        for index,fhirReport in enumerate(od['contained']):
            if (fhirReport['id'].startswith('sid-')):
                sidIndex = index
                break

        for index,(sequenceRel, fhirReport) in enumerate(zip(self.sequenceRels.index, od['contained'][sidIndex:])):
            dvRef1 = self.map_variant_ids.get(str(self.sequenceRels.at[index,'POS1']))
            dvRef2 = self.map_variant_ids.get(str(self.sequenceRels.at[index,'POS2']))
            if (fhirReport['id'].startswith('sid-')):
                derivedFromDV1 = {}
                derivedFromDV2 = {}
                derivedFromDV1['reference'] = "#dv-"+dvRef1
                derivedFromDV2['reference'] = "#dv-"+dvRef2
                derivedFrom = [derivedFromDV1,derivedFromDV2]
                fhirReport['derivedFrom']= derivedFrom

        for k,i in  enumerate(od['contained']):
            if (i['category'][0]['coding'][0]):
                odCategoryCoding = OrderedDict()
                odCategoryCoding["system"] = i['category'][0]['coding'][0]["system"] 
                odCategoryCoding["code"] = i['category'][0]['coding'][0]["code"] 
                od['contained'][k]['category'][0]['coding'][0]  = odCategoryCoding

            if (i['code']['coding'][0]):
                odCodeCoding = OrderedDict()
                odCodeCoding["system"] = i['code']['coding'][0]["system"] 
                odCodeCoding["code"] = i['code']['coding'][0]["code"]
                odCodeCoding["display"] = i['code']['coding'][0]["display"]
                od['contained'][k]['code']['coding'][0]  = odCodeCoding

            if 'valueCodeableConcept' in i.keys():
                odValueCodeableConceptCoding = OrderedDict()
                odValueCodeableConceptCoding["system"] = i['valueCodeableConcept']['coding'][0]["system"] 
                odValueCodeableConceptCoding["code"] = i['valueCodeableConcept']['coding'][0]["code"]
                odValueCodeableConceptCoding["display"] = i['valueCodeableConcept']['coding'][0]["display"]
                od['contained'][k]['valueCodeableConcept']['coding'][0] =  odValueCodeableConceptCoding

            if ((i['id'].startswith('dv-')) or (i['id'].startswith('rs-'))):
                for l,j in enumerate(i['component']):
                    odComponentCodeCoding = OrderedDict()
                    if j['code']['coding'][0]["system"]:
                        odComponentCodeCoding["system"] = j['code']['coding'][0]["system"] 
                    if j['code']['coding'][0]["code"]:
                        odComponentCodeCoding["code"] = j['code']['coding'][0]["code"]
                    if j['code']['coding'][0]["display"]:
                        odComponentCodeCoding["display"] = j['code']['coding'][0]["display"]
                    if od['contained'][k]['component'][l]['code']['coding'][0]:
                        od['contained'][k]['component'][l]['code']['coding'][0] = odComponentCodeCoding

                    odComponentvalueCodeableConcept = OrderedDict()
                    if 'valueCodeableConcept' in  j.keys():
                        odComponentvalueCodeableConcept["system"] = j['valueCodeableConcept']['coding'][0]["system"] 
                        if 'code' in j['valueCodeableConcept']['coding'][0].keys():
                            odComponentvalueCodeableConcept["code"] = j['valueCodeableConcept']['coding'][0]["code"]
                        if 'display' in j['valueCodeableConcept']['coding'][0].keys():
                            odComponentvalueCodeableConcept["display"] = j['valueCodeableConcept']['coding'][0]["display"]
                        od['contained'][k]['component'][l]['valueCodeableConcept']['coding'][0] = odComponentvalueCodeableConcept


            if (i['id'].startswith('rs-')):
                odRS = OrderedDict() 
                odRS["resourceType"] = i['resourceType']
                odRS["id"] = i['id']
                odRS["meta"] = i['meta']
                odRS["status"] = i['status']
                odRS["category"] = i['category']
                odRS["code"] = i['code']
                odRS["subject"] = i['subject']
                odRS["component"] = i['component']
                od['contained'][k] = odRS

            if (i['id'].startswith('dv-')):
                odDV = OrderedDict() 
                odDV["resourceType"] = i['resourceType']
                odDV["id"] = i['id']
                odDV["meta"] = i['meta']
                odDV["status"] = i['status']
                odDV["category"] = i['category']
                odDV["code"] = i['code']
                odDV["subject"] = i['subject']
                odDV["valueCodeableConcept"] = i['valueCodeableConcept']
                odDV["component"] = i['component']
                od['contained'][k] = odDV

            if (i['id'].startswith('sid-')):
                odSID = OrderedDict() 
                odSID["resourceType"] = i['resourceType']
                odSID["id"] = i['id']
                odSID["meta"] = i['meta']
                odSID["status"] = i['status']
                odSID["category"] = i['category']
                odSID["code"] = i['code']
                odSID["subject"] = i['subject']
                odSID["valueCodeableConcept"] = i['valueCodeableConcept']
                odSID["derivedFrom"] = i['derivedFrom']
                od['contained'][k] = odSID
        self.fhir_json = od
    
    def export_fhir_json(self, output_filename):
        with open(output_filename, 'w') as fp:
            json.dump(self.fhir_json, fp,indent=4)
        

    