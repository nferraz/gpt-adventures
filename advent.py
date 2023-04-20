#!/usr/bin/env python3

import json
import openai
import os

from random import randint
from textwrap import dedent

GAME_TEMPLATE = {
    '_title': '$game_title',
    '_plot': '$game_plot',
    'entities': {
        'player': {
            'type': 'player',
            'class': '$class',
            'alive': True,
            'position': 'loc_01',
            'short_description': '$short_description',
            'long_description': '$long_description',
        },
        'loc_01': {
            'type': 'location',
            'exits': {
                'north': 'loc_02',
            },
            'short_description': '$short_description',
            'long_description': 'You are in a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
        },
        'obj_01': {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'position': 'player',
        },
        'obj_02': {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'position': 'loc_01',
        }
    },
}


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

    if (len(data) == 1):
        # LLM returned a nested dict with only one key;
        # we want the next level dict
        first_key = list(data.keys())[0]
        return data[first_key]

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
    game["entities"][game["entities"]["player"]["position"]]["seen"] = True

    for key in game['entities']:
        entity = game['entities'][key]
        if entity.get('name'):
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
    structure corresponding to the new location (without the "{0}" key).

    INPUT:

    {1}

    OUTPUT:
    '''.format(
        position,
        json.dumps(game))

    data = _generate_content(prompt, 'location')
    data['seen'] = False

    return data


def create_object(game, position):
    prompt = '''
    You are a software agent. You will receive JSON and output JSON.

    Given this json data structure that represents a text-adventure game,
    please create a new entity of type "object" in the position "{0}".

    Populate this new object with all necessary attributes, including a
    single-word name and rich descriptions, following the same atmosphere
    of the game.

    Don't return the complete game JSON. Return the JSON for the data
    structure corresponding to the new object (without the "obj_" key).

    INPUT:

    {1}

    OUTPUT:
    '''.format(
        position,
        json.dumps(game))

    data = _generate_content(prompt, 'object')

    return data


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

    Return the complete JSON data structure below.

    OUTPUT:
    '''.format(
        json.dumps(game),
        sentence)

    game = _generate_content(prompt, 'action')

    if 'output' in game:
        print(game['output'])
        del game['output']

    return game


### auxiliar functions ###


def _clean_sentence(sentence):
    stopwords = ['the', 'a', 'an', 'at', 'of', 'to', 'in', 'on']
    words = sentence.lower().split()
    clean_words = [word for word in words if word not in stopwords]
    return ' '.join(clean_words)


def _list_exits_from(game, position):
    exits = game["entities"][position]["exits"]
    return sorted(exits.keys())


def _list_objects_in(game, position):
    entities = game["entities"]

    objects_here = sorted(
        [key for key, entity in entities.items()
         if entity["type"] == "object" and entity["position"] == position]
    )

    if not objects_here and not entities[position]["seen"]:
        entities[position]["seen"] = True
        new_object = create_object(game, position)
        new_key = f"obj_{randint(0,99):02}"
        if new_key not in entities:
            entities[new_key] = new_object
            return [new_key]

    return objects_here


def _short_description(game, entity_name):
    return game["entities"][entity_name]["short_description"]


def _long_description(game, entity_name):
    return game["entities"][entity_name]["long_description"]


### game actions ###


def help():
    print(dedent('''
    Type your instructions using one or two words, for example:

    > look
    > take $object
    > inventory
    > go north
    > drop $object
    '''))


def take(game, obj_name):
    entities = game['entities']
    player_position = entities['player']['position']

    object_to_handle = None

    for key, value in entities.items():
        if value.get('type') == 'object' and value.get(
                'name') == obj_name and value.get('position') == player_position:
            object_to_handle = key
            break

    if not object_to_handle:
        print("You can't take that.")
        return

    entities[object_to_handle]['position'] = 'player'
    print("Taken!")


def drop(game, obj_name):
    entities = game['entities']
    player_position = entities['player']['position']

    object_to_handle = None

    for key, value in entities.items():
        if value.get('type') == 'object' and value.get(
                'name') == obj_name and value.get('position') == 'player':
            object_to_handle = key
            break

    if not object_to_handle:
        print("You are not carrying that.")
        return

    entities[object_to_handle]['position'] = player_position
    print("Dropped!")


def go(game, direction):
    entities = game['entities']
    player_position = entities['player']['position']

    new_position = entities[player_position]['exits'].get(direction)

    if new_position is None:
        print("You can't go there.")
        return

    if entities.get(new_position) is None or len(entities[new_position]) == 0:
        entities[new_position] = generate_position(game, new_position)

    entities['player']['position'] = new_position
    print(_long_description(game, new_position))


def _look_around(game, player_position):
    objects = _list_objects_in(game, player_position)

    print(_long_description(game, player_position))
    print("I see here:")

    if objects:
        print("; ".join([_short_description(game, obj)
              for obj in objects if obj != 'player']))
    else:
        print("Nothing special.")

    print("")
    print("Exits: ", "; ".join(_list_exits_from(game, player_position)))


def _look_object(game, obj_name):
    entities = game['entities']
    player_position = entities['player']['position']

    for obj_key in entities.keys():
        if entities[obj_key].get('name') == obj_name and (
                entities[obj_key]['position'] ==
                player_position or entities[obj_key]['position'] == 'player'):
            print(_long_description(game, obj_key))
            break


def look(game, obj_name=None):
    if obj_name is None:
        _look_around(game, game['entities']['player']['position'])
    else:
        _look_object(game, obj_name)


def inventory(game):
    objects = _list_objects_in(game, 'player')
    print("You are carrying:")

    if objects:
        print("; ".join([_short_description(game, obj) for obj in objects]))
    else:
        print("Nothing special.")


if __name__ == '__main__':
    game = generate_world(GAME_TEMPLATE)

    print(game['_title'])
    print("")
    print(game['_plot'])
    print("")
    print(_long_description(game, game['entities']['player']['position']))

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
        '?': lambda game: print(game),
    }

    # main game loop
    while game['entities']['player']['alive']:
        sentence = _clean_sentence(input("What do you want to do? "))
        verb, *objects = sentence.split()
        function = VERB_TO_FUNCTION.get(verb, None)

        if function is None:
            # LLM magic!!!
            game = magic_action(game, sentence)
            print("")
            continue

        try:
            function(game, *objects)
        except Exception as e:
            print(e)
            print(game)

        print("")
