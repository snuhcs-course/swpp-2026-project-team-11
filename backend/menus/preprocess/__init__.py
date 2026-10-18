# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Daily menu preprocessing: which dishes does each cafeteria menu line stand for?

A raw line can be one dish ("육개장"), several dishes ("돈가스 카레우동"), or not a
meal at all ("공기밥", drinks). Lines are grouped by normalize.dish_key, so spacing
and size variants are the same line, and each line is resolved once and cached in
menus.MenuLine. See mapper.map_lines for the order the sources are consulted in.
"""
