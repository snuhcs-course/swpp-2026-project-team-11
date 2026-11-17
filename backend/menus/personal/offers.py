"""One canonical candidate per surviving type, retaining actual sales offers."""
import copy
from collections import defaultdict
from menus.allergens import ALLERGEN_VERSION
from .catalog import canonical_foods, resolve


def candidates(records, allergies):
    grouped=defaultdict(list)
    for row in records:
        grouped[row.restaurant_id,row.raw_name,row.description,row.price].append(row)
    catalog=canonical_foods();result={}
    for rows in grouped.values():
        row=rows[0]
        if allergies and any(r.allergen_version!=ALLERGEN_VERSION or not allergies.isdisjoint(r.allergens) for r in rows):continue
        key=resolve(row.restaurant,row.raw_name)
        if key is None:continue
        candidate=result.setdefault(key,copy.deepcopy(catalog[key])|{'offers':[]})
        offer={'restaurant':row.restaurant,'meal':row.meal,'price':row.price,'lat':row.lat,'lng':row.lng,
               'menu_name':row.raw_name,'restaurant_code':row.restaurant_code}
        if offer not in candidate['offers']:candidate['offers'].append(offer)
    return sorted(result.values(),key=lambda c:c['food_id'])
