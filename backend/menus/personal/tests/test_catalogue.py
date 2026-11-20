import copy
import datetime
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, SimpleTestCase
from menus.features.schema import FEATURE_KEYS, MODEL_LABELS, FEATURE_VERSION
from menus.features import extractor
from menus.models import Food, MenuItem, Restaurant, SalesMenu
from menus.features.daily import annotate, PROMPT_SHA256
from menus.personal.catalog import canonical_foods
from menus.personal import mapping_import
from menus.personal.offers import candidates
from menus.services import SalesLine, get_catalog
from menus.allergens import ALLERGEN_VERSION
from menus.menu_profiles import offer_key
from question_engines.rl import RLEngine
from question_engines.group import GroupEngine
from menus.services import get_feature_schema


def line(name,menu,pk=1,allergens=(),version=ALLERGEN_VERSION):
    return SalesLine(pk,pk,name,37.48,126.95,'LU',menu,'',7000,pk,list(allergens),version,'place-'+str(pk))

class MappingTests(SimpleTestCase):
    def index(self, rows, key='food_003'):
        return {offer_key('general',r.restaurant_code,r.raw_name,r.description):key for r in rows}

    def test_fixed_catalogue_and_dropped_categories(self):
        self.assertEqual(len(canonical_foods()),267)
        self.assertEqual(len(FEATURE_KEYS),53)
        self.assertEqual(len(set(MODEL_LABELS)),53)
        self.assertTrue({'덮밥','두부요리','콘치즈','국'}.isdisjoint({r['name'] for r in canonical_foods().values()}))

    def test_different_variants_share_one_candidate_with_actual_names_and_prices(self):
        rows=[line('One','Cheese pizza',1),line('Two','Pineapple pizza',2)]
        result=candidates(rows,frozenset(),self.index(rows))
        self.assertEqual(len(result),1);self.assertEqual(result[0]['name'],'피자')
        self.assertEqual({o['menu_name'] for o in result[0]['offers']},{r.raw_name for r in rows})
        self.assertEqual({o['restaurant_code'] for o in result[0]['offers']},{'place-1','place-2'})

    def test_source_import_exact_match_precedes_format_fallback(self):
        import tempfile,csv
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.csv'
            with path.open('w', encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(['식당명','기존 음식명','정규화 음식명'])
                writer.writerows([['Shop','[점심]Pizza','피자'],['Shop','Pizza','NULL'],['Shop','덮밥','덮밥']])
            index=mapping_import.load(path)
            self.assertEqual(mapping_import.resolve(index,'Shop','[점심]Pizza'),'food_003')
            self.assertIsNone(mapping_import.resolve(index,'Shop','Pizza'))
            self.assertIsNone(mapping_import.resolve(index,'Shop','[저녁]Pizza'))
            self.assertIsNone(mapping_import.resolve(index,'Shop','덮밥'))
            self.assertIsNone(mapping_import.resolve(index,'Other','[점심]Pizza'))

    def test_allergies_are_per_sales_offer_not_canonical_category(self):
        rows=[line('One','Pizza',1,['milk']),line('Two','Pizza',2,[])]
        result=candidates(rows,frozenset({'milk'}),self.index(rows))
        self.assertEqual([o['restaurant_code'] for o in result[0]['offers']],['place-2'])
        rows[1]=line('Two','Pizza',2,[],version='')
        self.assertEqual(candidates(rows,frozenset({'milk'}),self.index(rows)),[])

    def test_new_schema_runs_in_DT_group_without_RL(self):
        rows=[]
        for i,food in enumerate(list(canonical_foods().values())[:3]):
            rows.append(copy.deepcopy(food)|{'offers':[{'restaurant':'Hall '+str(i),'lat':37.,'lng':127.,'meal':'LU','price':5000}]})
        engine=GroupEngine(rows,get_feature_schema(),[set(),set()],config={'max_rounds':2})
        while not engine.finished:
            for i,q in engine.questions().items():engine.answer(i,q['question_id'],'yes')
        self.assertTrue(engine.recommendation()['picks'])

class WholeCampusTests(TestCase):
    def setUp(self):
        self.day=datetime.date(2026,11,17)
        self.hall=Restaurant.objects.create(code='hall',name='Hall')
        for name in ['돈까스','우동']:
            f=Food.objects.create(name=name,is_food=True)
            MenuItem.objects.create(date=self.day,meal='LU',restaurant=self.hall,raw_name='돈까스+우동',food=f,price=6000)

    def test_direct_whole_menu_extraction_and_prompt_version_cache(self):
        stats={key:{'mean':.5,'std':.1,'mask':True} for key in FEATURE_KEYS}
        stats['octopus']={'mean':None,'std':None,'mask':False}
        client=mock.Mock()
        def reply(messages):
            import json
            items=json.loads(messages[-1].content)['items']
            return {'items':[{'input_name':i['input_name'],'features':stats} for i in items]}
        client.invoke.side_effect=reply
        failed,count=annotate(self.day,lambda:client)
        self.assertEqual((failed,count),(set(),1));self.assertEqual(client.invoke.call_count,1)
        profile=SalesMenu.objects.get(source='cafeteria',feature_version=FEATURE_VERSION)
        self.assertEqual(profile.feature_version,FEATURE_VERSION)
        self.assertIsNone(profile.features['octopus'])
        self.assertEqual(profile.annotation_metadata['prompt_sha256'],PROMPT_SHA256)
        self.assertEqual(len(get_catalog(self.day)[0]),1)
        annotate(self.day,lambda:(_ for _ in ()).throw(AssertionError('Cache miss')))
        profile.annotation_metadata['prompt_sha256']='old';profile.save()
        annotate(self.day,lambda:client);self.assertEqual(client.invoke.call_count,2)

    def test_old_feature_rows_are_not_current(self):
        for f in Food.objects.all():f.features={};f.feature_version='v2';f.save()
        self.assertEqual(get_catalog(self.day)[0],[])
        failed,count=annotate(self.day,lambda:None)
        self.assertEqual(count,0);self.assertTrue(failed)

    def test_mask_requires_consistent_nulls_and_known_zero_is_known(self):
        self.assertFalse(extractor.FeatureStats(mean=None,std=None,mask=False).mask)
        self.assertTrue(extractor.FeatureStats(mean=0,std=0,mask=True).mask)
        with self.assertRaises(ValueError):extractor.FeatureStats(mean=.2,std=.1,mask=False)

class BilingualQuestionTests(SimpleTestCase):
    def test_all_53_questions_match_the_authored_Korean_and_English(self):
        import json
        from pathlib import Path
        from question_engines.decision_tree.contracts import FEATURE_PRESENTATION, translate
        source=json.loads((Path(__file__).parents[3]/'question_engines/rl/assets/questions.json').read_text(encoding='utf-8'))['questions']
        for key,expected in zip(FEATURE_KEYS,source):
            text=FEATURE_PRESENTATION[key][0]
            self.assertEqual(text,expected['en'])
            self.assertEqual(translate(text,'ko'),expected['ko'])

    def test_group_questions_use_the_same_new_text_in_both_languages(self):
        from question_engines.decision_tree.contracts import FEATURE_PRESENTATION, translate
        rows=[]
        for i,food in enumerate(list(canonical_foods().values())[:4]):
            rows.append(copy.deepcopy(food)|{'offers':[{'restaurant':'Hall '+str(i),'lat':37.,'lng':127.,'meal':'LU','price':5000}]})
        for language in ['en','ko']:
            engine=GroupEngine(rows,get_feature_schema(),[set(),set()],config={'language':language})
            self.assertTrue(engine.questions())
            for question in engine.questions().values():
                key=question['question_id'][2:]
                self.assertEqual(question['text'],translate(FEATURE_PRESENTATION[key][0],language))

class WholeMenuIdentityTests(TestCase):
    def test_same_title_at_lunch_and_dinner_keeps_different_compositions(self):
        hall=Restaurant.objects.create(code='meal',name='Hall')
        day=datetime.date(2026,11,17)
        for meal,name in [('LU','비빔국수'),('DN','제육볶음')]:
            food=Food.objects.create(name=name,is_food=True)
            MenuItem.objects.create(restaurant=hall,date=day,meal=meal,raw_name='오늘의 메뉴',food=food,price=5000)
        client=mock.Mock()
        def reply(messages):
            import json
            rows=json.loads(messages[-1].content)['items']
            return {'items':[{'input_name':row['input_name'],'features':{k:{'mean':.2 if '비빔국수' in row['input_name'] else .8,'std':.1,'mask':True} for k in FEATURE_KEYS}} for row in rows]}
        client.invoke.side_effect=reply
        failed,count=annotate(day,lambda:client)
        self.assertFalse(failed);self.assertEqual(count,2)
        lunch=get_catalog(day,'LU')[0][0];dinner=get_catalog(day,'DN')[0][0]
        self.assertNotEqual(lunch['food_id'],dinner['food_id'])
        self.assertNotEqual(lunch['features'],dinner['features'])

class GroupSalesVariantTests(TestCase):
    def test_same_category_at_one_place_returns_only_the_members_safe_variant(self):
        from menus import services
        from menus.personal import offers
        import json
        services._store_menus=None;self.addCleanup(setattr,services,'_store_menus',None)
        shop=Restaurant.objects.create(code='variants',name='One place',source='naver',lat=37.48,lng=126.95)
        for name,tags in [('Cheese pizza',['milk']),('No cheese pizza',[])]:
            from menus.models import StoreMenu
            StoreMenu.objects.create(restaurant=shop,raw_name=name,allergens=tags,allergen_version=ALLERGEN_VERSION,price=9000)
        def post(path,body=None,token=None):
            return self.client.post(path,data=json.dumps(body or {}),content_type='application/json',**({'HTTP_X_MEMBER_TOKEN':token} if token else {}))
        with mock.patch.object(offers,'resolve',return_value='food_003'):
            created=post('/api/rooms/',{'name':'Host','source':'general'}).json()
            code=created['state']['code'];host=created['token']
            joined=post('/api/rooms/join/',{'code':code,'name':'Member','allergies':['milk']}).json()
            response=post(f'/api/rooms/{code}/start/',token=host)
            self.assertEqual(response.status_code,200,response.content)
            state=response.json();self.assertEqual(state['status'],'done')
            pick=state['picks'][0]
            mine=next(row for row in pick['menus'] if row['member_id']==joined['state']['me'])['food']
            self.assertEqual(mine['display_name'],'No cheese pizza')
            self.assertEqual([o['menu_name'] for o in mine['offers']],['No cheese pizza'])
