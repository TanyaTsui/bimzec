from mesa import Agent, Model
from mesa.time import RandomActivation, BaseScheduler
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon, Point, MultiPoint, box
import math
import matplotlib.pyplot as plt
import numpy as np
from numpy import exp
from numpy.random import rand, seed
import folium
import random 
from haversine import haversine
import plotly.express as px
from plotly.subplots import make_subplots
import base64
from io import BytesIO
from IPython.display import IFrame
from IPython.display import display, Javascript
from IPython.core.display import HTML
pd.options.mode.chained_assignment = None  # default='warn'


class ConstructionSite(Agent): 
    def __init__(self, unique_id, model, buildingType, coords, inA10, waterbound):
        super().__init__(unique_id, model)
        self.buildingType = buildingType # A, B, C...etc. 
        self.coords = coords 
        self.inA10 = inA10 # True or False 
        self.waterbound = waterbound # True of False
        self.materials_request = {}
        self.materials_received = {}
        
        if self.model.hub_network == 'decentralized': 
            self.nearestHub_id = None
            self.nearestHub_dist = None
        self.nearestMacroHub_id = None
        self.nearestMacroHub_dist = None
        
        self.filter_material_composition_df()
        self.make_dicts_siteInfo()
        self.calc_materials_required()
            
    def filter_material_composition_df(self): 
        '''make df of materials required, based on building type and biobased type'''
        b = self.model.build_info.copy()
        b = b[(b.buildingType == self.buildingType) & (b.biobased_type == self.model.biobased_type)] 
        self.material_composition_df = b
    
    def make_dicts_siteInfo(self): 
        '''make dictionaries required to record information on construction site'''
        self.materials_required = {
            strucType: {
                mat: 0 for mat in [mat for mat in self.model.materials_list if mat != 'modules']
            } for strucType in ['foundation', 'structural', 'non-structural']
        }
        self.materials_received = {
            strucType: {
                mat: 0 for mat in self.model.materials_list
            } for strucType in ['foundation', 'structural', 'non-structural']
        }

    def calc_materials_required(self): 
        '''calculate materials required based on modularity_type
        self.materials_required = {'foundation': {'timber': 123, ...}, ... }'''        
        b = self.material_composition_df
        if self.model.modularity_type == 'none':
            strucTypes = ['foundation', 'structural', 'non-structural']
        else: 
            strucTypes = ['foundation', 'structural']
        
        for strucType, mat_amounts in self.materials_required.items():
            for mat, amounts in mat_amounts.items(): 
                b1 = b[(b.material == mat) & (b.structural_type == strucType)].iloc[0]
                self.materials_required[strucType][mat] += b1.tons
        if self.model.modularity_type != 'none': 
            self.materials_required['non-structural']['modules'] = b[(b.material == 'modules')].iloc[0].tons                              
                
    def step(self): 
        self.check_materials_toRequest()
        self.request_materials()
    
    def check_materials_toRequest(self): 
        '''check which materials still need to be requested based on 
        materials already received in previous rounds'''
        materials_toRequest = []
        for strucType, mat_required_dict in self.materials_required.items(): 
            for mat, amount in mat_required_dict.items():  
                mat_required = amount
                mat_received = self.materials_received[strucType][mat]
                if mat_received < mat_required: 
                    materials_toRequest.append(mat)
        self.materials_toRequest_list = list(set(materials_toRequest))
        
    def request_materials(self):
        '''make materials_request that will be received by supplier / macro / micro hub'''
        material_request = {key: dict.fromkeys(self.model.materials_list, 0) for key in 
                            list(self.materials_required.keys())} 
        for strucType in self.materials_required.keys(): 
            for mat in self.materials_toRequest_list:
                if mat == 'modules' and strucType != 'non-structural': 
                    continue
                mat_required = self.materials_required[strucType][mat]
                mat_received = self.materials_received[strucType][mat] 
                mat_stillNeeded = mat_required - mat_received
                mat_request = mat_required * random.uniform(0.1, 0.2)
                mat_request = mat_request if mat_request < mat_stillNeeded else mat_stillNeeded
                material_request[strucType][mat] += mat_request
        self.materials_request = material_request
        
class Hub(Agent):
    def __init__(self, unique_id, model, hubType, coords, inA10, waterbound):
        super().__init__(unique_id, model)
        self.hubType = hubType # macro or micro 
        self.coords = coords
        self.inA10 = inA10 # True of False
        self.waterbound = waterbound # True of False
        self.nearestMacroHub_id = None
        self.nearestMacroHub_dist = None
        
        self.materials_toSend = {}
        self.nTrips = {}
        self.materials_request = {}
        self.materials_received = dict.fromkeys(self.model.materials_list, 0)
        
        self.suppliers = {}
        self.clients = {}
        self.trucks_toSite = []
        self.vehicles_toSupplier = []
        self.demolition_site_ids = []
        self.supplier_ids = []
        self.client_ids = []
                                
    def step(self):
        self.find_clients()
        if self.clients: # if hub has clients: 
            self.calc_materials_toSend() # to each site / microHub
            self.make_materials_request() # for suppliers / demSites / macroHubs 
            self.triage_materials_request()
            
            if self.model.circularity_type != 'none' and self.hubType == 'macro': 
                self.convertNames_matRequest_forDemolitionSites()
                self.collect_materials_fromDemolitionSites()
            
            if self.hubType == 'macro': 
                self.find_suppliers()
                self.collect_materials_fromSupplier() # collect materials from suppliers 
            self.send_materials_toClient() # send materials to site / microhub
        
    def find_clients(self): 
        '''self.clients = {id: {'agent': agentObject, 'distance': 14312}, ... etc}'''
        
        self.clients = {}
        
        if self.model.hub_network == 'decentralized': 
            if self.hubType == 'macro': 
                microHubs = [hub for hub in self.model.hubs if hub.hubType == 'micro']
                microHubs = [hub for hub in microHubs if hub.nearestMacroHub_id == self.unique_id]
                sites = [s for s in self.model.construction_sites if s.nearestHub_id == self.unique_id]
                clients = microHubs + sites
                for client in clients: 
                    self.clients[client.unique_id] = {'agent': client, 'distance': client.nearestMacroHub_dist}
            
            elif self.hubType == 'micro': 
                sites = self.model.construction_sites
                clients = [site for site in sites if site.nearestHub_id == self.unique_id]
                for client in clients: 
                    self.clients[client.unique_id] = {'agent': client, 'distance': client.nearestHub_dist}
        
        elif self.model.hub_network == 'centralized': 
            sites = self.model.construction_sites
            clients = [site for site in sites if site.nearestMacroHub_id == self.unique_id]
            for client in clients: 
                self.clients[client.unique_id] = {'agent': client, 'distance': client.nearestMacroHub_dist}    
                        
    def calc_materials_toSend(self): 
        '''check which clients still need materials and make materials_toSend dictionary
        self.clients = microhubs or construction sites 
        self.materials_toSend = {site_id: {'foundation': {'timber': 123, ... }, ... }'''
        self.materials_toSend = {}
        for client_id in self.clients.keys():
            client = self.clients[client_id]['agent']
            # if the client is requesting any material: 
            if sum(sum(request.values()) for request in client.materials_request.values()) > 0: 
                self.materials_toSend[client_id] = client.materials_request
                        
    def make_materials_request(self):
        '''self.materials_request = {'foundation': {'timber': 123, ... }, ... }, ... }'''
        material_request = {
            strucType: {
                mat: 0 for mat in self.model.materials_list
            } for strucType in ['foundation', 'structural', 'non-structural']
        }
                        
        for site_id, mat_request in self.materials_toSend.items():
            for strucType, mat_amounts in mat_request.items(): 
                for mat, amount in mat_amounts.items(): 
                    material_request[strucType][mat] += amount 
        self.materials_request = material_request
                
    def triage_materials_request(self):
        '''separate self.materials_request into two parts, 
        one for demolition sites and one for suppliers'''
        
        # pick strucType for demSite and suppliers 
        strucTypes_forCircParam_dict = {
            'none': [], 
            'semi': ['non-structural'], 
            'full': ['non-structural', 'structural'], 
            'extreme': ['non-structural', 'structural', 'foundation']
        }
        strucTypes_all = ['non-structural', 'structural', 'foundation']
        strucTypes_demSites = strucTypes_forCircParam_dict[self.model.circularity_type] 
        strucTypes_suppliers = [i for i in strucTypes_all if i not in strucTypes_demSites]
        if self.model.modularity_type == 'full': 
            strucTypes_suppliers = strucTypes_suppliers + ['non-structural']
        
        # make separate materials_requests for demSites and suppliers
        def make_matRequest_triaged(strucTypes): 
            matRequest_triaged = {}
            for strucType in strucTypes:
                mat_amounts = self.materials_request[strucType]
                for mat, amount in mat_amounts.items(): 
                    matRequest_triaged[mat] = matRequest_triaged.get(mat, 0) + amount
            matRequest_triaged = {k: v for k, v in matRequest_triaged.items() if v!= 0}
            return matRequest_triaged
        
        self.materials_request_forDemSites = make_matRequest_triaged(strucTypes_demSites)
        self.materials_request_forSuppliers = make_matRequest_triaged(strucTypes_suppliers)
        
    def convertNames_matRequest_forDemolitionSites(self): 
        '''convert mat names in materials_request_forDemSites to match mat names in demolition_sites_df'''
        
        materials_request_old = self.materials_request_forDemSites
        df = self.model.materialNames_conversion
        materials_request_new = {key: 0 for key in df.name_from_demSiteData.unique()}
        
        for matName_con, amount in materials_request_old.items(): 
            matName = df[df.name_from_conSiteData == matName_con].name_from_demSiteData.iloc[0]
            materials_request_new[matName] += amount
        
        self.materials_request_forDemSites = materials_request_new
    
    def _get_vehicle_forDemSite(self, demSite): 
        '''make vehicle capacities for demolition sites by converting mat names in vehicles_info
        into mat names in demolition_sites_df'''
        
        # get info for vehicle based on model params  
        if self.model.network_type == 'water' and self.waterbound and demSite.waterbound: 
            transportation_network = 'water'
            vehicle_type = 'water'
        else: # road network is used 
            transportation_network = 'road'
            if self.model.truck_type == 'semi': 
                vehicle_type = 'electric' if self.inA10 or demSite.inA10 else 'diesel'
            else: 
                vehicle_type = self.model.truck_type 
        
        # select vehicle 
        vehicles_df = self.model.vehicles_info_demSites
        vehicle = vehicles_df[(vehicles_df.region == 'urban') & 
                              (vehicles_df.transportation_network == transportation_network) & 
                              (vehicles_df.vehicle_type == vehicle_type)].iloc[0]
        return vehicle # need this for self.collect_materials_fromDemolitionSites() 
                               
    def collect_materials_fromDemolitionSites(self): 
        '''collect materials from randomly selected demolition sites'''
        materials_collected = {key: 0 for key in self.materials_request_forDemSites.keys()}
        for mat, request_amount in self.materials_request_forDemSites.items(): 
            if mat not in self.model.demolition_sites_df.columns: 
                continue
            while True: 
                # randomly select demolition site and see what's available
                demSites = self.model.demolition_sites_df
                demSites = demSites[demSites.nearestMacroHub_id == self.unique_id]
                demSite = demSites.sample(1).iloc[0]
                available_tons = demSite[mat] 

                # collect what's still needed 
                still_needed = request_amount - materials_collected[mat]
                collect_tons = still_needed if available_tons >= still_needed else available_tons

                # record emissions and demolition site ids
                vehicle = self._get_vehicle_forDemSite(demSite)
                capacity = vehicle[f'capacity_{mat}'] * 0.8
                distance = demSite.nearestMacroHub_dist
                nTrips = math.ceil(collect_tons / capacity)
                emissions_perTonKm = vehicle.emissions_perTonKm
                emissions_perKm = emissions_perTonKm * (vehicle.vehicle_weight + collect_tons)
                emissions = emissions_perKm * distance * nTrips * 2
                self.model.emissions_s2h += emissions
                self.demolition_site_ids.append(demSite.unique_id)

                if vehicle.transportation_network == 'road': 
                    # record roads used
                    roadMatrix = self.model.road_matrix_d2h
                    road_ids = roadMatrix[(roadMatrix[:, 1] == self.unique_id) & (roadMatrix[:, 0] == demSite.unique_id)][0][2]
                    mask = self.model.roads_used['osmid'].isin(road_ids)
                    self.model.roads_used.loc[mask, 'nTrips'] += nTrips

                    # record road damage
                    nAxels = vehicle.nAxels
                    weight = capacity / nAxels 
                    damage = (weight ** 4) * nTrips 
                    self.model.roads_used.loc[mask, 'damage'] += damage
                               
                # stop if enough materials have been collected 
                materials_collected[mat] += collect_tons
                if materials_collected[mat] >= request_amount: 
                    break

    def find_suppliers(self): 
        '''this function is only run by macro hubs - see Hub.step()
        select supplier agent and distance based on location type (national / international)
        self.materials_request_forSuppliers = {'mat': 123, 'mat': 456 ... }
        self.suppliers = {'timber': {'agent': agentObject, 'distance': 14312}, ... etc}'''
               
        self.suppliers = {}
        mat_info = self.model.materials_logistics_info
        
        for mat in self.materials_request_forSuppliers.keys():
            self.suppliers[mat] = {}
            location_type = mat_info[mat_info.material == mat].iloc[0].supplier_type
            supplier = [s for s in self.model.suppliers if s.location_type == location_type][0]
            
            self.suppliers[mat]['agent'] = supplier 
            self.suppliers[mat]['distance'] = supplier.distance_fromAms
                        
    def collect_materials_fromSupplier(self): 
        '''this function is only run by macro hubs - see Hub.step()
        collect materials from factory supplier (national / international)'''
        
        for mat, amount in self.materials_request_forSuppliers.items(): 
            
            # get info for calculating emissions and road usage 
            supplier = self.suppliers[mat]['agent']
            distance = self.suppliers[mat]['distance']
            vehicles_df = self.model.vehicles_info
            vehicle = vehicles_df[(vehicles_df.region == 'international') & 
                                  (vehicles_df.transportation_network == self.model.network_type)].iloc[0]
            capacity = vehicle[f'capacity_{mat}']
            emissions_perTonKm = vehicle['emissions_perTonKm']
            
            # modify info based on water conditions 
            # if macro hub is not water bound, materials will be delivered from supplier by truck
            if self.model.network_type == 'water' and not self.waterbound: 
                vehicle = vehicles_df[(vehicles_df.region == 'international') & 
                                      (vehicles_df.transportation_network == 'road')].iloc[0]
                capacity = vehicle[f'capacity_{mat}']
                emissions_perTonKm = vehicle['emissions_perTonKm']
            nTrips = math.ceil(amount / capacity)

            # record road usage road network is used  
            if self.model.network_type == 'road' or (self.model.network_type == 'water' and not self.waterbound): 
                roadMatrix = self.model.road_matrix_s2h
                road_ids = roadMatrix[(roadMatrix[:, 0] == supplier.unique_id) & (roadMatrix[:, 1] == self.unique_id)][0][2]
                mask = self.model.roads_used['osmid'].isin(road_ids)
                self.model.roads_used.loc[mask, 'nTrips'] += nTrips
                
                # record road damage
                nAxels = vehicle['nAxels']
                weight = capacity / nAxels 
                damage = (weight ** 4) * nTrips 
                self.model.roads_used.loc[mask, 'damage'] += damage

            # record emissions, materials received, and suppliers used 
            emissions_perKm = emissions_perTonKm * (vehicle.vehicle_weight + amount)
            self.model.emissions_s2h += emissions_perKm * distance * nTrips * 2
            self.materials_received[mat] += amount
            self.supplier_ids.append(supplier.unique_id)
        
    def send_materials_toClient(self): 
        '''send materials to client (either construction sites or micro hubs) 
        self.materials_toSend = {site_id: {'foundation': {'timber': 123, ... }, ... }, ... }'''
        
        # for each client (either construction site or micro hub): 
        for client_id, mat_toSend_dict in self.materials_toSend.items(): 
            
            # get client info
            client = self.clients[client_id]['agent']
            distance = self.clients[client_id]['distance']
            
            # get vehicle based on params 
            region = 'urban'
            if self.model.network_type == 'water' and self.waterbound and client.waterbound: 
                transportation_network = 'water'
                vehicle_type = 'water'
            else: # road network is used: 
                transportation_network = 'road'
                if self.model.truck_type == 'semi': 
                    vehicle_type = 'electric' if client.inA10 or self.inA10 else 'diesel'
                else: 
                    vehicle_type = self.model.truck_type 
                    
            # get vehicle info
            vehicles_df = self.model.vehicles_info
            vehicle = vehicles_df[(vehicles_df.transportation_network == transportation_network) & 
                                  (vehicles_df.vehicle_type == vehicle_type)].iloc[0]
            
            # determine roads used
            roadMatrix = self.model.road_matrix_h2hc
            road_ids = roadMatrix[(roadMatrix[:, 0] == self.unique_id) & (roadMatrix[:, 1] == client.unique_id)][0][2]
            road_ids_str = [','.join(map(str, r)) if isinstance(r, list) else str(r) for r in road_ids]
            mask = self.model.roads_used['osmid'].isin(road_ids_str)

            for strucType, mat_amounts in mat_toSend_dict.items(): 
                for mat, amount in mat_amounts.items(): 
                    
                    # record emissions 
                    capacity = vehicle[f'capacity_{mat}']
                    nTrips = math.ceil(amount / capacity)
                    emissions_perKm = vehicle.emissions_perTonKm * (vehicle.vehicle_weight + amount)
                    emissions = emissions_perKm * distance * nTrips * 2
                    self.model.emissions_h2c += emissions
                    
                    if transportation_network == 'road': 
                        # record roads used, road damage
                        nAxels = vehicle.nAxels
                        weight = capacity / nAxels 
                        damage = (weight ** 4) * nTrips 
                        if self.model.network_type == 'water': 
                            if self.waterbound and client.waterbound: 
                                damage = 0
                        self.model.roads_used.loc[mask, 'damage'] += damage
                        self.model.roads_used.loc[mask, 'nTrips'] += nTrips
                    
                    # record  materials received, client ids 
                    if type(client) is ConstructionSite: 
                        client.materials_received[strucType].setdefault(mat, 0)
                        client.materials_received[strucType][mat] += amount
                    else: # if client == micro hub: 
                        client.materials_received.setdefault(mat, 0)
                        client.materials_received[mat] += amount
                    self.client_ids.append(client_id)
                                        
class Supplier(Agent): 
    def __init__(self, unique_id, model, material, distFromAms, coords): 
        super().__init__(unique_id, model)
        self.material = material
        self.location_type = material
        self.distance_fromAms = distFromAms 
        self.coords = coords
        self.clients = {}
        self.waterbound = 0
        self.location_type = material
        
    def step(self): 
        self.find_clients() 
        if self.clients and self.model.hub_network == 'none': 
            self.calc_materials_toSend() 
            self.send_materials_toClient() 
    
    def find_clients(self): 
        '''self.clients = list of client agents [agent, agent, agent ...]'''
        self.clients = {}
        if self.model.hub_network == 'centralized': 
            clients = self.model.hubs
        elif self.model.hub_network == 'decentralized': 
            clients = [hub for hub in self.model.hubs if hub.hubType == 'macro']
        elif self.model.hub_network == 'none': 
            clients = [site for site in self.model.construction_sites]
        self.clients = clients 
                        
    def calc_materials_toSend(self): 
        '''self.materials_toSend = {id: {foundation: {'timber': 123, 'concrete': 456}}, ... }'''
        self.materials_toSend = {}
        for client in self.clients: 
            mat_req = client.materials_request # {'foundation': {'mat': 123}, ... }
            self.materials_toSend[client.unique_id] = {}
            for strucType, mat_amounts in mat_req.items(): 
                self.materials_toSend[client.unique_id][strucType] = {}
                for mat, amount in mat_amounts.items(): 
                    try: 
                        self.materials_toSend[client.unique_id][strucType][mat] += amount 
                    except: 
                        self.materials_toSend[client.unique_id][strucType][mat] = amount

    def send_materials_toClient(self): 
        vehicles_df = self.model.vehicles_info
        vehicle = vehicles_df[(vehicles_df.region == 'international') & 
                              (vehicles_df.transportation_network == self.model.network_type)].iloc[0]
        emissions_perTonKm = vehicle.emissions_perTonKm

        for client_id, mat_toSend_dict in self.materials_toSend.items(): 
            client = [c for c in self.clients if c.unique_id == client_id][0]
            distance = self.distance_fromAms
            for strucType, mat_amounts in mat_toSend_dict.items(): 
                for mat, amount in mat_amounts.items(): 
                    # record emissions
                    # assuming that trucks from supplier to constructure site is 30% loaded
                    capacity = vehicle[f'capacity_{mat}'] * 0.3 
                    nTrips = math.ceil(amount / capacity)
                    emissions_perKm = emissions_perTonKm * (vehicle.vehicle_weight + amount)
                    emissions = emissions_perKm * distance * nTrips * 2
                    self.model.emissions_s2h += emissions
                    client.materials_received[strucType][mat] += amount

                    # record roads used 
                    roadMatrix = self.model.road_matrix_s2c
                    road_ids = roadMatrix[(roadMatrix[:, 0] == self.unique_id) & 
                                          (roadMatrix[:, 1] == client_id)][0][2]
                    roads_gdf = self.model.roads_used
                    mask = roads_gdf['osmid'].isin(road_ids)
                    roads_gdf.loc[mask, 'nTrips'] += nTrips
                    self.model.roads_used = roads_gdf
                    
                    # record road damage
                    nAxels = vehicle.nAxels
                    weight = capacity / nAxels 
                    damage = (weight ** 4) * nTrips 
                    self.model.roads_used.loc[mask, 'damage'] += damage


from mesa import Model
from mesa.datacollection import DataCollector
class Model(Model):
    def __init__(self, parameters_dict): 
        '''create construction sites, hubs, and vehicles'''
        super().__init__()
        self.schedule = BaseScheduler(self)
        self.emissions_s2h = 0
        self.emissions_h2c = 0 
        self.roads_used = gpd.read_file('data/data_cleaned/ams_roads_edges.shp')
        self.roads_used['damage'] = 0 
        self.roads_used['damage'] = self.roads_used['damage'].astype(float)
        self.datacollector = DataCollector(
            model_reporters = {
                'emissions_s2h': lambda m: m.emissions_s2h, 
                'emissions_h2c': lambda m: m.emissions_h2c, 
                'emissions_total': lambda m: m.emissions_s2h + m.emissions_h2c, 
            }
        )
        
        self.load_data()
        self.add_parameters(parameters_dict) 
        
        self.id_count = 0
        self.create_constructionSites()
        self.create_suppliers() 
        if self.hub_network != 'none': 
            self.create_hubs()
        
        if self.hub_network != 'none': 
            self.create_od_matrix_h2c()
            self.create_od_matrix_h2h()
            self.assign_hubs_to_sites()
            self.assign_hubs_to_hubs()
        
        if self.circularity_type != 'none': 
            self.create_od_matrix_d2h()
            self.assign_hubs_to_demolition_sites()
                    
    def load_data(self): 
        self.construction_sites_df = gpd.read_file('data/data_cleaned/construction_sites.shp')
        self.hubs_df = gpd.read_file('data/data_cleaned/hubs.shp')
        self.suppliers_df = gpd.read_file('data/data_cleaned/suppliers.shp')
        self.demolition_sites_df = gpd.read_file('data/data_cleaned/demolition_sites.shp')
        self.vehicles_info = pd.read_csv('data/data_cleaned/vehicles_info.csv')
        self.vehicles_info_demSites = pd.read_csv('data/data_cleaned/vehicles_info_demSites.csv')
        self.build_info = pd.read_csv('data/data_cleaned/buildingType_info.csv')
        self.materials_logistics_info = pd.read_csv('data/data_cleaned/materials_logistics_info.csv')
        self.materialNames_conversion = pd.read_csv('data/data_cleaned/materialNames_conversion.csv')
        self.materials_list = list(self.build_info.material.unique())
        self.road_matrix_h2hc = np.load('data/data_cleaned/roadOsmIds_matrix_h2hc.npy', allow_pickle=True)
        self.road_matrix_d2h = np.load('data/data_cleaned/roadOsmIds_matrix_d2h.npy', allow_pickle=True)
        self.road_matrix_s2h = np.load('data/data_cleaned/roadOsmIds_matrix_s2h.npy', allow_pickle=True)
        self.road_matrix_s2c = np.load('data/data_cleaned/roadOsmIds_matrix_s2c.npy', allow_pickle=True)

        self.construction_sites = []
        self.hubs = []
        self.suppliers = []
        self.trucks_urban = []
        self.vehicles_international = []
        
    def add_parameters(self, parameters_dict): 
        self.network_type = parameters_dict['network_type']
        self.truck_type = parameters_dict['truck_type']
        self.biobased_type = parameters_dict['biobased_type']
        self.modularity_type = parameters_dict['modularity_type']
        self.hub_network = parameters_dict['hub_network']
        self.circularity_type = parameters_dict['circularity_type']
        self.parameters_dict = parameters_dict
    
    def create_constructionSites(self): 
        for i, row in self.construction_sites_df.iterrows(): 
            coords = (row.geometry.y, row.geometry.x)
            site = ConstructionSite(self.id_count, self, row.buildType, 
                                    coords, row.inA10, row.waterbound)
            self.schedule.add(site)
            self.construction_sites.append(site)
            self.id_count += 1 
            
    def create_suppliers(self): 
        for i, row in self.suppliers_df.iterrows(): 
            coords = (row.geometry.y, row.geometry.x)
            supplier = Supplier(self.id_count, self, row.material, 
                                row.distAms, coords)
            self.schedule.add(supplier)
            self.suppliers.append(supplier)
            self.id_count += 1
    
    def create_hubs(self): 
        if self.hub_network == 'centralized': 
            hub_type = ['macro']
        elif self.hub_network == 'decentralized': 
            hub_type = ['micro', 'macro']
        elif self.hub_network == 'none': 
            hub_type = []
        for i, row in self.hubs_df.iterrows(): 
            if row.hub_type in hub_type: 
                coords = (row.geometry.y, row.geometry.x)
                hub = Hub(self.id_count, self, row.hub_type, coords, row.inA10, row.waterbound)
                self.schedule.add(hub)
                self.hubs.append(hub)
                self.id_count += 1 
                
    def get_capacity(self, network_type, truck_type): 
        '''capacity_dict = {'timber': 20, 'concrete': 25, ... }
        emissions_perTonKm = 0.0009 (emissions per km for a particular vehicle)'''
        v = self.vehicles_info.copy()
        v = v[(v.transportation_network == network_type) & (v.vehicle_type == truck_type)]
        capacity_dict = {}
        for mat in self.materials_list + ['modules']: 
            capacity = v[f'capacity_{mat}'].iloc[0]
            capacity_dict[mat] = capacity
        emissions_perTonKm = v.emissions_perTonKm.iloc[0]
        nAxels = v.nAxels.iloc[0]
        return capacity_dict, emissions_perTonKm, nAxels
    
    # this needs to be changed to real distance od matrix 
    # add this in data prep 
    def create_od_matrix_h2c(self): 
        '''This od matrix was made in dataPrep.ipynb. The ids correspond to the 
        agent unique ids in the agent based model. If the input data for construction sites
        and hubs changes, this od matrix needs to change accordingly in dataPrep.ipynb.'''
        self.od_matrix_h2c = np.load('data/data_cleaned/od_matrix_h2c.npy')
    
    # this needs to be changed to real distance od matrix 
    # add this in data prep
    def create_od_matrix_h2h(self): 
        '''This od matrix was made in dataPrep.ipynb. The ids correspond to the 
        agent unique ids in the agent based model. If the input data for construction sites
        and hubs changes, this od matrix needs to change accordingly in dataPrep.ipynb.'''
        self.od_matrix_h2h = np.load('data/data_cleaned/od_matrix_h2h.npy')
        
    def create_od_matrix_d2h(self): 
        '''This od matrix was made in dataPrep.ipynb. The ids correspond to the 
        agent unique ids in the agent based model. If the input data for construction sites
        and hubs changes, this od matrix needs to change accordingly in dataPrep.ipynb.'''
        self.od_matrix_d2h = np.load('data/data_cleaned/od_matrix_d2h.npy')
                
    def assign_hubs_to_sites(self):
        od = self.od_matrix_h2c
        nMacroHubs = len([hub for hub in self.hubs if hub.hubType == 'macro'])
        for site in self.construction_sites: 
            site_od = od[od[:, 1] == site.unique_id]
            if self.hub_network == 'decentralized': 
                site.nearestHub_id = int(site_od[np.argmin(site_od[:, 2]), 0])
                site.nearestHub_dist = site_od[np.argmin(site_od[:, 2]), 2]
            site_od_macro = site_od[:nMacroHubs]
            site.nearestMacroHub_id = int(site_od_macro[np.argmin(site_od_macro[:, 2]), 0])
            site.nearestMacroHub_dist = site_od_macro[np.argmin(site_od_macro[:, 2]), 2]
                        
    def assign_hubs_to_hubs(self): 
        od = self.od_matrix_h2h
        for hub in self.hubs: 
            hub_od = od[od[:, 1] == hub.unique_id]
            hub.nearestMacroHub_id = int(hub_od[np.argmin(hub_od[:, 2])][0])
            hub.nearestMacroHub_dist = hub_od[np.argmin(hub_od[:, 2])][2]
            
    def assign_hubs_to_demolition_sites(self): 
        od = self.od_matrix_d2h
        def func(row): 
            unique_id = row.unique_id
            site_od = od[od[:, 0] == unique_id]
            # nearest hub out of all hubs
            row['nearestHub_id'] = int(site_od[np.argmin(site_od[:, 2]), 1])
            row['nearestHub_dist'] = site_od[np.argmin(site_od[:, 2]), 2]
            # nearest macroHub
            macroHubIds = [h.unique_id for h in self.hubs if h.hubType == 'macro']
            site_od_macro = site_od[np.isin(site_od[:, 1], macroHubIds)]
            row['nearestMacroHub_id'] = int(site_od_macro[np.argmin(site_od_macro[:, 2]), 1])
            row['nearestMacroHub_dist'] = site_od_macro[np.argmin(site_od_macro[:, 2]), 2]
            return row
        self.demolition_sites_df = self.demolition_sites_df.apply(lambda row: func(row), axis=1)
            
    def step(self):
        self.schedule.step()
        self.calc_emissions()
        self.datacollector.collect(self)
    
    def calc_emissions(self): 
        self.emissions = round(self.emissions_h2c + self.emissions_s2h)
    
    def visualize(self): 
        emissions_text = self.display_total_emissions()
        fig_emissions = self.display_emissions_chart()
        fig_materials = self.display_materials_chart()
        map_html = self.display_folium_html()

        return emissions_text, fig_emissions, fig_materials, map_html
        
    def display_total_emissions(self): 
        total_emissions = round(self.emissions_h2c + self.emissions_s2h)
        emissions_text = (
            f'''
            emissions (hubs to construction sites): {round(self.emissions_h2c)} tCO2eq
            emissions (suppliers to hubs): {round(self.emissions_s2h)} tCO2eq
            emissions (total): {total_emissions} tCO2eq
            '''
        )
        return emissions_text
        
    def display_emissions_chart(self): 
        data = self.datacollector.get_model_vars_dataframe()
        data = data.reset_index(names='step')
        fig = px.line(data, x="step", 
                      y=['emissions_s2h', 'emissions_h2c', 'emissions_total'], 
                      title='emissions')
        fig.update_layout(height=500)  # or any desired height in pixels
        return fig
    
    def display_materials_chart(self): 
        df_mat = self._make_df_materials(self.construction_sites)
        df_circ = self._make_df_circular(self.construction_sites, self.circularity_type)
        fig_1 = px.pie(df_mat, values='tons', names='material', title='materials used')
        fig_2 = px.pie(df_circ, values='tons', names='circular', title='materials used')

        fig = make_subplots(rows=1, cols=2, 
                            subplot_titles=('by material type', 'by circularity type'),
                            specs=[[{'type':'domain'}, {'type':'domain'}]])
        fig.add_trace(fig_1.data[0], 1, 1)
        fig.add_trace(fig_2.data[0], 1, 2)
        fig.update_layout(title_text="Total material usage")
        for annotation in fig['layout']['annotations']: 
            annotation['font'] = dict(size=12)  # Set to desired font size
        
        return fig 
    
    def _make_df_materials(self, consite_agents_list): 
        dfs = []
        for site in consite_agents_list: 
            df = site.material_composition_df
            df = df.groupby(by='material').sum(numeric_only=True).reset_index()
            dfs.append(df)
        return pd.concat(dfs).groupby('material').sum(numeric_only=True).reset_index() 
    
    def _make_df_circular(self, consite_agents_list, circularity_type): 
        circularity_dict = {
            'none': [], 
            'semi': ['non-structural'], 
            'full': ['non-structural', 'structural'], 
            'extreme': ['non-structural', 'structural', 'foundation']
        }

        dfs = []
        for site in consite_agents_list: 
            df = site.material_composition_df
            df['circular'] = df.structural_type.map(lambda x: 'circular' if x in circularity_dict[circularity_type] else 'not circular')
            df = df.groupby('circular').sum(numeric_only=True).reset_index()
            dfs.append(df)

        return pd.concat(dfs).groupby('circular').sum(numeric_only=True).reset_index()
    
    def display_folium_html(self): 
        
        m = folium.Map([52.377231, 4.899288], zoom_start=11, tiles='cartodbdark_matter')
        self.plotLines_roadsUsed(m)
        if self.hub_network != 'none':  
            if self.circularity_type != 'none': 
                self.plotPoints_demSites(m, 'grey', 1)
        if self.network_type != 'road': 
            self.plotLines_s2h(m)
        self.plotPoints(m, self.suppliers, 'grey', 1)
        self.plotPoints(m, self.construction_sites, 'white', 1)
        self.plotPoints(m, [h for h in self.hubs if h.hubType == 'macro' and h.clients], 'red', 8)
        self.plotPoints(m, [h for h in self.hubs if h.hubType == 'micro' and h.clients], 'red', 4)
        html_string = m._repr_html_()
        return html_string
    
    def plotPoints(self, m, agent_list, color, radius): 
        for agent in agent_list: 
            # selected_color = 'blue' if agent.waterbound else color
            selected_color = color
            folium.CircleMarker(
                location=agent.coords, radius=radius, color=selected_color, fill_color=selected_color, 
                popup=folium.Popup(f'id: {agent.unique_id}', max_width=300, height=150), 
            ).add_to(m)

    def plotLines_roadsUsed(self, m): 
        indicator = 'damage'
        df = self.roads_used
        df = df[df.nTrips > 0]
        max_trips = df[indicator].max()
        quantiles = df[indicator].quantile([0, 0.2, 0.4, 0.6, 0.8, 1])
        def get_color(value):
            lowVal = 80
            inc = (255 - lowVal) / 5
            if value <= quantiles[0.2]:
                return f'rgb({lowVal}, 0, 0)'  # Dark Red
            elif value <= quantiles[0.4]:
                return f'rgb({lowVal+inc*1}, 0, 0)'  # Slightly Brighter Red
            elif value <= quantiles[0.6]:
                return f'rgb({lowVal+inc*2}, 0, 0)'  # Medium Bright Red
            elif value <= quantiles[0.8]:
                return f'rgb({lowVal+inc*3}, 0, 0)'  # Brighter Red
            else:
                return 'rgb(255, 0, 0)'  # Brightest Red
        def style_function(feature):
            nTrips = feature['properties'][indicator]
            proportion = np.log(1 + nTrips) / np.log(1 + max_trips)
            red_intensity = int(20 + 235 * proportion)
            return {
                'fillOpacity': 0.5,
                'weight': 2,  # or however thick you want your roads
                'color': get_color(nTrips)
                # 'color': f'rgb({red_intensity}, 0, 0)'
            }
        def popup_function(feature):
            return folium.Popup(str(feature['properties'][indicator]))
        folium.GeoJson(
            df, 
            style_function=style_function, 
            popup=popup_function
        ).add_to(m)
                
    def plotLines_s2h(self, m): 
        if self.hub_network != 'none': 
            macroHubs = [hub for hub in self.hubs if hub.hubType == 'macro']
            for hub in self.hubs: 
                if hub.supplier_ids: 
                    for supplier_id in hub.supplier_ids: 
                        suppliers = self.suppliers if hub.hubType == 'macro' else macroHubs
                        supplier = [s for s in suppliers if s.unique_id == supplier_id][0]
                        folium.PolyLine(
                            locations=[supplier.coords, hub.coords], weight=1, 
                            color='#454545', dash_array='5'
                        ).add_to(m)
        else: 
            sites = self.construction_sites
            for supplier in self.suppliers: 
                for site in sites: 
                    folium.PolyLine(
                        locations=[supplier.coords, site.coords], weight=1, 
                        color='#454545', dash_array='5'
                    ).add_to(m)
                
    def plotLines_d2h(self, m):
        for hub in self.hubs: 
            coords_hub = hub.coords
            demSite_ids = list(set(hub.demolition_site_ids))
            for demSite_id in demSite_ids:
                demSites = self.demolition_sites_df
                demSite = demSites[demSites.unique_id == demSite_id].iloc[0]
                coord_demSite = (demSite.geometry.y, demSite.geometry.x)
                folium.PolyLine(
                    locations=[coords_hub, coord_demSite], weight=1, 
                    color='#454545', dash_array='5'
                ).add_to(m)
        
    def plotPoints_demSites(self, m, color, radius): 
        for hub in self.hubs: 
            demSite_ids = list(set(hub.demolition_site_ids))
            for demSite_id in demSite_ids: 
                demSites = self.demolition_sites_df
                demSite = demSites[demSites.unique_id == demSite_id].iloc[0]
                coord = (demSite.geometry.y, demSite.geometry.x)
                folium.CircleMarker(
                    location=coord, radius=radius, color=color, 
                    popup=folium.Popup(f'id: {demSite.unique_id}', max_width=300)
                ).add_to(m)
                
    def plotPoints_hubs(self, m, color):
        self.plotPoints(m, [hub for hub in self.hubs if hub.hubType == 'macro'], color, 5)
        if self.hub_network == 'decentralized': 
            for macroHub in [h for h in self.hubs if h.hubType == 'macro']: 
                for client_id in macroHub.client_ids: 
                    if client_id in [h.unique_id for h in self.hubs]: 
                        microHub = [h for h in self.hubs if h.unique_id == client_id][0]
                        folium.CircleMarker(
                            location=microHub.coords, radius=1, color=color, 
                            popup=folium.Popup(f'id: {microHub.unique_id}', max_width=300)
                        ).add_to(m)


import ipywidgets as widgets
from IPython.display import display

# Define your parameters and their options
params_options = {
    'hub_network': ['centralized', 'decentralized', 'none'],
    'network_type': ['road', 'water', 'rail'],
    'truck_type': ['diesel', 'semi', 'electric'],
    'biobased_type': ['biobased non-structural elements', 
                      'biobased non-structural + structural elements', 
                      'biobased non-structural + structural + foundation elements', 
                      'conventional'],
    'modularity_type': ['conventional', 'non-structural modules'], 
    'circularity_type': ['circular non-structural elements', 
                      'circular non-structural + structural elements', 
                      'circular non-structural + structural + foundation elements', 
                      'conventional'],
}

params_conversion = {
    'biobased_type': {'biobased non-structural elements': 'semi', 
                      'biobased non-structural + structural elements': 'full', 
                      'biobased non-structural + structural + foundation elements': 'extreme', 
                      'conventional': 'none'}, 
    'modularity_type': {'conventional': 'none', 
                        'non-structural modules': 'full'}, 
    'circularity_type': {'circular non-structural elements': 'semi', 
                      'circular non-structural + structural elements': 'full', 
                      'circular non-structural + structural + foundation elements': 'extreme', 
                      'conventional': 'none'}
}

import streamlit as st

def main():
    st.title("Agent Based Model of Circular Construction Hubs")

    # Create dropdown widgets
    parameters_dict = {}
    for key, options in params_options.items():
        parameters_dict[key] = st.selectbox(key, options)

    for key, value in parameters_dict.items():
        if key in params_conversion:
            parameters_dict[key] = params_conversion[key][value]

    if st.button("Run model!"):
        # create and run model 
        model = Model(parameters_dict)
        for i in range(2): 
            model.step()

        emissions_text, fig_emissions, fig_materials, map_html = model.visualize()

        # visualize in Streamlit
        st.write(emissions_text)
        col1, col2 = st.columns(2)
        col1.write(fig_emissions)
        col1.write(fig_materials)
        col2.markdown(map_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

