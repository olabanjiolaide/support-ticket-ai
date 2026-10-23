"""Exercise human need grouping, selected evidence, persistence and stale-tab conflicts."""
import argparse
import asyncio
from pathlib import Path
import socket
import tempfile

from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server

TEXT='My order was cancelled last week. I cannot find the item again. Is it out of stock?'


async def check(base,out):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context()
        page=await context.new_page(); errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('#ticket').fill(TEXT)
        await page.locator('#save-with-prediction').uncheck()
        await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        request_id=page.url.split('#request/')[1]
        host=page.locator('#saved-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await expect(host.locator('.breakdown-part')).to_have_count(3)
        await expect(host.locator('.need-summary')).to_contain_text('0 customer need(s)')
        await expect(host.get_by_label('Clarification question / coordination note')).to_have_attribute('placeholder','Ask for the specific missing detail, or explain how the requests depend on one another.')
        await host.get_by_role('button',name='+ Add customer need',exact=True).click()
        group=host.locator('.customer-need').first
        await group.get_by_label('Customer need / goal').fill('Locate the item and check availability')
        await group.get_by_label('Your category for this need').select_option('ORDER')
        cards=host.locator('.breakdown-part')
        for i,role in enumerate(['context','request','request']):
            await cards.nth(i).get_by_label('Your interpretation').select_option(role)
            await cards.nth(i).get_by_label('Attach to customer need').select_option('need-1')
            await expect(cards.nth(i).get_by_label('Your category for this fragment')).to_be_disabled()
        await expect(group).to_contain_text('2 current request fragment(s) · 1 background fragment(s) · 3 total assigned')
        # Removing an unused group never deletes evidence or moves the existing group.
        await host.get_by_role('button',name='+ Add customer need',exact=True).click()
        await host.locator('.customer-need').last.get_by_role('button',name='Remove need',exact=True).click()
        await expect(cards).to_have_count(3)
        await expect(cards.nth(2).get_by_label('Attach to customer need')).to_have_value('need-1')
        # The real existing model sees selected exact excerpts together, with no fabricated paraphrase.
        async with page.expect_request('**/predict') as observed:
            await group.get_by_role('button',name='Suggest category using need evidence',exact=True).click()
        payload=(await observed.value).post_data_json
        assert payload['text']=='My order was cancelled last week.\nI cannot find the item again.\nIs it out of stock?'
        await expect(group).to_contain_text('Grouped-evidence hypothesis',timeout=15000)
        await expect(group.get_by_label('Your category for this need')).to_have_value('ORDER')
        before=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert before['version']==1 and before['need_review'] is None
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(host).to_contain_text('Enter a reviewer label above')
        await page.locator('#reviewer-name').fill('Group reviewer')
        await host.get_by_label('Clarification question / coordination note').fill('Could you share the product name or link?')
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            for theme in ['light','dark']:
                await page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                await page.wait_for_timeout(250)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                await host.screenshot(path=str(out/f'need-group-{width}-{theme}.png'))
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(page.locator('#detail-feedback')).to_contain_text('Grouped needs review saved locally')
        await expect(host.locator('.breakdown-details')).not_to_have_attribute('open','')
        after=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert after['version']==2 and after['status']=='open' and after['review_state']=='pending'
        assert after['confirmed_category'] is None and after['prediction']==before['prediction']
        assert after['need_review']['review']['parts'][0]['role']=='context'
        assert len(after['need_review']['review']['groups'])==1 and len(after['history'])==2
        await page.reload()
        await expect(host.locator('.customer-need').first.get_by_label('Customer need / goal')).to_have_value('Locate the item and check availability')
        await expect(host.locator('.need-summary')).to_contain_text('1 customer need(s)')
        await host.screenshot(path=str(out/'need-group-saved-320.png'))
        # A second tab cannot overwrite a newer grouped review, and its draft remains editable.
        stale=await context.new_page();await stale.goto(base+'/#request/'+request_id)
        await expect(stale.locator('#saved-breakdown .customer-need')).to_have_count(1)
        await stale.locator('#saved-breakdown').get_by_label('Customer need / goal').fill('Keep this stale draft')
        await stale.locator('#reviewer-name').fill('Second reviewer')
        await page.locator('#reviewer-name').fill('First reviewer')
        await host.get_by_label('Customer need / goal').fill('Locate the product listing')
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(host.get_by_label('Customer need / goal')).to_have_value('Locate the product listing')
        await stale.locator('#saved-breakdown').get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(stale.locator('#saved-breakdown')).to_contain_text('changed in another tab')
        await expect(stale.locator('#saved-breakdown').get_by_label('Customer need / goal')).to_have_value('Keep this stale draft')
        await expect(stale.locator('#saved-breakdown').get_by_role('button',name='Save grouped review',exact=True)).to_be_enabled()
        # History retains both structured snapshots; no group save changes category/status.
        current=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert current['version']==3 and current['status']=='open' and current['confirmed_category'] is None
        assert current['history'][-1]['before']['need_review']['groups'][0]['title']=='Locate the item and check availability'
        assert current['history'][-1]['after']['need_review']['groups'][0]['title']=='Locate the product listing'
        assert not errors,errors
        await browser.close()
        return request_id


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args();out=args.artifacts.resolve();out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);model=fixture(root);db=root/'requests.sqlite3'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with (out/'server.log').open('w') as log:
            server=start_server(model,db,port,log)
            try: request_id=asyncio.run(check(f'http://127.0.0.1:{port}',out))
            finally: server.terminate();server.wait(timeout=10)
            server=start_server(model,db,port,log)
            try:
                import json,urllib.request
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/requests/{request_id}') as response:
                    record=json.load(response)
                assert record['need_review']['review']['groups'][0]['title']=='Locate the product listing'
            finally:server.terminate();server.wait(timeout=10)
    print('Need grouping passed: exact linked evidence, independent real word prediction, explicit structured save, reload/restart persistence, source/status preservation, stale-tab recovery and 3 widths/2 themes.')


if __name__=='__main__':main()
