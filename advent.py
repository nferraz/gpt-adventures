#!/usr/bin/env python3

import json
import openai
import os
import pdb
import re

from random import randint
from textwrap import dedent, fill

GPT_MODEL = os.environ.get('GPT_MODEL', 'text-davinci-003')

GAME_TEMPLATE = {
    '_title': '$game_title',
    '_genre': '$game_genre',
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
            'location': '$location1_name',
            'short_description': 'a $short_description',
            'long_description': 'You are $long_description',
        },
        {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'location': 'player',
        },
        {
            'type': 'object',
            'short_description': 'a $short_description',
            'long_description': 'It\'s a $long_description',
            'name': '$single_word',
            'adjective': '$single_word',
            'location': '$location1_name',
        },
    ],
}


def DEBUG(*msg):
    if os.environ.get('DEBUG'):
        print("\x1b[90m", *msg, "\x1b[0m")


def DEBUG2(*msg):
    if int(os.environ.get('DEBUG', '0')) > 1:
        print("\x1b[90m", *msg, "\x1b[0m")


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


def _completion(prompt):
    if GPT_MODEL == 'text-davinci-003':
        res = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=2048,
        )
        return res.choices[0].text
    elif GPT_MODEL == 'gpt-3.5-turbo':
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system",
                       "content":
                       "You are a software agent. You output will be strict JSON, with no indentation."},
                      {"role": "user", "content": prompt}],)
        return res.choices[0].message.content
    else:
        raise Exception('Invalid GPT model')


def _generate_content(prompt, str_type):
    print(f"# Generating {str_type}...")
    prompt = dedent(prompt).lstrip()

    DEBUG2(prompt)

    json_str = None
    try:
        json_str = _completion(prompt)
    except BaseException:
        print(prompt)
        raise

    # fix malformed json
    json_str = re.sub(r',\s*}', '}', json_str)

    DEBUG2(json_str)

    try:
        data = json.loads(json_str)
    except BaseException:
        print('Error parsing JSON: ' + json_str)
        raise

    return data


def generate_world(game):
    prompt = """
    Given this json data structure that represents a text-adventure game,
    please replace all variables starting with a dollar sign (`$`) with
    rich descriptions.

    INPUT:

    $json

    OUTPUT (strict json):
    """

    json_str = json.dumps(game)
    prompt = prompt.replace("$json", json_str)

    game = _generate_content(prompt, 'game')
    DEBUG(game)

    player = _get_entity_by_type(game, "player")

    # mark initial location as seen
    player_location = _get_entity_by_name(game, player['location'])
    player_location["seen"] = True

    # make sure all object names are lowercase
    for entity in game['entities']:
        if entity.get('type', '') == 'object':
            entity['name'] = entity['name'].lower()

    return game


def generate_location(game, location):
    player = _get_entity_by_type(game, "player")

    prompt = '''
    Given this json data structure that represents a text-adventure game,
    please create a new entity of type "location", named "{0}".

    Populate this new location with all necessary attributes, including
    rich new descriptions, following the same atmosphere of the previous
    locations.

    Most locations in the game should have at least two exits (usually
    "north", "south", "east" or "west"; sometimes "up" or "down"); and
    each exit should have a distinct name. One exit should go back to
    "{1}".

    Don't return the complete game JSON. Return the JSON for the data
    structure corresponding to the new entity.

    INPUT:

    {2}

    OUTPUT (strict json):
    '''.format(
        location,
        player['location'],
        json.dumps(game))

    location = _generate_content(prompt, 'location')
    location['seen'] = False

    return location


def create_object(game, location):
    prompt = '''
    Given this json data structure that represents a text-adventure game,
    please create a new entity of type "object" in the location "{0}".

    Populate this new object with all necessary attributes, including a
    single-word name and rich descriptions, following the same atmosphere
    of the game.

    Make sure that the short description contains the object name.

    Don't return the complete game JSON. Return the JSON for the data
    structure corresponding to the new entity.

    INPUT:

    {1}

    OUTPUT (strict json):
    '''.format(
        location,
        json.dumps(game))

    obj = _generate_content(prompt, 'object')

    return obj


def magic_action(game, sentence):

    game['output'] = '$output'

    prompt = '''
    Given this json data structure that represents a text-adventure game:

    {0}

    The user typed the following command: "{1}".

    Consider the player class and the game context to see if the action
    can be performed.

    Replace the "output" value with a description of the action result, and
    modify the data structure reflecting any changes.

    Some important points to consider:

    1) Embrace creativity: Encourage your players to think outside the box
    and reward them for their creativity.

    2) While it's important to be flexible, it's also important to ensure
    that the game world remains consistent.

    3) Consider the consequences: Every action has consequences, both
    intended and unintended.

    If the action can be performed, modify the game properties as
    necessary to reflect the changes caused by this action. You may
    change player attributes, objects, and locations as necessary.

    No matter what, return the complete JSON data structure for the game
    including the "output" explaining what happened.

    OUTPUT (strict json):
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
                           ["location"] == location["name"]])

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
            'location') != player['location']:
        print("You can't take that.")
        return

    entity['location'] = 'player'
    print("Taken!")


def drop(game, entity):
    player = _get_entity_by_type(game, 'player')

    if entity.get('type') != 'object' or entity.get('location') != 'player':
        print("You can't drop that.")
        return

    entity['location'] = player['location']
    print("Dropped!")


def go(game, direction):
    player = _get_entity_by_type(game, 'player')
    player_location = _get_entity_by_name(game, player['location'])

    new_location_name = player_location['exits'].get(direction)

    if new_location_name is None:
        print("You can't go there.")
        return

    new_location = _get_entity_by_name(game, new_location_name)

    if new_location is None or len(new_location) == 0:
        new_location = generate_location(game, new_location_name)
        game['entities'].append(new_location)

    player['location'] = new_location_name
    print(fill(new_location['long_description']))


def _look_around(game):
    player = _get_entity_by_type(game, 'player')
    player_location = _get_entity_by_name(game, player['location'])

    print(fill(player_location['long_description']))
    print("")
    print("I see here:")

    if not player_location["seen"]:
        # special case: this room was just created
        player_location["seen"] = True
        new_object = create_object(game, player_location['name'])
        if len(new_object):
            game['entities'].append(new_object)

    objects_here = _list_objects_in(game, player_location)

    if objects_here:
        print("; ".join(obj['short_description'] for obj in objects_here))
    else:
        print("Nothing special.")

    print("")
    print("Exits: ", "; ".join(_list_exits_from(game, player_location)))


def _look_object(game, obj):
    entities = game['entities']
    player = _get_entity_by_type(game, 'player')

    for e in entities:
        if e.get('name') == obj['name'] and (
                e['location'] == player['location'] or
                e['location'] == 'player'):
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
               == 'object' and e['location'] == 'player']

    print("You are carrying:")

    if objects:
        print("; ".join(sorted([obj['short_description'] for obj in objects])))
    else:
        print("Nothing special.")


if __name__ == '__main__':
    game = generate_world(GAME_TEMPLATE)

    player = _get_entity_by_type(game, 'player')
    current_location = _get_entity_by_name(game, player['location'])

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
