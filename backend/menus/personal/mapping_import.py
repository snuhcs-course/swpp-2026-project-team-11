"""Read an operator-supplied map for import, never on a recommendation request."""
import csv
import re
from .catalog import canonical_foods

DROPPED = {'덮밥', '두부요리', '콘치즈', '국'}

def format_key(name):
    return re.sub(r'[\s_]+', '', re.sub(r'\[[^\]]*\]', '', name))


def load(path):
    names = {row['name']: key for key, row in canonical_foods().items()}
    exact, formatted = {}, {}
    with path.open(encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        if not {'식당명', '기존 음식명', '정규화 음식명'} <= set(reader.fieldnames or ()):
            raise ValueError('Missing mapping columns')
        for row in reader:
            owner, title, target = row['식당명'], row['기존 음식명'], row['정규화 음식명']
            if not owner.strip() or not title.strip():
                raise ValueError('Restaurant and original menu must not be empty')
            if target not in names and target not in DROPPED | {'NULL', ''}:
                raise ValueError(f'Unknown canonical name: {target}')
            value = names.get(target)
            key = owner, title
            if key in exact and exact[key] != value:
                raise ValueError('Conflicting exact menu mapping')
            exact[key] = value
            formatted.setdefault((owner, format_key(title)), set()).add(value)
    if not exact:
        raise ValueError('Empty menu mapping')
    return exact, formatted


def resolve(index, restaurant, raw_name):
    exact, formatted = index
    if (restaurant, raw_name) in exact:
        return exact[restaurant, raw_name]
    matches = formatted.get((restaurant, format_key(raw_name)), set())
    return next(iter(matches)) if len(matches) == 1 else None
