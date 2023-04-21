#!/usr/bin/env python3

import json
import openai
import os
import pdb

from random import randint
from textwrap import dedent, fill

GAME_TEMPLATE = {
    '_title': '$game_title',
    '_theme': '$game_theme',
    '_objective': '$game_objective',
    '_plot': '$game_plot',
    'entities': [
        {
            'type': 'location',
            'exits': {
                'north': '$location2_name',
                'south': '$location3_name',
            },
            'short_description': 'a $short_description',
            'long_description': 'You are in a $long_description',
            'name': '$location1_name',
            'adjective': '$single_word',
        },
        {
            'type': 'player',
            'class': '$class',
            'alive': True,
            'position': '$location1_name',
            'short_description': 'a $short_description',
            'long_description': 'You are $long_description',
        },
        {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'position': 'player',
        },
        {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'position': '$location1_name',
        },
    ],
}


def DEBUG(*msg):
    if os.environ.get('DEBUG'):
        print(*msg)


def _get_entity_by_name(game, entity_name):
    for e in game['entities']:
        if e.get('name', '') == entity_name:
            return e
    return None


def _get_entity_by_type(game, entity_type):
    for e in game['entities']:
        if e.get('type', '') == entity_type:
            return e
    return None


### AI text generation ###


openai.api_key = os.environ.get('OPENAI_API_KEY')


def _generate_content(prompt, str_type):
    print(f"# Generating {str_type}...")
    res = openai.Completion.create(
        engine="text-davinci-003",
        prompt=dedent(prompt).lstrip(),
        temperature=0.7,
        max_tokens=2000,
    )

    try:
        data = json.loads(res.choices[0].text)
    except BaseException:
        print(res.choices[0].text)
        raise

    return data


def generate_world(game):
    prompt = """
    You are a software agent. You will receive JSON and output JSON.

    Given this json data structure that represents a text-adventure game,
    please replace all variables starting with a dollar sign (`$`) with
    rich descriptions.

    INPUT:

    $json

    OUTPUT:
    """

    json_str = json.dumps(game)
    prompt = prompt.replace("$json", json_str)

    game = _generate_content(prompt, 'game')
    DEBUG(game)

    player = _get_entity_by_type(game, "player")

    # mark initial position as seen
    player_position = _get_entity_by_name(game, player['position'])
    player_position["seen"] = True

    # make sure all object names are lowercase
    for entity in game['entities']:
        if entity.get('type', '') == 'object':
            entity['name'] = entity['name'].lower()

    return game


def generate_position(game, position):
    prompt = '''
    You are a software agent. You will receive JSON and output JSON.

    Given this json data structure that represents a text-adventure game,
    please create a new entity of type "location", named "{0}".

    Populate this new location with all necessary attributes, including
    rich new descriptions, following the same atmosphere of the previous
    locations.

    At least one location in the game should have four exits (north,
    south, east and west); and one exit should usually go back to the
    previous location.

    Don't return the complete game JSON. Return the JSON for the data
    structure corresponding to the new entity.

    INPUT:

    {1}

    OUTPUT:
    '''.format(
        position,
        json.dumps(game))

    location = _generate_content(prompt, 'location')
    location['seen'] = False

    return location


def create_object(game, position):
    prompt = '''
    You are a software agent. You will receive JSON and output JSON.

    Given this json data structure that represents a text-adventure game,
    please create a new entity of type "object" in the position "{0}".

    Populate this new object with all necessary attributes, including a
    single-word name and rich descriptions, following the same atmosphere
    of the game.

    Don't return the complete game JSON. Return the JSON for the data
    structure corresponding to the new entity.

    INPUT:

    {1}

    OUTPUT:
    '''.format(
        position,
        json.dumps(game))

    obj = _generate_content(prompt, 'object')

    return obj


def magic_action(game, sentence):

    game['output'] = '$short_action_description'

    prompt = '''
    You are a software agent. You will receive JSON and output JSON.

    Given this json data structure that represents a text-adventure game:

    {0}

    The user typed the following command: "{1}"

    Replace the "output" value with a description of the action result.

    You don't have to please the player; consider the user class and
    location as well the object properties to see if the action can be
    performed.

    Modify the object properties as necessary to reflect the changes.

    Return the complete JSON data structure for the game.

    OUTPUT:
    '''.format(
        json.dumps(game),
        sentence)

    game = _generate_content(prompt, 'action')

    if 'output' in game:
        print(fill(game['output']))
        del game['output']

    return game


### auxiliar functions ###


def _clean_sentence(sentence):
    stopwords = ['the', 'a', 'an', 'at', 'of', 'to', 'in', 'on']
    words = sentence.lower().split()
    clean_words = [word for word in words if word not in stopwords]
    return ' '.join(clean_words)


def _list_exits_from(game, location):
    return sorted(location['exits'].keys())


def _list_objects_in(game, location):
    entities = game["entities"]

    objects_here = sorted([entity for entity in entities
                           if entity["type"] == "object" and entity
                           ["position"] == location["name"]])

    return objects_here


### game actions ###


def help():
    print(dedent('''
    Type your instructions using one or two words, for example:

    > look
    > take $object
    > look at $object
    > inventory
    > go north
    > drop $object
    > ?
    '''))


def take(game, entity):
    player = _get_entity_by_type(game, 'player')

    if entity.get('type') != 'object' or entity.get(
            'position') != player['position']:
        print("You can't take that.")
        return

    entity['position'] = 'player'
    print("Taken!")


def drop(game, entity):
    player = _get_entity_by_type(game, 'player')

    if entity.get('type') != 'object' or entity.get('position') != 'player':
        print("You can't drop that.")
        return

    entity['position'] = player['position']
    print("Dropped!")


def go(game, direction):
    player = _get_entity_by_type(game, 'player')
    player_position = _get_entity_by_name(game, player['position'])

    new_position_name = player_position['exits'].get(direction)

    if new_position_name is None:
        print("You can't go there.")
        return

    new_position = _get_entity_by_name(game, new_position_name)

    if new_position is None or len(new_position) == 0:
        new_position = generate_position(game, new_position_name)
        game['entities'].append(new_position)

    player['position'] = new_position_name
    print(fill(new_position['long_description']))



def _look_around(game):
    player = _get_entity_by_type(game, 'player')
    player_position = _get_entity_by_name(game, player['position'])

    print(fill(player_position['long_description']))
    print("I see here:")

    if not player_position["seen"]:
        # special case: this room was just created
        player_position["seen"] = True
        new_object = create_object(game, player_position['name'])
        if len(new_object):
            game['entities'].append(new_object)

    objects_here = _list_objects_in(game, player_position)

    if objects_here:
        print("; ".join(obj['short_description'] for obj in objects_here))
    else:
        print("Nothing special.")

    print("")
    print("Exits: ", "; ".join(_list_exits_from(game, player_position)))


def _look_object(game, obj):
    entities = game['entities']
    player = _get_entity_by_type(game, 'player')

    for e in entities:
        if e.get('name') == obj['name'] and (
                e['position'] == player['position'] or
                e['position'] == 'player'):
            print(obj['long_description'])
            return

    print("I can't see that.")


def look(game, obj=None):
    if obj is None:
        _look_around(game)
    else:
        _look_object(game, obj)


def inventory(game):
    objects = [e for e in game['entities'] if e['type']
               == 'object' and e['position'] == 'player']

    print("You are carrying:")

    if objects:
        print("; ".join(sorted([obj['short_description'] for obj in objects])))
    else:
        print("Nothing special.")


if __name__ == '__main__':
    game = generate_world(GAME_TEMPLATE)

    player = _get_entity_by_type(game, 'player')
    current_location = _get_entity_by_name(game, player['position'])

    print(game['_title'])
    print("")
    print(fill(game['_plot']))

    help()

    # define a dictionary to map verbs to functions
    VERB_TO_FUNCTION = {
        'quit': lambda game: exit(),
        'look': lambda game, *objects: look(game, *objects),
        'inventory': lambda game: inventory(game),
        'go': lambda game, direction: go(game, direction),
        'take': lambda game, obj_name: take(game, obj_name),
        'drop': lambda game, obj_name: drop(game, obj_name),
        'help': lambda game: help(),
        'debug': lambda game: breakpoint(),
        '?': lambda game: print(game),
    }

    # main game loop
    while player['alive']:
        sentence = input("What do you want to do? ")
        verb, *object_names = _clean_sentence(sentence).split()
        print("")

        function = VERB_TO_FUNCTION.get(verb, None)

        if function is None or len(object_names) > 1:
            # LLM magic!!!
            game = magic_action(game, sentence)
            print("")
            continue

        entities = filter(
            None,
            [_get_entity_by_name(game, name) for name in object_names]
        )

        # special case: go <direction>
        if object_names and object_names[0] in [
                'north', 'south', 'east', 'west']:
            entities = object_names

        try:
            function(game, *entities)
        except Exception as e:
            print(e)
            print(game)

        print("")
