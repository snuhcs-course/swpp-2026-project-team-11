from pathlib import Path
from dotenv import dotenv_values
REPO = Path(__file__).resolve().parents[2]
def load_config():
    return {k:v for k,v in dotenv_values(REPO / '.env').items() if v is not None}
"""Daily campus-menu writer for the mini PC; never opens Supabase. Called under a Windows boot-independent task."""
import argparse,contextlib,datetime,hashlib,json,logging,os,sqlite3,sys,tempfile,time,traceback
from pathlib import Path
from collections import defaultdict,Counter
from zoneinfo import ZoneInfo
KST=ZoneInfo('Asia/Seoul')
def now():return datetime.datetime.now(KST)
def status_file(path,data):
    tmp=path.with_suffix('.new')
    with tmp.open('w',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    tmp.replace(path)
@contextlib.contextmanager
def write_lock(root):
    f=(root/'state/catalog-writer.lock').open('a+b')
    try:
        if f.tell()==0:f.write(b'x');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:f.close()
class Budget:
    def __init__(self,root,cap,key):
        self.root=root;self.cap=cap;self.key=key;self.actual=0;self.model='google/gemini-3.5-flash'
        self.day=None;self.provider_error=None
    def rollover(self):
        day=now().date()
        if self.day!=day:
            self.path=self.root/'state'/('menu-model-'+day.isoformat()+'.json')
            self.used=json.loads(self.path.read_text())['used'] if self.path.is_file() else 0
            if type(self.used) is not int or self.used<0:raise RuntimeError('Invalid daily model call ledger')
            self.day=day
    @property
    def available(self):
        self.rollover()
        return bool(self.key) and self.provider_error is None and (self.cap is None or self.used<self.cap)
    def client(self,schema):
        if not self.available:return None
        from langchain_openai import ChatOpenAI
        model=ChatOpenAI(model=self.model,api_key=self.key,base_url='https://openrouter.ai/api/v1',timeout=75,max_retries=0)
        delegate=model.with_structured_output(schema,method='function_calling')
        budget=self
        class Client:
            def invoke(self,messages):
                if not budget.available:raise RuntimeError('Daily menu model limit')
                budget.used+=1;budget.actual+=1
                status_file(budget.path,{'used':budget.used,'as_of':now().isoformat()})
                try:
                    return delegate.invoke(messages)
                except Exception as error:
                    if getattr(error,'status_code',None) in (401,402,403,404,429):
                        budget.provider_error=type(error).__name__
                    raise
        return Client()
def fill_labels(day,budget):
    from menus.models import Food
    from menus import allergens
    group=defaultdict(list)
    for f in Food.objects.filter(is_food=True,menu_items__date=day).distinct():group[f.name].append(f)
    valid=lambda f:f.allergen_version==allergens.ALLERGEN_VERSION and isinstance(f.allergens,list) and set(f.allergens)<=set(allergens.ALLERGEN_KEYS)
    cache={}
    for f in Food.objects.filter(name__in=group):
        if valid(f):cache.setdefault(f.name,f.allergens)
    missing=sorted(group.keys()-cache.keys())
    if missing and (client:=budget.client(allergens.AllergenBatch)):
        values,_=allergens.extract(missing,client)
        cache.update({name:value.keys() for name,value in values.items()})
    bad=set()
    for name,variants in group.items():
        for f in variants:
            if name in cache and not valid(f):
                f.allergens=cache[name];f.allergen_version=allergens.ALLERGEN_VERSION
                f.save(update_fields=['allergens','allergen_version'])
            if not valid(f):bad.add(f.pk)
    return bad,{'uncached_allergens_before':len(missing),'unresolved_foods':sorted(set(group)-set(cache))}
def refresh(root,day,report,budget,label_tagging_enabled=False):
    from menus.sources import siksha, fixed_cafeterias
    from menus.management.commands.fetch_menus import menu_lines,store
    from menus.preprocess import mapper
    from menus.models import MenuItem
    from django.db import connection
    from django.db.models import Count
    records=[r for r in siksha.parse(siksha.fetch_days(day,day)) if r.date==day]
    report['raw_by_meal']=dict(Counter(r.meal for r in records))
    if not records:raise RuntimeError('No source records; serving database unchanged')
    records+=fixed_cafeterias.records(day)
    # The canonical mapper caches LLM and reviewed mappings. Its RULE result
    # is a provisional raw line and must never become a selectable dish.
    lines=menu_lines(records);report['distinct_clean_lines']=len(lines)
    maps=mapper.map_lines(lines,budget.client(mapper.LineBatch))
    pending=[lines[k] for k,v in maps.items() if v.source=='rule']
    safe={k:mapper.Mapping(False,(),'rule') if v.source=='rule' else v for k,v in maps.items()}
    report['unresolved_lines']=sorted(pending)
    day_q=MenuItem.objects.filter(date=day)
    fields=('meal','restaurant_id','raw_name','food_id')
    old={tuple(x[1:]):x[0] for x in day_q.values_list('pk',*fields)}
    store(day,records,safe)
    # These two Gusia board names denote rice bowls at this counter only.
    # The global mappings for other restaurants keep their original meaning.
    from menus.management.commands.fetch_menus import ensure_foods
    board_items=day_q.filter(restaurant__name='구시아푸드마켓>바비든든',raw_name__in=['고기든든','직화구이'])
    for raw_name,canonical in [('고기든든','삼겹살덮밥'),('직화구이','직화구이덮밥')]:
        matching=board_items.filter(raw_name=raw_name)
        if matching.exists():
            foods,_=ensure_foods({(canonical,False)})
            matching.update(food_id=foods[(canonical,False)].pk)
    from menus.menu_registry import register_menu_ids
    register_menu_ids('cafeteria',date=day,restaurant_ids=board_items.values_list('restaurant_id',flat=True).distinct())
    bad,feature_report=fill_labels(day,budget);report.update(feature_report)
    from menus.features.daily import annotate
    from menus.features.extractor import FoodBatch
    unresolved_profiles, profile_count = annotate(day, client_factory=lambda:budget.client(FoodBatch))
    report.update(campus_profiles=profile_count,unresolved_menu_profiles=len(unresolved_profiles))
    # Opt in only after approval of paid label extraction; use the existing daily call cap.
    if label_tagging_enabled and budget.available:
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from unittest.mock import patch
        from menus import labels, llm
        import io
        try:
            with patch.object(labels,'build_llm',return_value=budget.client(labels.LabelBatch)), patch.object(llm,'api_key_available',return_value=True):
                call_command('tag_menu_labels','--date',str(day),stdout=io.StringIO())
            report['menu_labels']='complete'
        except CommandError:
            report['menu_labels']='partial'
    else:report['menu_labels']='disabled_or_budget_exhausted'
    items=list(day_q.values_list('pk',*fields))
    unsafe={tuple(x[1:4]) for x in items if x[4] in bad}
    unsafe |= {tuple(x[1:4]) for x in items if (x[2],x[3],x[1]) in unresolved_profiles}
    hide=[x[0] for x in items if tuple(x[1:4]) in unsafe]
    if hide:day_q.filter(pk__in=hide).delete()
    # The canonical store() replaces today's rows. Retain existing IDs for
    # the same offer, including price corrections, across repeated refreshes.
    with connection.cursor() as c:
        c.executemany('UPDATE menus_menuitem SET id=%s WHERE id=%s',[(old[tuple(x[1:])],x[0]) for x in items if tuple(x[1:]) in old and tuple(x[1:4]) not in unsafe])
    counts=dict(day_q.values('meal').order_by().annotate(n=Count('food_id',distinct=True)).values_list('meal','n'))
    report.update(eligible_by_meal=counts,offers=day_q.count(),withheld_offers=len(unsafe))
    if not counts:raise RuntimeError('No verified menu; serving database unchanged')
    lost={k[0] for k in old}-set(counts)
    if lost:raise RuntimeError('Previously available meal disappeared; serving database unchanged: '+','.join(sorted(lost)))
    return 'partial' if pending or bad or unresolved_profiles else 'complete'
def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--date',type=datetime.date.fromisoformat);ap.add_argument('--root',type=Path,default=REPO/'.local/hosting');args=ap.parse_args()
    root=args.root.resolve();day=args.date or now().date()
    cfg=load_config()
    if cfg.get('DATABASE_URL'):raise RuntimeError('The API must serve the local catalogue before enabling the local writer')
    settings=root/'private/menu-refresh.json';opt=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
    cap=opt.get('paid_calls_per_kst_day',0)
    if cap is not None and (type(cap) is not int or cap<0):raise ValueError('Invalid daily model call limit')
    budget=None;live=root/'private/menu.sqlite3';report={'date':str(day),'started':now().isoformat(),'source':'siksha','machine':os.environ.get('COMPUTERNAME','local-test'),'paid_daily_cap':cap}
    with write_lock(root):
        try:
            budget=Budget(root,cap,cfg.get('OPENROUTER_API_KEY'))
            with tempfile.TemporaryDirectory(prefix='menu-refresh-',dir=root/'private') as tmp:
                stage=Path(tmp)/'stage.sqlite3'
                with contextlib.closing(sqlite3.connect(live.as_uri()+'?mode=ro',uri=True,timeout=30)) as reader,contextlib.closing(sqlite3.connect(stage)) as dst:
                    version=reader.execute('PRAGMA data_version').fetchone()[0]
                    reader.backup(dst)
                    release='checkout-main'
                    sys.path.insert(0,str(REPO/'backend'))
                    os.environ.update(DATABASE_URL='sqlite:///'+stage.as_posix(),DJANGO_SETTINGS_MODULE='metchu.settings',METCHU_DEBUG='0')
                    import django;django.setup()
                    from django.db import connections
                    try:result=refresh(root,day,report,budget,opt.get('label_tagging_enabled') is True)
                    finally:connections.close_all()
                    assert dst.execute('PRAGMA integrity_check').fetchone()==('ok',) and not dst.execute('PRAGMA foreign_key_check').fetchall()
                    # The writer lock protects menus; concurrent account writes are preserved at publication.
                    backups=root/'private/backups';backups.mkdir(exist_ok=True)
                    bak=backups/('pre-daily-'+str(now().date())+'.sqlite3')
                    if not bak.exists():
                        temp=bak.with_suffix('.tmp')
                        with contextlib.closing(sqlite3.connect(temp)) as b:reader.backup(b)
                        temp.replace(bak)
                    from menu_publish import publish_menus
                    publish_menus(stage, live)
                    for old_bak in sorted(backups.glob('pre-daily-*.sqlite3'))[:-14]:old_bak.unlink()
                    report['result']=result;report['published']=True
        except Exception as error:
            report.update(result='error',published=False,error_type=type(error).__name__,error=str(error)[:180] if type(error) is RuntimeError else 'See source/data checks')
        finally:
            report.update(finished=now().isoformat(),paid_calls=budget.actual if budget else 0,provider_error=budget.provider_error if budget else None)
            status_file(root/'state/daily-menu-last.json',report)
            status_file(root/'state'/('daily-menu-'+str(day)+'.json'),report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('unresolved_lines','unresolved_foods')},ensure_ascii=True))
    return 0 if report.get('result')=='complete' else (2 if report.get('published') else 1)
if __name__=='__main__':sys.exit(main())
