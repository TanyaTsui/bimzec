
from haversine import haversine
import pandas as pd


class ConstructionProject():
    '''Construction project class.

    This class represents a construction project or a group of housing units that are planned to be built in a certain location.'''

    def __init__(self, id: int, location: tuple, project_type: str, materials_required: dict) -> None:
        '''Initialize a construction project.

        Parameters:
        id (int): The unique identifier of the construction project.
        location (tuple): The location of the construction project.
        project_type (str): The type of construction project.
        materials_required (dict): The materials required for the construction project.
        '''
        self.id = id
        self.location = location
        self.project_type = project_type
        self.materials_required = materials_required
        self.number_of_vehicle_trips = {
            'wood': None, 'concrete': None, 'steel': None}

    def calculate_number_of_vehicle_trips(self, vehicle_volume: str) -> dict:
        '''Calculate the number of vehicle trips required to transport the materials to the construction project.

        Parameters:
        vehicle_volume (str): The volume of the vehicle that is used to transport the materials.

        Returns:
        number_of_vehicle_trips (dict): The number of vehicle trips required to transport the materials to the construction project.
        '''
        volume_multipliers = {'wood': 2, 'concrete': 1, 'steel': 1.5}
        for material, material_volume in self.materials_required.items():
            self.number_of_vehicle_trips[material] = material_volume * \
                volume_multipliers[material] / vehicle_volume
        return self.number_of_vehicle_trips


class Vehicle():
    '''Vehicle class.

    This class represents a vehicle that is used to transport materials to a construction project.
    '''

    def __init__(self, id, vehicle_type, vehicle_volume) -> None:
        '''Initialize a vehicle.

        Parameters:
        id (int): The unique identifier of the vehicle.
        vehicle_type (str): The type of vehicle.
        vehicle_volume (int): The volume of the vehicle.
        '''
        self.id = id
        self.vehicle_type = vehicle_type
        self.vehicle_volume = vehicle_volume


class ProductionSite():
    '''Production site class.

    This class represents a production site where materials are produced.

    Parameters:
    id (int): The unique identifier of the production site.
    production_site_type (str): The type of production site.
    location (tuple): The location of the production site.
    '''

    def __init__(self, id: int, production_site_type: str, location: tuple) -> None:
        self.id = id
        self.production_site_type = production_site_type
        self.location = location


class Model(ConstructionProject, Vehicle, ProductionSite):
    '''Model class.

    The model class represents the model that is used to calculate the number of vehicle trips required to transport the materials to the construction projects.
    It also calculates the total distance that is traveled by the vehicles and the amount of CO2 that is emitted during the transportation of the materials.
    '''

    def __init__(self, construction_projects, vehicles, production_sites) -> None:
        '''Initialize the model.

        Parameters:
        construction_projects (dict): The construction projects that are planned.
        vehicles (dict): The vehicles that are used to transport the materials.
        production_sites (dict): The production sites where the materials are produced.
        '''
        self.construction_projects = []
        self.vehicles = []
        self.production_sites = []
        self.number_of_vehicle_trips = {}

        # Initialize construction projects
        i = 0
        for project_type, project_attributes in construction_projects.items():
            number_of_projects = project_attributes['number_of_projects']  ### question1: what's number_of_projects, where is it?
            location = project_attributes['location']
            materials_required = project_attributes['materials_required']
            for _ in range(number_of_projects):
                self.construction_projects.append(ConstructionProject(
                    i, location, project_type, materials_required))
                i += 1

        # Initialize vehicles
        i = 0
        for vehicle_type, vehicle_attributes in vehicles.items():
            number_of_vehicles = vehicle_attributes['number_of_vehicles']
            vehicle_volume = vehicle_attributes['vehicle_volume']
            for _ in range(number_of_vehicles):
                self.vehicles.append(Vehicle(i, vehicle_type, vehicle_volume))
                i += 1

        # Initialize production sites
        i = 0
        for production_site_type, production_site_attributes in production_sites.items():
            number_of_production_sites = production_site_attributes['number_of_production_sites']
            location = production_site_attributes['location']
            for _ in range(number_of_production_sites):
                self.production_sites.append(
                    ProductionSite(i, production_site_type, location))
                i += 1

    def run_model(self) -> None:
        '''Run the model.'''
        self.calculate_total_number_oF_trips()
        self.make_od_matrix()
        self.calculate_total_distance()
        self.calculate_total_co2()

    def calculate_total_number_oF_trips(self) -> None:
        '''Calculate the total number of vehicle trips required to transport the materials to the construction projects.'''
        for project in self.construction_projects:
            chosen_vehicle = self.vehicles[1]
            vehicle_trips = project.calculate_number_of_vehicle_trips(
                chosen_vehicle.vehicle_volume)
            self.number_of_vehicle_trips[project.id] = {
                chosen_vehicle.vehicle_type: vehicle_trips}
        print(self.number_of_vehicle_trips)

    def make_od_matrix(self) -> None:
        '''Make the OD matrix that contains the distances between the production sites and the construction projects.'''
        self.od_matrix = []
        for production_site in self.production_sites:
            for project in self.construction_projects:
                distance = haversine(
                    production_site.location, project.location)
                self.od_matrix.append(
                    [production_site.id, project.id, distance])

        # Convert OD matrix to a dataframe
        self.od_matrix = pd.DataFrame(
            self.od_matrix, columns=['production_site_id', 'construction_project_id', 'distance'])
        print(self.od_matrix)

    def calculate_total_distance(self) -> None:
        '''Calculate the total distance that is traveled by the vehicles.'''
        total_distance = {}
        for project in self.construction_projects:
            project_distance = {}
            trips_by_vehicle_type = self.number_of_vehicle_trips[project.id]
            for vehicle_type, trips in trips_by_vehicle_type.items():
                distance_by_vehicle_type = 0
                for material, number_of_trips in trips.items():
                    # Get a production site that produces the material
                    production_site = [
                        site for site in self.production_sites if site.production_site_type == material][0]
                    # Get the total distance for the material
                    material_distance = self.od_matrix[(self.od_matrix['production_site_id'] == production_site.id) & (
                        self.od_matrix['construction_project_id'] == project.id)]['distance'].values[0]
                    # Add the total distance for the material to the total distance for the project
                    distance_by_vehicle_type += material_distance * number_of_trips
                project_distance[vehicle_type] = distance_by_vehicle_type
            total_distance[project.id] = project_distance
        self.total_distance = total_distance
        print(self.total_distance)

    def calculate_total_co2(self) -> None:
        '''Calculate the amount of CO2 that is emitted during the transportation of the materials.'''
        self.co2_emissions = {}
        co2_emissions_per_km = {'truck': 750,
                                'train': 500,
                                'ship': 250}
        for project in self.construction_projects:
            self.co2_emissions[project.id] = 0
            for vehicle_type, distance in self.total_distance[project.id].items():
                self.co2_emissions[project.id] += distance * \
                    co2_emissions_per_km[vehicle_type]
        print(self.co2_emissions)