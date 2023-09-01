from model import Model

# How many projects and of which type are planned?
construction_projects = {'conventional': {'number_of_projects': 1,  
                                          'location': (52.36, 4.90),  # Amsterdam
                                          'materials_required': {'wood': 0, 'concrete': 3, 'steel': 3}},
                         'bio-based': {'number_of_projects': 1,
                                       'location': (51.92, 4.48),  # Rotterdam
                                       'materials_required': {'wood': 1, 'concrete': 0, 'steel': 1}},
                         'modular': {'number_of_projects': 1,
                                     'location': (52.07, 4.30),  # The Hague
                                     'materials_required': {'wood': 1, 'concrete': 1, 'steel': 2}}}

vehicles = {'truck': {'number_of_vehicles': 1,
                      'vehicle_volume': 1},
            'train': {'number_of_vehicles': 1,
                      'vehicle_volume': 5},
            'ship': {'number_of_vehicles': 1,
                     'vehicle_volume': 10}}

production_sites = {'steel': {'number_of_production_sites': 1,
                              'location': (50.85, 5.69)},  # Maastricht
                    'concrete': {'number_of_production_sites': 1,
                                 'location': (50.84, 4.35)},  # Brussels
                    'wood': {'number_of_production_sites': 1,
                             'location': (47.26, 11.40)}}  # Innsbruck

my_model = Model(construction_projects, vehicles, production_sites)
my_model.run_model()