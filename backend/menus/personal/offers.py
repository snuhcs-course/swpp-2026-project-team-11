"""One canonical candidate per surviving type, retaining actual sales offers."""
import copy
from collections import defaultdict
from menus.allergens import ALLERGEN_VERSION
from .catalog import canonical_foods
from menus.menu_profiles import offer_key
from menus.models import SalesMenu

MAPPING_VERSION = "canonical.1"

def mapping_index():
    return {key:metadata.get("canonical_id") for key,metadata in
            SalesMenu.objects.filter(source="general", annotation_metadata__mapping_version=MAPPING_VERSION)
            .values_list("key", "annotation_metadata")}

def resolve(row, mappings):
    return mappings.get(offer_key("general", row.restaurant_code, row.raw_name, row.description))


def candidates(records, allergies, mappings=None):
    mappings = mapping_index() if mappings is None else mappings
    grouped=defaultdict(list)
    for row in records:
        grouped[row.restaurant_id,row.raw_name,row.description,row.price].append(row)
    catalog=canonical_foods();result={}
    for rows in grouped.values():
        row=rows[0]
        if allergies and any(r.allergen_version!=ALLERGEN_VERSION or not allergies.isdisjoint(r.allergens) for r in rows):continue
        key=resolve(row,mappings)
        if key not in catalog:continue
        candidate=result.setdefault(key,copy.deepcopy(catalog[key])|{'offers':[]})
        offer={'restaurant':row.restaurant,'meal':row.meal,'price':row.price,'lat':row.lat,'lng':row.lng,
               'menu_name':row.raw_name,'restaurant_code':row.restaurant_code}
        if offer not in candidate['offers']:candidate['offers'].append(offer)
    return sorted(result.values(),key=lambda c:c['food_id'])
