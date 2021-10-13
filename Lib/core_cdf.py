# -*- coding: utf-8 -*-
"""
Created on Thu Sep  2 13:56:36 2021

@author: asligar
"""
# ------------------------------------------------------------------------------
# Standard Python Module Imports
import os
import sys
import json
import numpy as np
from Lib.Codebook import Codebook_Utils
from Lib.NearField_Setup import NearField_Utils
from Lib.FarField_Setup import FarField_Utils
from Lib.NearFieldsProcessing import Load_NF_Fields
from Lib.FarFieldsProcessing import Load_FF_Fields
from Lib.FarFieldsProcessing import envelope_pattern_all_jobs
from Lib.Reporter import Report_Module
from Lib.MultiSetup import Read_Multi_Setup
from Lib.CreateReports_in_AEDT import AEDT_CreateReports
import Lib.Utillities as utils

from pyaedt import Hfss
from pyaedt import Desktop
#from AEDTLib.HFSS import HFSS
#from AEDTLib.Desktop import Desktop
print(sys.path)


oDesktop = None

###########
# TODO
# multi thread averaging calculation
# support codebook with single beam id or no codebook (case of wifi6 with only 1 port)
# gui
# format output
###########

class CDF():
    def __init__(self,aedtapp,output_path = './output/'):
        print('Calculating CDF...')
        self.aedtapp = aedtapp
        self.version = '2021.2'
        self.multirun_state = False
        self.multi_setup_file_path = ''
        self.freq = 28e9
        
        self.project_name = ''
        self.design_name = ''
        self.setup_name = ""
        self.path_to_codebook = ''
        self.cs_name = 'Global'
        
        self.renormalize = False
        self.renormalize_dB = True
        self.renorm_value = 1
        
        current_date_and_time =utils.round_time()
        current_date_and_time_string = str(current_date_and_time).replace(':','').replace(' ','_')
        
        self.base_output_path = output_path + current_date_and_time_string + '/CDF/'
        self.output_path = self.base_output_path
        
    def get_desktop_settings(self):
        self.current_autosave_state = self.aedtapp.odesktop.GetAutoSaveEnabled()
        self.current_updatereports_state = self.aedtapp.odesktop.GetRegistryInt('Desktop/Settings/ProjectOptions/HFSS/UpdateReportsDynamicallyOnEdits') 
    def disable_desktop_settings(self):
        self.aedtapp.odesktop.EnableAutoSave(False)
        self.aedtapp.odesktop.SetRegistryInt('Desktop/Settings/ProjectOptions/HFSS/UpdateReportsDynamicallyOnEdits', 0)
        
    def restore_desktop_settings(self):
        self.aedtapp.odesktop.EnableAutoSave(self.current_autosave_state)
        self.aedtapp.odesktop.SetRegistryInt('Desktop/Settings/ProjectOptions/HFSS/UpdateReportsDynamicallyOnEdits', 
                                        self.current_updatereports_state)
        
    def run_cdf(self,projectname = '5G_28GHz_AntennaModule'):


        
        #get current state of autosave, will restore after script completes
        self.get_desktop_settings()
        self.disable_desktop_settings()
        
        run_multi_setup = True
        
        if self.multirun_state:
            all_jobs = Read_Multi_Setup(self.multi_setup_file_path,calc_type='CDF')
            #validation of setup is not complete
            if not all_jobs.validate_multi_setup(self.aedtapp):
                raise SystemExit("Multi-run setup file is not valid")
            jobs = all_jobs.jobs
        else:
            #select parameters
            job_dict = {}
            
            job_dict['Project_Name'] = self.project_name
            job_dict['Design_Name'] = self.design_name
            job_dict['Solution_Name'] = self.setup_name
            job_dict['Codebook_Name'] = self.path_to_codebook
            job_dict['Freq'] = self.freq
            job_dict['CS_Name'] = self.cs_name

            #only one job
            jobs = {0:job_dict}
    
    
        job_ids = list(jobs.keys())

            
        cdf_dict_all_jobs = {}
        for job in jobs.keys():
            print('Runnning JobID ' + str(job))
                    
            #output_path = self.base_output_path +jobs[job]['Project_Name'] + '\\'+ jobs[job_ids[0]]['Design_Name'] + '\\'
            output_path = self.base_output_path  + 'JobID_' + str(job) + '/'
            if not os.path.exists(output_path):
                os.makedirs(output_path)
                
            ant_param_dict  = {}
            update_fields = True
            
            #read parameters from job dictionary

            self.aedtapp = Hfss(jobs[job]['Project_Name'],specified_version=self.version)
            self.aedtapp.set_active_design(jobs[job]['Design_Name'])
            print('Active Design: ' + jobs[job]['Design_Name'])
            self.solution_type = self.aedtapp.solution_type
            freq = jobs[job]['Freq']
            path_to_codebook = jobs[job]['Codebook_Name']
            setup_name = jobs[job]['Solution_Name']

            #write out information related to the job
            job_summary_name =  'job_summary.json'
            job_sum_path_name = output_path + job_summary_name
            
            variation_dict = self.aedtapp.available_variations.nominal_w_values_dict
            output_dict = jobs[job]
            output_dict['Variation'] = variation_dict
            utils.write_dictionary_to_json(path=job_sum_path_name,dict_to_write=output_dict)

            wl = 3e8/freq
        
            #import codebook
            codebook = Codebook_Utils(self.aedtapp,path_to_codebook)
            codebook.codebook_import()
            beam_ids = codebook.beam_ids
            #create near field setup
            
            farfield_setup = FarField_Utils(self.aedtapp)
            ff_setup_name = farfield_setup.insert_infinite_sphere(cs_name = jobs[job]['CS_Name'])

            
            
            
            #export fields, save to results directory with some sub folders
            save_path = (self.aedtapp.project_path + '\\'+self.aedtapp.project_name +  '.aedtresults\\' + 
                         self.aedtapp.design_name  + '.results\\'+ str(freq) + '.ffd\\')
            

            
            #only export port names that exist in the codebook, helpful in cases where
            #multiple modules exist in the design but are not being used for evaluation
            port_names_to_export = codebook.port_names_in_codebook
            
            #extract fields for each port excited individually
            ffd_files_dict = farfield_setup.export_all_ffd(ff_setup_name,
                                           freq=freq,
                                           setup_name = setup_name,
                                           export_path=save_path,
                                           overwrite=update_fields)
            

            
            #set edit sources back to values that represent codebook, this allows fields to be seen in AEDT
            #codebook.edit_sources(current_edit_sources_status)
            codebook.add_or_edit_variable('beamID',beam_ids[0])
            
            #Load Fields from nfd files
            #this just reads the data from file into memory
            fields_data = Load_FF_Fields(ffd_files_dict)
            fields_data.solution_type = self.solution_type
            
            #renormalization is not applied to individiual runs in with multi-run state
            if not self.multirun_state:
                fields_data.renormalize = self.renormalize 
                fields_data.renormalize_dB = self.renormalize_dB
                fields_data.renorm_value = self.renorm_value
            else:
                print("CDF renormalization not applied when using multi-run state")
            
            fields_data.unique_beams = codebook.unique_beams
            
            #recombine fields based on steering vector (codebook.input_vector)
            results = fields_data.combine_fields(codebook.input_vector)
            
            cdf_dict_all_jobs[job] = results
            
            max_realized_gain = fields_data.get_max_for_each_beam(results,qty='RealizedGain')
            max_pin = fields_data.get_max_for_each_beam(results,qty='Pincident')
            #get_one_type(self,all_beam_ff,qty='RealizedGain')

            #plots for testimg
            # plot_one_beam= results[4]
            reports = Report_Module(self.aedtapp,output_path)
            show_plot=True
            if self.multirun_state:
                reports.close_all_reports()
                show_plot=False
            # reports.plot_far_field_rect(plot_one_beam,'rETotal')
            # reports.plot_far_field_rect(plot_one_beam,'RealizedGain')
            #reports.polar_plot(plot_one_trace,'RealizedGain')
            
            reports.max_vs_beam_line(max_realized_gain,title='Max Realized Gain',
                                     pd_type_label = 'Realized_Gain',
                                     save_name ="max_gain_vs_beam",
                                     save_plot = True,
                                     show_plot = show_plot)
            


            envelope_pattern = fields_data.envelope_pattern(results,qty='RealizedGain')
            
            envelope_pattern_for_writing = utils.dict_with_numpy_to_lists(envelope_pattern)
            utils.write_dictionary_to_json(path=output_path + 'CDF.json',
                                           dict_to_write=envelope_pattern_for_writing)
        
            reports.plot_far_field_rect(envelope_pattern,'RealizedGain',
                                        title="Envelope Pattern",
                                        save_name ="envelope_pattern",
                                        save_plot = True,
                                        dB=True)
                

            
            reports.plot_far_field_rect(envelope_pattern,'Beam_For_Max',
                                        title="Beam Index for Max Pattern",
                                        save_name ="beam_id_for_maxbeam",
                                        save_plot = True,
                                        dB=False,
                                        levels=len(codebook.unique_beams))
            
            reports.plot_xy(envelope_pattern['CDF_Value'],
                            envelope_pattern['CDF_Area'],
                            title='CDF DB', 
                            xlabel = 'RealizedGain',
                            ylabel= 'CDF',
                            save_name ="CDF_"+ codebook.name,
                            save_plot = True,
                            dB=True)
                    
            if self.renormalize: 
                reports.plot_xy(envelope_pattern['CDF_Value_Renorm'],
                                envelope_pattern['CDF_Area'],
                                title='CDF DB - Renormalized', 
                                xlabel = 'Renormalized (dB)',
                                ylabel= 'CDF',
                                save_name ="CDF_"+ codebook.name,
                                save_plot = True,
                                dB=True)
                
            if self.multirun_state:
                    reports.close_all_reports()

        if len(job_ids)>1:
            envelope_pattern_all = envelope_pattern_all_jobs(cdf_dict_all_jobs,
                                                             qty='RealizedGain')
            
            envelope_pattern_for_writing_all = utils.dict_with_numpy_to_lists(envelope_pattern_all)
            utils.write_dictionary_to_json(path=self.base_output_path + 'CDF_AllJobs.json',
                                           dict_to_write=envelope_pattern_for_writing_all)
            
            reports.plot_far_field_rect(envelope_pattern_all,
                                        'RealizedGain',
                                        title="Envelope Pattern Mullti_run",
                                        output_path = self.base_output_path,
                                        save_name = 'Envelope_Pattern_MultiRun_' + all_jobs.name,
                                        save_plot = True,
                                        dB=True)
            
            reports.plot_xy(envelope_pattern_all['CDF_Value'],
                                envelope_pattern_all['CDF_Area'],
                                title='CDF_MultiRun_' + all_jobs.name, 
                                xlabel = 'RealizedGain',
                                ylabel= 'CDF',
                                output_path = self.base_output_path,
                                save_name = 'CDF_MultiRun_' + all_jobs.name,
                                save_plot = True,
                                dB=True)
        self.restore_desktop_settings()
        print('Done')


        #we don't have to do this, but we can create the same reports in AEDT, 
        # that way the are linked to design variaions
        # if not self.multirun_state:
        #     aedt_reports = AEDT_CreateReports(self.aedtapp)
        #     aedt_reports.selected_setup =self.setup_name
        #     aedt_reports.selected_freq = self.freq
        #     aedt_reports.ff_setup = ff_setup_name

        #     aedt_reports.create_report_cdf('Realized Gain',beam_ids)
        #     aedt_reports.generate_envelope_pattern_3D('Realized Gain',beam_ids)