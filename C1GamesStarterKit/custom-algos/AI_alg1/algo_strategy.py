import gamelib
import random
import math
import warnings
from sys import maxsize
import json
import numpy as np
import math
from copy import deepcopy
from scipy.optimize import curve_fit

"""
Most of the algo code you write will be in this file unless you create new
modules yourself. Start by modifying the 'on_turn' function.
Advanced strategy tips: 
  - You can analyze action frames by modifying on_action_frame function
  - The GameState.map object can be manually manipulated to create hypothetical 
  board states. Though, we recommended making a copy of the map to preserve 
  the actual current map state.
"""
global UTILITY_OF_INTERCEPTING_ATTACK
UTILITY_OF_INTERCEPTING_ATTACK = 10

class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        seed = random.randrange(maxsize)
        random.seed(seed)
        gamelib.debug_write('Random seed: {}'.format(seed))

    def on_game_start(self, config):
        """ 
        Read in config and perform any initial setup here 
        """
        gamelib.debug_write('Configuring your custom algo strategy...')
        self.config = config
        global WALL, SUPPORT, TURRET, SCOUT, DEMOLISHER, INTERCEPTOR, MP, SP
        WALL = config["unitInformation"][0]["shorthand"]
        SUPPORT = config["unitInformation"][1]["shorthand"]
        TURRET = config["unitInformation"][2]["shorthand"]
        SCOUT = config["unitInformation"][3]["shorthand"]
        DEMOLISHER = config["unitInformation"][4]["shorthand"]
        INTERCEPTOR = config["unitInformation"][5]["shorthand"]
        MP = 1
        SP = 0
        # This is a good place to do initial setup
        self.scored_on_locations = []
        self.spawn_stats = {}
        self.enemy_spawn_history = {}
        self.enemy_attacking_rounds = [] # records the round number where enemy dealt damange or took away health from us
        self.enemy_attack_history = [] # records the mp % used in attack
        self.enemy_defense_history = [] # records the mp % used in defense
        self.current_enemy_mp = 0

    def on_turn(self, turn_state):
        """
        This function is called every turn with the game state wrapper as
        an argument. The wrapper stores the state of the arena and has methods
        for querying its state, allocating your current resources as planned
        unit deployments, and transmitting your intended deployments to the
        game engine.
        """
        game_state = gamelib.GameState(self.config, turn_state)
        gamelib.debug_write('Performing turn {} of mcts strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  #Comment or remove this line to enable warnings.

        game_state.attempt_spawn(INTERCEPTOR, [[7,6], [20,6]], 1)
        self.mcts_strategy(game_state)
        self.tally_spawn_stats(game_state)

        game_state.submit_turn()


    """
    NOTE: All the methods after this point are part of the sample starter-algo
    strategy and can safely be replaced for your custom algo.
    """

    def choose_frontline_defence_row(self, game_state):
        self.FRONTLINE_DEFENCE_ROW = 11
        self.BACKLINE_DEFENCE_ROW = 8

    def build_initial_defences(self, game_state):
        # builds a turret in each corner with walls
        # then depending on FRONTLINE_DEFENCE_ROW, puts a row of 4 turrets evenly spread out with walls in front

        turret_locations = []
        turret_locations += [[i, 12] for i in [1,26]]
        turret_locations += [[i, 11] for i in [3,24]]
        turret_locations += [[i, self.FRONTLINE_DEFENCE_ROW-1] for i in [6,11,16,21]]

        # attempt_spawn will try to spawn units if we have resources, and will check if a blocking unit is already there
        game_state.attempt_spawn(TURRET, turret_locations)

        self.initial_turret_locations = turret_locations
        # Place walls in front of turrets to soak up damage for them
        wall_locations = []
        wall_locations += [[i, 13] for i in [0,1,2,25,26,27]]
        wall_locations += [[i, 12] for i in [2,3,4,23,24,25]]
        wall_locations += [[i, self.FRONTLINE_DEFENCE_ROW] for i in [2,4,6,7,9,10,11,12,14,15,16,17,18,20,21,23,25]]
        game_state.attempt_spawn(WALL, wall_locations)
        self.initial_wall_locations = wall_locations

        frontline_hole_locations = []
        frontline_hole_locations += [[i, self.FRONTLINE_DEFENCE_ROW] for i in [5,8,13,19,22]]
        self.frontline_hole_locations = frontline_hole_locations

        backline_hole_locations = []
        backline_hole_locations += [[i, self.BACKLINE_DEFENCE_ROW] for i in [7,20]]
        self.backline_hole_locations = backline_hole_locations


    def repair_initial_defences(self, game_state):
        game_state.attempt_spawn(TURRET, self.initial_turret_locations)
        game_state.attempt_spawn(WALL, self.initial_wall_locations)

    def get_best_attacking_path(self, game_state):
        self.hole_index = np.random.randint(len(self.hole_locations))

    def reset_wall_openings(self, game_state):
        game_state.attempt_remove(self.frontline_hole_locations)
        game_state.attempt_remove(self.backline_hole_locations)

    def build_backline_defences(self, game_state):

        backline_walls = []

        backline_walls += [[3, 10], [24,10], [4,9], [23,9]]
        backline_walls += [[i, self.BACKLINE_DEFENCE_ROW] for i in range(5,23) if [i, self.BACKLINE_DEFENCE_ROW] not in self.backline_hole_locations]

        game_state.attempt_spawn(WALL, backline_walls)


    def upgrade_structures(self, game_state):
        game_state.attempt_upgrade(self.initial_turret_locations)

        important_wall_locations = []
        important_wall_locations += [[i, 13] for i in [0,1,2,25,26,27]]
        important_wall_locations += [[i, 12] for i in [3,4,23,24]]
        important_wall_locations += [[i, self.FRONTLINE_DEFENCE_ROW] for i in [4,6,11,16,21,23]]   
        # important_wall_locations += [[3,10], [4,9], [5,8], [22,8], [23,9], [24,10]]   

        game_state.attempt_upgrade(self.initial_wall_locations)

    def build_selected_path(self, game_state, front_hole, back_hole):
        for loc in self.backline_hole_locations:
            if loc != back_hole:
                game_state.attempt_spawn(WALL, loc)

        for loc in self.frontline_hole_locations:
            if loc != front_hole:
                game_state.attempt_spawn(WALL, loc)


    def _attack_unit(self, game_state, unit, loc, damage):
        structures_destroyed = False
        unit_dmg = 0
        all_units_at_loc = game_state.game_map[loc]
        units_of_type = [_unit_of_type for _unit_of_type in all_units_at_loc if _unit_of_type.unit_type == unit.unit_type]
        units_to_destroy = []
        while damage > 0 and len(units_of_type) > 0:
            unit = units_of_type[-1]
            dmg_done = min(unit.health, damage)
            
            # Unit will be destroyed
            if unit.health <= damage:
                structures_destroyed = unit.stationary
                unit.health = 0
                damage -= unit.health

                units_to_destroy.append((loc, units_of_type.pop()))

            else:
                # Update unit health
                unit.health -= damage
                damage = 0

            # Impossible to stack multiple structures. If unit.stationary, both condition in if 
            # statement will result in termination of while loop
            if unit.stationary:
                unit_dmg += dmg_done

        return unit_dmg, structures_destroyed, units_to_destroy

    def _is_valid_attacker(self, game_state, location, attacker):
        atk_range = attacker.attackRange
        loc = (attacker.x, attacker.y)
        return atk_range >= game_state.game_map.distance_between_locations(location, loc)

    def _taken_dmg(self, game_state, location, health, player_index):
        damage = 0
        attackers = game_state.get_attackers(location, player_index)
        for attacker in attackers:
            if not self._is_valid_attacker(game_state, location, attacker):
                continue
            damage += attacker.damage_f
            if damage >= health:
                break
        return damage

    def _dealt_dmg(self, game_state, unit):
        unit_to_attack = game_state.get_target(unit)
        if unit_to_attack is None:
            return None

        damage = unit.damage_f if unit_to_attack.stationary else unit.damage_i
        return unit_to_attack, damage


    def _spawn_units(self, game_state, actions):
        # Stores a set of units spawned as a dictionary with location as key and a list of units at the location.
        # One element in the list would indicate a specific type of unit, its respective GameUnit, initial edge and path
        mobiles = {}
        for action in actions:
            unit, num, location = action
            num_spawned = game_state.attempt_spawn(unit, location, num=num)
            if unit in [SCOUT, DEMOLISHER, INTERCEPTOR]:
                unit_stack = [x for x in game_state.game_map[location] if x.unit_type == unit]
                edge = game_state.get_target_edge(location)
                if location not in mobiles:
                    mobiles[location] = [[unit, unit_stack, edge, None]]
                else:
                    mobiles[location].append([unit, unit_stack, edge, None])

        return mobiles    


    def _interact(self, game_state, friendly_mobiles, enemy_mobiles):
        # If mobiles are destroyed, update the dictionary with count / remove
        structure_destroyed = False
        unit_dmg_0 = 0
        unit_dmg_1 = 0
        
        # For all friendlies, find if they will attack anyone at their current location
        for location, unit_list in friendly_mobiles.items():
            for unit_details in unit_list:
                unit = unit_details[1][0]
                action_result = self._dealt_dmg(game_state, unit)
                if unit is None:
                    continue
                # Target found, damage done
                unit_to_attack, damage = action_result

                # if unit_to_attack.stationary:
                #     unit_dmg_0 += damage

                # Compute number of units destroyed / health lowered and apply to the game units
                num_attack_units = len(unit_details[1])
                effective_dmg = damage * num_attack_units

                attack_location = unit_to_attack.x, unit_to_attack.y

                


        # If they do, find the target and compute the damage * num

        # If target is structure, add min(damage, health) to unit_dmg_0
        
        # Mark target for destruction if necessary

        # C


        return unit_dmg_0, unit_dmg_1, structure_destroyed

    def _inner_step(self, game_state, mobiles):
        new_mobiles = {}
        health_dmg = 0
        for _, unit_list in mobiles.items():
            for unit_details in unit_list:
                if len(unit_details[3]) == 1:
                    # Score!
                    health_dmg += len(unit_details)
                    continue            


                new_location = unit_details[3][1]
                new_path = unit_details[3][1:]
                unit_details[3] = new_path
                
                if new_location not in new_mobiles:
                    new_mobiles[new_location] = [unit_details]
                else:
                    new_mobiles[new_location].append(unit_details)

                # Add the game units into the list
                game_state.game_map[new_location].extend(unit_details[1])

        return health_dmg, new_mobiles


    def _step(self, game_state, friendly_mobiles, enemy_mobiles):
        # If mobiles hit pass edge, then just delete them from the dictionary and return the dmg done
        for location in friendly_mobiles.keys():
            game_state.game_map.remove_unit(location)

        for location in enemy_mobiles.keys():
            game_state.game_map.remove_unit(location)
        
        health_dmg_0, friendly_mobiles = self._inner_step(friendly_mobiles)
        health_dmg_1, enemy_mobiles = self._inner_step(friendly_mobiles)

        return health_dmg_0, friendly_mobiles, health_dmg_1, enemy_mobiles


    def _get_path_for_mobiles(self, game_state, mobiles):
        for location, unit_list in mobiles.items():
            for i, (_, _, edge, path) in enumerate(unit_list):
                path = game_state.find_path_to_edge(location, edge)
                unit_list[i][3] = path
        return mobiles

    def simulate_action_pair(self, game_state, action_0=None, action_1=None):
        """
        Define an action as unit, num, location.

        Local copy of game_state is deep copied to prevent mutation. Simply resumbit the chosen
        action on the original game_state to submit the action outside of this function.
        """

        game_state = deepcopy(game_state)

        dmg_utility_0 = 0
        dmg_utility_1 = 0
        health_utility_0 = 0
        health_utility_1 = 0

        friendly_mobiles = self._spawn_units(game_state, action_0) if action_0 is not None else {}
        enemy_mobiles = self._spawn_units(game_state, action_1) if action_1 is not None else {}

        friendly_mobiles = self._get_path_for_mobiles(game_state, friendly_mobiles)
        enemy_mobiles = self._get_path_for_mobiles(game_state, enemy_mobiles)

        while len(friendly_mobiles) + len(enemy_mobiles):
            unit_dmg_0, unit_dmg_1, struct_destroyed = \
                self._interact(game_state, friendly_mobiles, enemy_mobiles)
            dmg_utility_0 += unit_dmg_0
            dmg_utility_1 += unit_dmg_1
            # Update routing when structure is destroyed as pathing may change
            if struct_destroyed:
                friendly_mobiles = self._get_path_for_mobiles(game_state, friendly_mobiles)
                enemy_mobiles = self._get_path_for_mobiles(game_state, enemy_mobiles)
            health_dmg_0, friendly_mobiles, health_dmg_1, enemy_mobiles = \
                self._step(game_state, friendly_mobiles, enemy_mobiles)
            health_utility_0 += health_dmg_0 
            health_utility_1 += health_dmg_1

        return dmg_utility_0, health_utility_0, dmg_utility_1, health_utility_1


    def predict_enemy_spawn_locations(self, game_state):
        # returns a dictionary of coord: {prob: p, demolisher_prob: dp, demolisher_num: dn, scout_prob: sp, scout_num: sn}  
        # coord is coordinate of opponent's spawn location as a tuple (x,y)
        # prob: probablity the opponent will spawn troops here
        # demolisher_prob: probability a demolisher will be spawned here
        # demolisher_num: number of estimated demolishers that will be spawned
        # scout_prob: probability that a scout will be spawned here
        # scout_num: number of estimated scouts that will be spawned
        most_likely_spawn_locations = {}
        num_attacking_rounds = len(self.enemy_attacking_rounds) + 1

        # gamelib.debug_write("history", self.enemy_spawn_history)

        for coord, info in self.enemy_spawn_history.items():
            most_likely_spawn_locations[coord] = {
                "prob": info['times_spawned_scout_or_demolisher_here']/num_attacking_rounds if num_attacking_rounds > 0 else 0, 
                "demolisher_prob": info['times_spawned_demolisher']/info['times_spawned_scout_or_demolisher_here'] if info['times_spawned_scout_or_demolisher_here'] > 0 else 0, 
                "demolisher_num": math.ceil(info['total_demolisher_count']/info['times_spawned_demolisher']) if info['times_spawned_demolisher'] > 0 else 0, 
                "scout_prob": info['times_spawned_scout']/info['times_spawned_scout_or_demolisher_here'] if info['times_spawned_scout_or_demolisher_here'] > 0 else 0, 
                "scout_num": math.ceil(info['total_scout_count']/info['times_spawned_scout']) if info['times_spawned_scout'] > 0 else 0,
            }
        return most_likely_spawn_locations


    def check_interceptor_reachability(self, game_state, unit, num, spawn_loc, front_hole, back_hole):
        # checks whether an interceptor can intercept an enemy unit spawned at the spawn_loc given front_hole, back_hole
        # returns 
        # reachable: True if the unit can be intercepted by interceptors
        # interceptor_spawn_loc: where the interceptor needs to be spawned (None if not reachable)
        # interceptor_num: how many interceptors to spawn (0 if not reachable)

        copied_game_state = deepcopy(game_state)
        
        self.build_selected_path(copied_game_state, front_hole, back_hole)
        if unit == SCOUT:
            speed = 1
        elif unit == DEMOLISHER:
            speed = 2
        gamelib.debug_write('enemy spawn loc', spawn_loc)
        # gamelib.debug_write('enemy spawn loc', spawn_loc)
        enemy_path = copied_game_state.find_path_to_edge(spawn_loc)

        interceptor_speed = 4
        interceptor_range = 4.3

        possible_interceptor_spawns = [[7,6], [9,4], [11,2], [13,0], [14,0],[16,2],[18,4],[20,6]]
        interceptor_utility = {}
        for interceptor_spawn_location in possible_interceptor_spawns:
            frames_in_range = 0 # count how many frames the unit will be seen by our interceptor
            interceptor_path = copied_game_state.find_path_to_edge(interceptor_spawn_location)

            interceptor_index = -1
            earliest_interception_frame = len(enemy_path)
            for enemy_index in range(len(enemy_path)):
                if enemy_index%(interceptor_speed//speed) == 0:
                    interceptor_index += 1
                if interceptor_index >= len(interceptor_path):
                    break
                enemy_position = enemy_path[enemy_index]
                interceptor_position = interceptor_path[interceptor_index]

                if copied_game_state.game_map.distance_between_locations(enemy_position, interceptor_position) <= interceptor_range:
                    frames_in_range += 1
                    earliest_interception_frame = min(earliest_interception_frame, enemy_index)
                    # gamelib.debug_write('can intercept on frame', earliest_interception_frame)
                    # gamelib.debug_write('enemy path: ', enemy_path)
                    # gamelib.debug_write('our path', interceptor_path)
            interceptor_utility[tuple(interceptor_spawn_location)] = {'earliest_frame':earliest_interception_frame, 'number_of_frames': frames_in_range}


        best_interceptor_locations = [(k,v) for k,v in sorted(interceptor_utility.items(), key=lambda x:x[1]['earliest_frame'])]

        interceptable = False
        location = None
        number_of_interceptors = 0
        interception_utility = 0 
        for loc, info in best_interceptor_locations:
            if info['number_of_frames'] > 0:
                interceptable = True
                location = loc
                number_of_interceptors = max(1, int(num/info['number_of_frames'])) if unit == SCOUT else max(1, int(num))
                interception_utility = (35 - info['earliest_frame']) * 2
                break

        if enemy_path: # if the unit is spawned where there is structure, this will return None
            interceptor_speed = 4
            interceptor_range = 4.3

            possible_interceptor_spawns = [[7,6], [9,4], [11,2], [13,0], [14,0],[16,2],[18,4],[20,6]]
            interceptor_utility = {}
            for interceptor_spawn_location in possible_interceptor_spawns:
                frames_in_range = 0 # count how many frames the unit will be seen by our interceptor
                interceptor_path = copied_game_state.find_path_to_edge(interceptor_spawn_location)

                interceptor_index = -1
                earliest_interception_frame = len(enemy_path)
                for enemy_index in range(len(enemy_path)):
                    if enemy_index%(interceptor_speed//speed) == 0:
                        interceptor_index += 1
                    if interceptor_index >= len(interceptor_path):
                        break
                    enemy_position = enemy_path[enemy_index]
                    interceptor_position = interceptor_path[interceptor_index]

                    if copied_game_state.game_map.distance_between_locations(enemy_position, interceptor_position) <= interceptor_range:
                        frames_in_range += 1
                        earliest_interception_frame = min(earliest_interception_frame, enemy_index)
                        # gamelib.debug_write('can intercept on frame', earliest_interception_frame)
                        # gamelib.debug_write('enemy path: ', enemy_path)
                        # gamelib.debug_write('our path', interceptor_path)
                interceptor_utility[tuple(interceptor_spawn_location)] = {'earliest_frame':earliest_interception_frame, 'number_of_frames': frames_in_range}


            best_interceptor_locations = [(k,v) for k,v in sorted(interceptor_utility.items(), key=lambda x:x[1]['earliest_frame'])]


            for loc, info in best_interceptor_locations:
                if info['number_of_frames'] > 0:
                    interceptable = True
                    location = loc
                    number_of_interceptors = max(1, int(num/info['number_of_frames'])) 
                    interception_utility = (100 - info['earliest_frame'])
                    break

        return interceptable, location, number_of_interceptors, interception_utility

    def execute_defence_plan(self, game_state, plan):
        if not plan:
            return

        self.build_selected_path(game_state, front_hole=plan['front_hole'], back_hole=plan['back_hole'])

        self.build_selected_path(game_state, front_hole=plan['front_hole'], back_hole=plan['back_hole'])
        if plan['interceptor_num'] > 0:
            game_state.attempt_spawn(INTERCEPTOR, list(plan['interceptor_loc']), plan['interceptor_num'])

    def choose_defence_move(self, game_state):
       
        enemy_spawn_locations = self.predict_enemy_spawn_locations(game_state) # {(x,y): {prob:p, demolisher_prob, scout_prob}}
        # gamelib.debug_write('enemy spawn locations', enemy_spawn_locations)
        NUM_LOCATIONS_TO_SEARCH = 5
        most_likely_scout_locations = {k: v for k, v in sorted(enemy_spawn_locations.items(), reverse=True, key=lambda v: v[1]['scout_prob'])[:NUM_LOCATIONS_TO_SEARCH]}
        most_likely_demolisher_locations = {k: v for k, v in sorted(enemy_spawn_locations.items(), reverse=True, key=lambda v: v[1]['demolisher_prob'])[:NUM_LOCATIONS_TO_SEARCH]}
        most_likely_locations = {}
        most_likely_locations.update(most_likely_scout_locations)
        most_likely_locations.update(most_likely_demolisher_locations)
        gamelib.debug_write('most likely enemy spawn locations: ', most_likely_locations)
        # gamelib.debug_write('stats for (3,17) ', most_likely_locations.get((3,17)))
        
        plans = []
        best_expected_utility = -np.inf
        best_plan = None
        for coord, info in most_likely_locations.items():
            
            coord = list(coord)
            spawn_prob = info['prob']
            demolisher_prob = info['demolisher_prob']
            demolisher_num = info['demolisher_num']
            
            scout_prob = info['scout_prob']
            scout_num = info['scout_num']
            plan = {}
            
            for front_hole in self.frontline_hole_locations:
                for back_hole in self.backline_hole_locations:
                    expected_loss = 0 # placeholder for now, calculate with scout and demolisher utility

                    if np.random.rand() < demolisher_prob:
                        reachable, interceptor_spawn_loc, interceptor_num, interception_utility = self.check_interceptor_reachability(game_state=game_state, unit=DEMOLISHER, num=demolisher_num, spawn_loc=coord, front_hole=front_hole, back_hole=back_hole)
                        prob = demolisher_prob
                    else:
                        reachable, interceptor_spawn_loc, interceptor_num, interception_utility = self.check_interceptor_reachability(game_state=game_state, unit=SCOUT, num=scout_num, spawn_loc=coord, front_hole=front_hole, back_hole=back_hole)
                        prob = scout_prob
                        
                    if reachable:
                        expected_utility = (interception_utility + expected_loss)*prob
                        
                    else:
                        expected_utility = expected_loss*prob
                        
                    plan['expected_utility'] = expected_utility
                    plan['front_hole'] = front_hole
                    plan['back_hole'] = back_hole
                    plan['interceptor_loc'] = interceptor_spawn_loc
                    plan['interceptor_num'] = interceptor_num
                    
                    plans.append(plan)
                    if expected_utility > best_expected_utility:
                        gamelib.debug_write('turn', game_state.turn_number,'new best plan', plan)
                        best_expected_utility = expected_utility
                        best_plan = plan.copy()
                        
        self.execute_defence_plan(game_state, best_plan)                
        self.upgrade_structures(game_state)
    

    def calculate_demolisher_utility(self, game_state, spawn_location, front_hole, back_hole, num_units):
        return np.random.rand()

    def calculate_scout_utility(self, game_state, spawn_location, front_hole, back_hole, num_units):
        return np.random.rand()
    
    def calculate_interceptor_utility(self, game_state, spawn_location, front_hole, back_hole, num_units):
        return np.random.rand()


    def choose_offence_move(self, game_state, sub_stategy="Assault"):

        possible_actions = []

        # To simplify we will just check sending them from back left and right
        spawn_location_options = [[13, 0], [14, 0]]
        for back_hole in self.backline_hole_locations:
            for front_hole in self.frontline_hole_locations:
                for spawn_location in spawn_location_options:

                    num_units = game_state.get_resource(MP, 0)//game_state.type_cost(SCOUT)[MP]
                    scout_utility = self.calculate_scout_utility(game_state, spawn_location, front_hole, back_hole, num_units)
                    possible_actions.append({
                        "utility": scout_utility, 
                        "holes": [front_hole, back_hole],
                        "units": [{'type': SCOUT, 'num': int(num_units), 'loc': spawn_location}],
                        "structures": []
                        })

                    num_units = game_state.get_resource(MP, 0)//game_state.type_cost(DEMOLISHER)[MP]
                    demolisher_utility = self.calculate_demolisher_utility(game_state, spawn_location, front_hole, back_hole, num_units)
                    possible_actions.append({
                        "utility": demolisher_utility, 
                        "holes": [front_hole, back_hole],
                        "units": [{'type': DEMOLISHER, 'num': int(num_units), 'loc': spawn_location}],
                        "structures": []
                        })

        highest_utility = -np.inf
        best_action = possible_actions[0]
        for a in possible_actions:
            if a['utility'] > highest_utility:
                best_action = a.copy()
                highest_utility = a['utility']

        for unit in best_action['units']:
            game_state.attempt_spawn(unit['type'], unit['loc'], unit['num'])

        for structure in best_action['structures']:
            game_state.attempt_spawn(structure['type'], structure['loc'])

    def predict_enemy(self, data):
        def fourier_series(x, *params):
            result = 0
            for i in range(0, len(params), 3):
                amplitude, frequency, phase = params[i:i+3]
                result += amplitude * np.sin(frequency * x + phase)
            return result
        num_terms = 3 
        initial_guess = [1.0, 2.0, 0.0] * num_terms
        x_values = np.linspace(0, 8*np.pi, len(data))
        data = np.arange(data)
        params, covariance = curve_fit(fourier_series, x_values, data, p0=initial_guess)
        return fourier_series(8*np.pi, *params)

    def choose_HLA(self, game_state):
        #TODO: implement better logic here, to decide at high level whether to attack, defend, or stall, or use some mixed strategy
        # depending on past opponent attacks, threat level based on opponet's base reconfiguration last turn, how much mp they have
        # somehow store a "memory" of past opponent's attacks, check where their walls are planning to be removed

        strategy = {'attack': 1.0, 'defend': 1.0, 'stall': 1.0}
        sub_stategy = {'Assault': 1.0, 'Harassment': 1.0, 'Plundering': 1.0}
        # We focus on the interceptor sending of each side: when, where, how many

        our_mp = game_state.get_resource(MP, 0)
        our_sp = game_state.get_resource(SP, 0)

        enemy_mp = game_state.get_resource(MP, 1)
        enemy_sp = game_state.get_resource(SP, 1)
        self.current_enemy_mp = enemy_mp

        if enemy_mp > 5:
            strategy['defend'] *= enemy_mp
            if enemy_mp < 10:
                strategy['stall'] *= 5
        elif our_mp > 10:
            strategy['attack'] *= our_mp / 5
        else:
            strategy['stall'] *= 10

        enemy_attack_p = self.predict_enemy(self.enemy_attack_history)
        enemy_defense_p = self.predict_enemy(self.enemy_defense_history)

        strategy['defend'] *= enemy_attack_p
        strategy['attack'] *= min(5, 0.5 / enemy_defense_p)
        strategy['stall'] *= max(1, enemy_defense_p * 5)

        # sub_stategy
        if enemy_defense_p * 2 < sum(self.enemy_defense_history) / len(self.enemy_defense_history):
            sub_stategy['Assault'] *= 10
        elif enemy_defense_p < sum(self.enemy_defense_history) / len(self.enemy_defense_history):
            sub_stategy['Assault'] *= 2
            sub_stategy['Assault'] *= our_mp / 5    
        else:
            sub_stategy['Assault'] *= 0.2

        if enemy_sp < 5:
            sub_stategy['Plundering'] *= max(2, 5 / enemy_sp)
            sub_stategy['Plundering'] *= max(1, our_mp * 0.1)
        else:
            sub_stategy['Plundering'] *= 0.1

        # normalize
        total = sum(strategy.values())
        for k in strategy:
            strategy[k] /= total

        total = sum(sub_stategy.values())
        for k in sub_stategy:
            sub_stategy[k] /= total

        return strategy, sub_stategy

    def mcts_strategy(self, game_state):

        if game_state.turn_number == 0:
            self.choose_frontline_defence_row(game_state)
            self.build_initial_defences(game_state)
        else:
            self.repair_initial_defences(game_state)
            self.build_backline_defences(game_state)

        hla_strategy, sub_stategy = self.choose_HLA(game_state)

        num = np.random.rand()
        if num <= hla_strategy['attack']:
            self.choose_offence_move(game_state, max(sub_stategy, key=sub_stategy.get))
        elif num <= hla_strategy['attack'] + hla_strategy['defend']:
            self.choose_defence_move(game_state) # TODO: David
        else:
            # do nothing
            pass

        self.repair_initial_defences(game_state)    
        self.reset_wall_openings(game_state)  

    def tally_spawn_stats(self, game_state):

        turn_num = game_state.turn_number -1
        if turn_num not in self.spawn_stats:
            gamelib.debug_write('turn num ', turn_num, " not in", self.spawn_stats.keys())
            return
        
        enemy_attack_cost = 0
        enemy_defense_cost = 0

        for coord, stats in self.spawn_stats[turn_num]['coord_to_unit'].items():
            if coord not in self.enemy_spawn_history.keys():
                self.enemy_spawn_history[coord]={
                    "times_spawned_here": 0,
                    "times_spawned_scout_or_demolisher_here": 0,
                    "times_spawned_scout": 0,
                    "total_scout_count": 0,
                    "times_spawned_demolisher": 0,
                    "total_demolisher_count": 0,
                    "times_spawned_interceptor": 0,
                    "total_interceptor_count": 0,
                    "health_taken": 0,
                    "damage_dealt": 0
                }
            self.enemy_spawn_history[coord]['times_spawned_here'] += 1
            if stats[SCOUT] > 0 or stats[DEMOLISHER] > 0:
                self.enemy_spawn_history[coord]['times_spawned_scout_or_demolisher_here'] += 1
            if stats[SCOUT] > 0:
                self.enemy_spawn_history[coord]['times_spawned_scout'] += 1
                self.enemy_spawn_history[coord]['total_scout_count'] += stats[SCOUT]
                enemy_attack_cost += stats[SCOUT]
            if stats[DEMOLISHER] > 0:
                self.enemy_spawn_history[coord]['times_spawned_demolisher'] += 1
                self.enemy_spawn_history[coord]['total_demolisher_count'] += stats[DEMOLISHER]
                enemy_attack_cost += stats[DEMOLISHER] * 3
            if stats[INTERCEPTOR] > 0:
                self.enemy_spawn_history[coord]['times_spawned_interceptor'] += 1
                self.enemy_spawn_history[coord]['total_interceptor_count'] += stats[INTERCEPTOR]
                enemy_defense_cost += stats[INTERCEPTOR]
        self.enemy_attack_history.append(enemy_attack_cost/self.current_enemy_mp)
        self.enemy_defense_history.append(enemy_defense_cost/self.current_enemy_mp)

        total_damage_dealt = 0
        total_health_taken = 0
        for id, id_info in self.spawn_stats[turn_num]['id_info'].items():
            spawn_coord = id_info['coord']
            self.enemy_spawn_history[spawn_coord]['health_taken'] += id_info['health_taken']
            total_health_taken += id_info['health_taken']

            self.enemy_spawn_history[spawn_coord]['damage_dealt'] += id_info['damage_dealt']
            total_damage_dealt += id_info['damage_dealt']

        gamelib.debug_write(f"damage dealt on round {turn_num}", total_damage_dealt)
        gamelib.debug_write(f"health taken on round {turn_num}", total_health_taken)
        if total_damage_dealt > 0 or total_health_taken > 0:
            self.enemy_attacking_rounds.append(turn_num)
        # gamelib.debug_write("turn num: ", turn_num, "enemy spawn history", self.enemy_spawn_history)

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called 
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at in json-docs.html in the root of the Starterkit.
        """
        # Let's record at what position we get scored on
        state = json.loads(turn_string)
        turn_num = state["turnInfo"][1]
        events = state["events"]

        spawns = events["spawn"]
        if turn_num not in self.spawn_stats:
            self.spawn_stats[turn_num] = {'id_info': {}, 'coord_to_unit':{}}


        for spawn_event in spawns:
            if spawn_event[3] == 1: # if this is our spawned unit, ignore
                continue

            unit = spawn_event[1]
            if unit == 3:
                unit = SCOUT
            elif unit == 4:
                unit = DEMOLISHER
            elif unit == 5:
                unit = INTERCEPTOR
            else:
                continue # ignore other spawn events

            coord = tuple(spawn_event[0])

            id = spawn_event[2]
            gamelib.debug_write('enemy spawned unit with id', id, ' of type', unit, 'on turn', turn_num)
            if id in self.spawn_stats[turn_num]['id_info']:
                continue # we have already recorded this unit

            self.spawn_stats[turn_num]['id_info'][id] = {"coord":None, "health_taken": 0, "damage_dealt": 0}

            self.spawn_stats[turn_num]['id_info'][id]['coord'] = coord
            if coord not in self.spawn_stats[turn_num]['coord_to_unit']:
                self.spawn_stats[turn_num]['coord_to_unit'][coord] = {DEMOLISHER:0, SCOUT:0, INTERCEPTOR:0}

            self.spawn_stats[turn_num]['coord_to_unit'][coord][unit] += 1

        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            id = breach[3]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                spawn_coord = self.spawn_stats[turn_num]['id_info'][id]['coord']
                self.spawn_stats[turn_num]['id_info'][id]['health_taken'] = 1

                self.scored_on_locations.append(spawn_coord)

        attacks = events["attack"]
        for attack_event in attacks:
            if attack_event[6] == 1: # ignore if it is our attack
                continue

            attacking_unit = attack_event[3]
            if attacking_unit == 3:
                attacking_unit = SCOUT
            elif attacking_unit == 4:
                attacking_unit = DEMOLISHER
            else:
                continue # ignore other units attacking     
            attacking_id = attack_event[4]
            # attacked_unit = attack_event[5]
            # if attacked_unit == 0:
            #     attacked_unit = WALL
            # elif attacked_unit == 1:
            #     attacked_unit = SUPPORT
            # elif attacked_unit == 2:
            #     attacked_unit = TURRET
            # else:
            #     continue # only consider structures being attacked

            damage = attack_event[2]
            self.spawn_stats[turn_num]['id_info'][attacking_id]['damage_dealt'] += damage

    def build_defences(self, game_state):
        """
        Build basic defenses using hardcoded locations.
        Remember to defend corners and avoid placing units in the front where enemy demolishers can attack them.
        """
        # Useful tool for setting up your base locations: https://www.kevinbai.design/terminal-map-maker
        # More community tools available at: https://terminal.c1games.com/rules#Download

        # Place turrets that attack enemy units
        turret_locations = [[0, 13], [27, 13], [8, 11], [19, 11], [13, 11], [14, 11]]
        # attempt_spawn will try to spawn units if we have resources, and will check if a blocking unit is already there
        game_state.attempt_spawn(TURRET, turret_locations)

        # Place walls in front of turrets to soak up damage for them
        wall_locations = [[8, 12], [19, 12]]
        game_state.attempt_spawn(WALL, wall_locations)
        # upgrade walls so they soak more damage
        game_state.attempt_upgrade(wall_locations)

    def build_reactive_defense(self, game_state):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        for location in self.scored_on_locations:
            # Build turret one space above so that it doesn't block our own edge spawn locations
            build_location = [location[0], location[1]+1]
            game_state.attempt_spawn(TURRET, build_location)

    def stall_with_interceptors(self, game_state):
        """
        Send out interceptors at random locations to defend our base from enemy moving units.
        """
        deploy_location = []
        # We can spawn moving units on our edges so a list of all our edge locations
        friendly_edges = game_state.game_map.get_edge_locations(game_state.game_map.BOTTOM_LEFT) + game_state.game_map.get_edge_locations(game_state.game_map.BOTTOM_RIGHT)

        # Remove locations that are blocked by our own structures 
        # since we can't deploy units there.
        deploy_locations = self.filter_blocked_locations(friendly_edges, game_state)

        # While we have remaining MP to spend lets send out interceptors randomly.
        while game_state.get_resource(MP) >= game_state.type_cost(INTERCEPTOR)[MP] and len(deploy_locations) > 0:
            # Choose a random deploy location.
            deploy_index = random.randint(0, len(deploy_locations) - 1)
            deploy_location = deploy_locations[deploy_index]

            game_state.attempt_spawn(INTERCEPTOR, deploy_location)
            """
            We don't have to remove the location since multiple mobile 
            units can occupy the same space.
            """

    def demolisher_line_strategy(self, game_state):
        """
        Build a line of the cheapest stationary unit so our demolisher can attack from long range.
        """
        # First let's figure out the cheapest unit
        # We could just check the game rules, but this demonstrates how to use the GameUnit class
        stationary_units = [WALL, TURRET, SUPPORT]
        cheapest_unit = WALL
        for unit in stationary_units:
            unit_class = gamelib.GameUnit(unit, game_state.config)
            if unit_class.cost[game_state.MP] < gamelib.GameUnit(cheapest_unit, game_state.config).cost[game_state.MP]:
                cheapest_unit = unit

        # Now let's build out a line of stationary units. This will prevent our demolisher from running into the enemy base.
        # Instead they will stay at the perfect distance to attack the front two rows of the enemy base.
        for x in range(27, 5, -1):
            game_state.attempt_spawn(cheapest_unit, [x, 11])

        # Now spawn demolishers next to the line
        # By asking attempt_spawn to spawn 1000 units, it will essentially spawn as many as we have resources for
        game_state.attempt_spawn(DEMOLISHER, [24, 10], 1000)

    def least_damage_spawn_location(self, game_state, location_options):
        """
        This function will help us guess which location is the safest to spawn moving units from.
        It gets the path the unit will take then checks locations on that path to 
        estimate the path's damage risk.
        """
        damages = []
        # Get the damage estimate each path will take
        for location in location_options:
            path = game_state.find_path_to_edge(location)
            damage = 0
            for path_location in path:
                # Get number of enemy turrets that can attack each location and multiply by turret damage
                damage += len(game_state.get_attackers(path_location, 0)) * gamelib.GameUnit(TURRET, game_state.config).damage_i
            damages.append(damage)

        # Now just return the location that takes the least damage
        return location_options[damages.index(min(damages))]

    def detect_enemy_unit(self, game_state, unit_type=None, valid_x = None, valid_y = None):
        total_units = 0
        for location in game_state.game_map:
            if game_state.contains_stationary_unit(location):
                for unit in game_state.game_map[location]:
                    if unit.player_index == 1 and (unit_type is None or unit.unit_type == unit_type) and (valid_x is None or location[0] in valid_x) and (valid_y is None or location[1] in valid_y):
                        total_units += 1
        return total_units

    def filter_blocked_locations(self, locations, game_state):
        filtered = []
        for location in locations:
            if not game_state.contains_stationary_unit(location):
                filtered.append(location)
        return filtered

    ## BELOW ARE STARTER CODE METHODS, NOT USED  
    def starter_strategy(self, game_state):
        """
        For defense we will use a spread out layout and some interceptors early on.
        We will place turrets near locations the opponent managed to score on.
        For offense we will use long range demolishers if they place stationary units near the enemy's front.
        If there are no stationary units to attack in the front, we will send Scouts to try and score quickly.
        """
        # First, place basic defenses
        self.build_defences(game_state)
        # Now build reactive defenses based on where the enemy scored
        self.build_reactive_defense(game_state)

        # If the turn is less than 5, stall with interceptors and wait to see enemy's base
        if game_state.turn_number < 5:
            self.stall_with_interceptors(game_state)
        else:
            # Now let's analyze the enemy base to see where their defenses are concentrated.
            # If they have many units in the front we can build a line for our demolishers to attack them at long range.
            if self.detect_enemy_unit(game_state, unit_type=None, valid_x=None, valid_y=[14, 15]) > 10:
                self.demolisher_line_strategy(game_state)
            else:
                # They don't have many units in the front so lets figure out their least defended area and send Scouts there.

                # Only spawn Scouts every other turn
                # Sending more at once is better since attacks can only hit a single scout at a time
                if game_state.turn_number % 2 == 1:
                    # To simplify we will just check sending them from back left and right
                    scout_spawn_location_options = [[13, 0], [14, 0]]
                    best_location = self.least_damage_spawn_location(game_state, scout_spawn_location_options)
                    game_state.attempt_spawn(SCOUT, best_location, 1000)

                # Lastly, if we have spare SP, let's build some supports
                support_locations = [[13, 2], [14, 2], [13, 3], [14, 3]]
                game_state.attempt_spawn(SUPPORT, support_locations)




if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()