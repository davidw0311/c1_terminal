def choose_HLA(self, game_state):
    # TOD0: implement better logic here, to decide at high level whether to attack, defend, or stall, or use some mixed strategy
    # depending on past opponent attacks, threat level based on opponet's base reconfiguration last turn, how much mp they have
    # somehow store a "memory" of past opponent's attacks, check where their walls are planning to be removed

    # TOD0: Shanhe
    strategy = {'attack': 0.0, 'defend': 0.0,'stall': 0.0}

    # Our Health & Enemy Health
    our_health = game_state.get_resources(game_state.player_index, gamelib.GameState.RESOURCE_HEALTH)
    enemy_health = game_state.get_resources(1 - game_state.player_index, gamelib.GameState.RESOURCE_HEALTH)

    # Get Iur Structure Units Count
    our_structure_count = game_state.get_resource(game_state.SP)
    # Get Enemy Structure Units Count
    enemy_structure_count = game_state.get_resource(game_state.SP, 1)


    our_mp = game_state.get_resource(MP, 0)
    our_sp = game_state.get_resource(SP, 0)
    enemy_mp = game_state.get_resource(MP, 1)
    enemy_sp = game_state.get_resource(SP, 1)

    if game_state.turn_number == 1:
        old_our_health = 30
        old_enemy_health = 30
        health_subtraction = 0

        old_enemy_structure_count = 0
        old_our_structure_count = 0
        structure_subtraction = 0
    else:
        # Calculate the subtraction of health change between enemy and me
        # If health_subtraction > 0, this means that the enemy's health loss is greater than ours
        health_subtraction = ( our_health - old_our_health ) - ( enemy_health - old_enemy_health )

        # Calculate the structure count of health change between enemy and me
        # If structure_subtraction > 0, this means that the enemy's structure loss is greater than ours
        structure_subtraction = ( our_structure_count - old_our_structure_count ) - ( enemy_structure_count - old_enemy_structure_count )

    if health_subtraction >= 0:
        if our_mp > 10:
            strategy = {'attack': 1.0, 'defend': 0.0, 'stall': 0.0}
        else:
            strategy = {'attack': 0.0,'defend': 0.0,'stall': 1.0}
    else:
        strategy = {'attack': 0.0,'defend': 1.0, 'stall': 0.0}

    if game_state.turn_number != 1:
        old_enemy_health = enemy_health
        old_our_health = our_health        

    return strategy