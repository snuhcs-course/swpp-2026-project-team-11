"""Annotate complete campus sales menus with the user-authored 53-feature rubric."""
from collections import defaultdict
import hashlib

from django.utils import timezone
from menus.models import MenuItem, SalesMenu
from menus.menu_profiles import campus_key, description_digest, digest
from . import extractor
from .prompt import SYSTEM_PROMPT
from .schema import FEATURE_VERSION

PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()


def annotate(day, client_factory=None, batch_size=8):
    groups=defaultdict(list)
    for item in MenuItem.objects.filter(date=day).select_related('food','restaurant').order_by('id'):
        groups[item.restaurant_id,item.raw_name,item.meal].append(item)
    pending={};failed=set();complete=0
    for identity,items in groups.items():
        item=items[0]
        if any(i.food is None or not i.food.is_food for i in items):
            failed.add(identity);continue
        components=sorted({i.food.name for i in items})
        key=campus_key(item.restaurant.code,item.raw_name,item.meal,[i.food for i in items])
        composition=digest(components)
        profile=SalesMenu.objects.filter(key=key).first()
        if profile and profile.feature_version==FEATURE_VERSION and profile.annotation_metadata.get('prompt_sha256')==PROMPT_SHA256 and profile.annotation_metadata.get('composition')==composition:
            try:
                from menus.menu_profiles import validate_features
                validate_features(profile.features,profile.feature_std)
                complete+=1;continue
            except (ValueError,TypeError):pass
        label=item.raw_name+' — 구성: '+', '.join(components)
        pending.setdefault(label,[]).append((identity,item,key,components,composition))
    names=list(pending)
    if names:
        client=(client_factory or extractor.build_llm)()
        if client is None:
            failed.update(row[0] for values in pending.values() for row in values)
            return failed,complete
        results,missing=extractor.extract(names,client,batch_size=batch_size)
        for label in missing:failed.update(row[0] for row in pending[label])
        for label,annotation in results.items():
            values=annotation.features.model_dump()
            for identity,item,key,components,composition in pending[label]:
                SalesMenu.objects.update_or_create(key=key,defaults={
                    'source':'cafeteria','restaurant_code':item.restaurant.code,'name':item.raw_name,
                    'description_sha256':description_digest(''),
                    'features':{k:v['mean'] for k,v in values.items()},
                    'feature_std':{k:v['std'] for k,v in values.items()},'feature_version':FEATURE_VERSION,
                    'annotation_metadata':{'components':components,'composition':composition,
                                           'prompt_sha256':PROMPT_SHA256,'extracted_at':timezone.now().isoformat()}})
                complete+=1
    return failed,complete
