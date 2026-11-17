"""Personal and group sources use the same new 53-feature catalogue."""
import datetime
import threading
from unittest import mock
from django.test import TestCase, override_settings
from menus import services
from menus.allergens import ALLERGEN_VERSION
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant, StoreMenu
from menus.personal.catalog import canonical_foods
from menus.personal import offers
from recommend import sessions
from .helpers import post

class GeneralSourceTests(TestCase):
    def setUp(self):
        services._store_menus=None
        self.addCleanup(setattr,services,'_store_menus',None)
        self.lookup={'Pizza A':'food_003','Pizza B':'food_003','Kimchi':'food_009','Unknown':None}
        patch=mock.patch.object(offers,'resolve',side_effect=lambda restaurant,title:self.lookup.get(title))
        patch.start();self.addCleanup(patch.stop)
        self.near=Restaurant.objects.create(code='near',name='Near',lat=37.48,lng=126.95,source='naver')
        self.far=Restaurant.objects.create(code='far',name='Far',lat=37.6,lng=127.1,source='naver')
        for restaurant,title,tags in [(self.near,'Pizza A',['milk']),(self.far,'Pizza B',[]),(self.near,'Kimchi',[]),(self.near,'Unknown',[])]:
            StoreMenu.objects.create(restaurant=restaurant,raw_name=title,allergens=tags,allergen_version=ALLERGEN_VERSION,price=7000)
        f=Food.objects.create(name='Campus',is_food=True,feature_version=FEATURE_VERSION,features=dict.fromkeys(FEATURE_KEYS,.5),feature_std=dict.fromkeys(FEATURE_KEYS,.1),allergen_version=ALLERGEN_VERSION)
        self.campus=Restaurant.objects.create(code='hall',name='Hall',lat=37.48,lng=126.95)
        MenuItem.objects.create(date=datetime.date(2026,11,2),meal='LU',restaurant=self.campus,raw_name='Campus',food=f,price=5000)

    def start(self,**extra):
        response=post(self.client,'/api/sessions/',{'date':'2026-11-02','meal':'LU','source':'general'}|extra)
        self.assertEqual(response.status_code,201,response.content);return response.json()

    def test_one_candidate_per_type_and_unknown_mapping_excluded(self):
        rows,schema=services.get_store_catalog('LU')
        self.assertEqual(len(rows),2);self.assertEqual(len(schema),53)
        pizza=next(r for r in rows if r['name']=='피자')
        self.assertEqual(len(pizza['offers']),2)
        self.assertEqual({r['menu_name'] for r in pizza['offers']},{'Pizza A','Pizza B'})
        self.assertEqual(self.start()['candidate_count'],2)

    def test_allergy_filter_precedes_grouping(self):
        rows,_=services.get_store_catalog('LU',frozenset({'milk'}))
        pizza=next(r for r in rows if r['name']=='피자')
        self.assertEqual([o['restaurant'] for o in pizza['offers']],['Far'])
        StoreMenu.objects.filter(raw_name='Pizza B').update(allergen_version='')
        services._store_menus=None
        self.assertEqual([r['name'] for r in services.get_store_catalog('LU',frozenset({'milk'}))[0]],['김치찌개'])

    def test_both_sources_compete_in_DT_and_RL_and_ids_do_not_collide(self):
        for engine in ['decision_tree','rl']:
            state=self.start(source='all',engine=engine)
            self.assertEqual(state['candidate_count'],3)
            s=sessions.get(state['session_id']);ids=[r for r in s.reason_data]
            self.assertEqual(len(set(ids)),3)

    def test_distance_filter_keeps_only_available_reverse_references(self):
        state=self.start(source='all',distance_scope='near',location={'lat':37.48,'lng':126.95})
        s=sessions.get(state['session_id']);rows=list(s.engine._foods) if hasattr(s.engine,'_foods') else list(s.engine.catalog.candidates)
        for row in rows:
            os=row['offers'] if isinstance(row,dict) else row.offers
            self.assertTrue(all(o['restaurant']!='Far' for o in os))

    @override_settings(RECOMMEND_STORE_MENU_CACHE_S=300)
    def test_each_meal_and_allergy_combination_is_built_once_and_copies_offers(self):
        with mock.patch.object(offers,'candidates',wraps=offers.candidates) as build:
            a,_=services.get_store_catalog('LU');a[0]['offers'].clear()
            b,_=services.get_store_catalog('LU')
            self.assertTrue(b[0]['offers']);self.assertEqual(build.call_count,1)
            services.get_store_catalog('DN');self.assertEqual(build.call_count,2)
            services.get_store_catalog('LU',frozenset({'egg'}));self.assertEqual(build.call_count,3)

    def test_prewarm_has_no_session_side_effect(self):
        before=len(sessions._sessions)
        response=post(self.client,'/api/sessions/prewarm/',{'meal':'LU','source':'all'})
        self.assertEqual(response.status_code,204);self.assertEqual(before,len(sessions._sessions))

    def test_rejecting_a_type_excludes_all_its_variants_and_undo_restores_it(self):
        s=sessions.get(self.start(engine='rl')['session_id']);s.recommend_now();before=s.public_state()['step']
        s.feedback(before['guess_id'],False);s.recommend_now();after=s.public_state()['step']
        self.assertNotEqual(before['food']['food_id'],after['food']['food_id'])
        while s.engine.can_undo:
            s.engine.undo()
            if s.engine.next_step()==before:break
        self.assertEqual(s.engine.next_step(),before)

    def test_mapped_menu_list_uses_actual_sales_names(self):
        s=sessions.get(self.start()['session_id'])
        names={d['display_name'] for d in s.menu('Near')['dishes']}
        self.assertEqual(names,{'Pizza A','Kimchi'})
