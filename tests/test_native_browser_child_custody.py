"""Real pinned Chromium descendants plus explicit parser-only negative cases.

The renderer/zygote prefix only execs the same approved Chromium executable
with this authored profile. Kernel PIDs, births, executable hashes and real
Node→browser→child ancestry remain genuine; no process guard is substituted.
"""
from contextlib import contextmanager
from pathlib import Path
import json,os,shlex,sys,time
import pytest
from tests import gui_native_browser as browser

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]

@contextmanager
def _real_profile_child(tmp_path):
    node,chromium=browser.pin_executables()
    profile=tmp_path/'owned-profile';profile.mkdir(mode=0o700)
    prefix=tmp_path/'child-prefix.py'
    prefix.write_text('import os,sys\n' + 'expected='+repr(chromium.path)+'\nprofile='+repr(str(profile))+'\n' + '''
args=sys.argv[1:]
if not args or args[0]!=expected:raise SystemExit(97)
if not any(item.startswith('--type=') for item in args):raise SystemExit(98)
if not any(item.startswith('--user-data-dir') for item in args):args.append('--user-data-dir='+profile)
os.execv(expected,args)
''')
    prefix.chmod(0o600)
    command=shlex.join([sys.executable,'-I','-B',str(prefix)])
    sync=browser._load_sync_playwright();previous=os.environ.get('PLAYWRIGHT_NODEJS_PATH')
    os.environ['PLAYWRIGHT_NODEJS_PATH']=node.path
    observed=set()
    try:
        with sync() as driver:
            context=driver.chromium.launch_persistent_context(str(profile),executable_path=chromium.path,
                headless=True,service_workers='block',args=['--no-first-run','--no-default-browser-check',
                    '--disable-sync','--disable-extensions','--disable-background-networking',
                    '--disable-component-update','--no-sandbox','--disable-breakpad','--disable-crash-reporter',
                    '--renderer-cmd-prefix='+command,'--zygote-cmd-prefix='+command])
            try:
                page=context.pages[0] if context.pages else context.new_page()
                page.set_content('<p id="owned-child">authored real Chromium child</p>')
                assert page.locator('#owned-child').inner_text()=='authored real Chromium child'
                deadline=time.monotonic()+10;children=[]
                while time.monotonic()<deadline:
                    table=browser._process_table();children=[]
                    for pid,(_,argv,_) in table.items():
                        if str(profile) not in '\n'.join(argv):continue
                        birth=browser._pinned_process(pid,chromium)
                        parts=tuple(shlex.split(argv[0])) if len(argv)==1 else argv
                        if any(item.startswith('--type=') for item in parts):
                            children.append({'pid':pid,'birth':birth,'pipe_count':parts.count('--remote-debugging-pipe'),
                                'profile_count':parts.count('--user-data-dir='+str(profile))})
                    if children:break
                    time.sleep(.02)
                assert children, 'Actual Chromium child carrying the profile was not observed.'
                assert all(row['profile_count']==1 for row in children)
                yield node,chromium,profile,children
            finally:
                table=browser._process_table();own_nodes=set()
                for pid,(_,argv,_) in table.items():
                    if tuple(argv)!=node.argv:continue
                    cursor,seen=pid,set()
                    while cursor in table and cursor not in seen and cursor!=os.getpid():
                        seen.add(cursor);cursor=table[cursor][0]
                    if cursor==os.getpid():own_nodes.add(pid)
                observed=browser._with_descendants(own_nodes)
                context.close()
    finally:
        if previous is None:os.environ.pop('PLAYWRIGHT_NODEJS_PATH',None)
        else:os.environ['PLAYWRIGHT_NODEJS_PATH']=previous
    cleanup=browser._wait_for_cleanup(observed)
    assert cleanup['cleaned'],cleanup


def test_actual_profile_child_keeps_unique_root_custody(tmp_path):
    with _real_profile_child(tmp_path) as (node,chromium,profile,children):
        assert any(row['pipe_count']==0 for row in children)
        browser._assert_process_custody(node,chromium,profile)


@pytest.mark.parametrize('extra', [
    ['--remote-debugging-port=9222'], ['--remote-debugging-port','9222'],
    ['--remote-debugging-address=127.0.0.1'], ['--user-data-dir=/foreign'],
    ['--user-data-dir','/foreign'], ['--type=unknown'], ['--type=renderer','--type=utility'],
    ['--type'], ['--remote-debugging-pipe=extra'],
])
def test_child_argument_policy_refuses_unqualified_flags(tmp_path,extra):
    # Pure parser controls confer no process ownership or browser qualification.
    pin=browser.PinnedExecutable('synthetic-chromium','/synthetic/chrome','0'*64,('/synthetic/chrome',))
    with pytest.raises(browser.BrowserCapabilityError):
        browser._chromium_role_argv((pin.path,'--type=renderer',*extra),pin,tmp_path)


@pytest.mark.parametrize('role',['zygote','renderer','gpu-process','utility'])
def test_child_profile_may_be_absent_but_supplied_profile_is_exact(tmp_path,role):
    pin=browser.PinnedExecutable('synthetic-chromium','/synthetic/chrome','0'*64,('/synthetic/chrome',))
    for profile in [[],['--user-data-dir='+str(tmp_path)]]:
        label,_=browser._chromium_role_argv((pin.path,'--type='+role,*profile),pin,tmp_path)
        assert label==role
    with pytest.raises(browser.BrowserCapabilityError):
        browser._chromium_role_argv((pin.path,'--type='+role,'--user-data-dir='+str(tmp_path)+'-other'),pin,tmp_path)


def test_root_parser_still_requires_unique_pipe_and_profile(tmp_path):
    pin=browser.PinnedExecutable('synthetic-chromium','/synthetic/chrome','0'*64,('/synthetic/chrome',))
    for extra in [[],['--user-data-dir='+str(tmp_path)],['--remote-debugging-pipe']]:
        with pytest.raises(browser.BrowserCapabilityError):
            browser._chromium_title_argv((pin.path,*extra),pin,tmp_path)
