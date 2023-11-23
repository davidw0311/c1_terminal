import gamelib
import random
import math
import warnings
from sys import maxsize
import json

from gamelib.game_state import GameState 

"""
Most of the algo code you write will be in this file unless you create new
modules yourself. Start by modifying the 'on_turn' function.

Advanced strategy tips: 

  - You can analyze action frames by modifying on_action_frame function

  - The GameState.map object can be manually manipulated to create hypothetical 
  board states. Though, we recommended making a copy of the map to preserve 
  the actual current map state.
"""

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

    def on_turn(self, turn_state):
        """
        This function is called every turn with the game state wrapper as
        an argument. The wrapper stores the state of the arena and has methods
        for querying its state, allocating your current resources as planned
        unit deployments, and transmitting your intended deployments to the
        game engine.
        """
        game_state = gamelib.GameState(self.config, turn_state)
        gamelib.debug_write('Performing turn {} of your custom algo strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  #Comment or remove this line to enable warnings.

        self.starter_strategy(game_state)

        game_state.submit_turn()


    """
    NOTE: All the methods after this point are part of the sample starter-algo
    strategy and can safely be replaced for your custom algo.
    """

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

        # Do deepcopy here..
        game_state = GameState(game_state.config, game_state.serialized_string)

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

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called 
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at in json-docs.html in the root of the Starterkit.
        """
        # Let's record at what position we get scored on
        state = json.loads(turn_string)
        events = state["events"]
        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.scored_on_locations.append(location)
                gamelib.debug_write("All locations: {}".format(self.scored_on_locations))


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()
