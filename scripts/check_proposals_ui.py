"""UI integration using authored proposal responses; not live language-model evaluation."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import socket
import tempfile

from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server
from support_ticket_ai.proposals import align_plan
from support_ticket_ai.resources import data_path


async def check(base,out):
    case=json.loads(data_path('needs_proposals_development.json').read_text())['cases'][0]
    text=case['text'];review=align_plan(text,case['expected_plan'])
    proposal={'status':'draft','requires_human_review':True,'model':'UI-fixture:latest','model_digest':'a'*64,
              'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'prompt_version':1,'prompt_sha256':'b'*64,'review':review}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True);context=await browser.new_context();page=await context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(base)
        draft=page.locator('#draft-breakdown')
        await expect(draft.get_by_role('button',name='Generate needs proposals',exact=True)).to_be_disabled()
        await expect(draft).to_contain_text('not configured')
        await page.route('**/proposals/status',lambda route:route.fulfill(json={'configured':True,'available':True,'model':'UI-fixture:latest'}))
        await page.route('**/proposals',lambda route:route.fulfill(json=proposal))
        await page.locator('#ticket').fill(text)
        await page.locator('#save-with-prediction').uncheck();await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        request_id=page.url.split('#request/')[1];host=page.locator('#saved-breakdown')
        await host.get_by_role('button',name='Check local model',exact=True).click()
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await expect(host.locator('.breakdown-part')).to_have_count(1)
        await host.get_by_role('button',name='+ Add customer need',exact=True).click()
        await host.get_by_label('Customer need / goal').fill('Keep this manual review')
        await host.get_by_role('button',name='Generate needs proposals',exact=True).click()
        await expect(host).to_contain_text('Proposal ready.')
        await expect(host.get_by_label('Customer need / goal')).to_have_value('Keep this manual review')
        before=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert before['need_review'] is None and before['version']==1
        await host.get_by_role('button',name='Use as editable draft',exact=True).click()
        await expect(host.locator('.customer-need')).to_have_count(2)
        await expect(host.locator('.breakdown-part')).to_have_count(2)
        await expect(host.locator('.need-relation')).to_have_count(1)
        await expect(host.locator('.breakdown-part').nth(1).get_by_label('Your interpretation')).to_have_value('obstacle')
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(host).to_contain_text('Confirm that you reviewed the model draft')
        await page.locator('#reviewer-name').fill('Proposal UI reviewer')
        await host.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.').check()
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            for theme in ['light','dark']:
                await page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme);await page.wait_for_timeout(250)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                await host.screenshot(path=str(out/f'proposals-{width}-{theme}.png'))
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(page.locator('#detail-feedback')).to_contain_text('Grouped needs review saved locally')
        after=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert after['need_review']['review']['schema_version']==3
        assert after['need_review']['review']['relations']==review['relations']
        assert after['need_review']['review']['groups'][1]['kind']=='obstacle'
        assert after['prediction']==before['prediction'] and after['status']=='open' and after['confirmed_category'] is None
        await page.reload();await expect(host.locator('.need-relation')).to_have_count(1)
        await expect(host.locator('.customer-need')).to_have_count(2)
        # Failure never replaces an existing editable review or saved snapshot.
        await host.locator('.customer-need').first.get_by_label('Customer need / goal').fill('Keep my correction')
        await page.unroute('**/proposals')
        await page.route('**/proposals',lambda route:route.fulfill(status=502,json={'detail':'Evidence validation failed.'}))
        await host.get_by_role('button',name='Generate needs proposals',exact=True).click()
        await expect(host).to_contain_text('Evidence validation failed.')
        await expect(host.locator('.customer-need').first.get_by_label('Customer need / goal')).to_have_value('Keep my correction')
        assert await (await page.request.get(base+'/requests/'+request_id)).json()==after
        # Late replies after cancellation or source editing are discarded.
        await page.unroute('**/proposals')
        async def delayed(route):
            await asyncio.sleep(2)
            try:await route.fulfill(json=proposal)
            except Exception:pass
        await page.route('**/proposals',delayed)
        await host.get_by_role('button',name='Generate needs proposals',exact=True).click()
        await host.get_by_role('button',name='Cancel generation',exact=True).click()
        await page.wait_for_timeout(2200)
        await expect(host.get_by_role('button',name='Use as editable draft',exact=True)).to_have_count(0)
        await expect(host.locator('.customer-need').first.get_by_label('Customer need / goal')).to_have_value('Keep my correction')
        await page.goto(base+'/#new');await page.locator('#ticket').fill(text)
        await draft.get_by_role('button',name='Generate needs proposals',exact=True).click()
        await page.locator('#ticket').fill('Different current message')
        await page.wait_for_timeout(2200)
        await expect(draft.get_by_role('button',name='Use as editable draft',exact=True)).to_have_count(0)
        assert not errors,errors
        await browser.close()
    print('Proposal UI passed with authored model stubs: separate draft/confirmation, fine evidence spans, obstacle/relationship persistence, failure/cancel/source-edit preservation and 3 widths/2 themes. No live LLM evaluation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args();out=args.artifacts.resolve();out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);model=fixture(root)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with (out/'server.log').open('w') as log:
            server=start_server(model,root/'requests.sqlite3',port,log)
            try:asyncio.run(check(f'http://127.0.0.1:{port}',out))
            finally:server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
