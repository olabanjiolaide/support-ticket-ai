"""Verify atomic draft handoff and honest workflow states with authored AI proposals."""
import argparse
import asyncio
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
    proposal={'status':'draft','requires_human_review':True,'review':review,'model':'UI-fixture:latest'}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:(errors.append(str(e)),print('Browser:',str(e),flush=True)))
        await page.route('**/proposals/status',lambda route:route.fulfill(json={'available':True,'configured':True,'model':'UI-fixture:latest'}))
        async def generate(route):
            await asyncio.sleep(.8)
            try:await route.fulfill(json=proposal)
            except Exception:pass
        await page.route('**/proposals',generate)
        await page.goto(base);await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('#ticket').fill(text);await page.locator('#save-with-prediction').uncheck()
        draft=page.locator('#draft-breakdown');saved=page.locator('#saved-breakdown')
        await page.locator('#generate-needs-shortcut').click()
        await expect(page.locator('#save-request')).to_be_disabled()
        await expect(draft).to_contain_text('Proposal ready.')
        await expect(draft.locator('[data-stage="proposed"]')).to_contain_text('2 AI need(s)')
        await expect(draft.locator('[data-stage="adopted"]')).to_contain_text('Awaiting adoption')
        await expect(page.locator('#save-request')).to_have_text('Save request + needs draft')
        await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        identifier=page.url.split('#request/')[1]
        await expect(saved.locator('[data-stage="saved"]')).to_contain_text('Unreviewed draft saved')
        await expect(saved.locator('.proposal-need')).to_have_count(2)
        record=await (await page.request.get(base+'/requests/'+identifier)).json()
        assert record['need_review'] is None and record['review_state']=='pending' and record['needs_draft']['editable'] is None
        await page.reload();await expect(saved.locator('.proposal-need')).to_have_count(2)
        await saved.get_by_role('button',name='Use as editable draft',exact=True).click()
        await expect(saved.locator('.customer-need')).to_have_count(2)
        await expect(saved.locator('[data-stage="saved"]')).to_contain_text('Unsaved changes')
        await expect(saved.locator('[data-stage="reviewed"]')).to_contain_text('Confirmation required')
        await saved.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(saved).to_contain_text('Confirm that you reviewed the model draft')
        await page.locator('#reviewer-name').fill('Handoff reviewer')
        await saved.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.').check()
        await expect(saved.locator('[data-stage="reviewed"]')).to_contain_text('Ready for explicit save')
        await saved.locator('.customer-need').first.get_by_label('Customer need / goal').fill('Find the requested order number')
        await expect(saved.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.')).not_to_be_checked()
        await saved.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.').check()
        await saved.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(saved.locator('[data-stage="saved"]')).to_contain_text('Human review saved')
        record=await (await page.request.get(base+'/requests/'+identifier)).json()
        assert record['needs_draft'] is None and record['need_review'] is not None
        assert record['confirmed_category'] is None and record['status']=='open' and record['prediction'] is None
        # A checked confirmation in New request is never carried over as a reviewed database decision.
        await page.goto(base+'/#new');await page.locator('#ticket').fill(text)
        await page.locator('#generate-needs-shortcut').click();await expect(draft).to_contain_text('Proposal ready.')
        await draft.get_by_role('button',name='Use as editable draft',exact=True).click()
        await draft.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.').check()
        await page.locator('#save-request').click();await expect(page.locator('#request-detail-content')).to_be_visible()
        await expect(saved.locator('.customer-need')).to_have_count(2)
        await expect(saved.get_by_label('I reviewed the proposed evidence, roles, categories and relationships against the complete message.')).not_to_be_checked()
        await expect(saved.locator('[data-stage="saved"]')).to_contain_text('Unreviewed draft saved')
        await page.reload();await expect(saved.locator('.customer-need')).to_have_count(2)
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            await saved.locator('.needs-workflow').screenshot(path=str(out/f'workflow-{width}.png'))
        await page.set_viewport_size({'width':1440,'height':1000})
        await page.evaluate("dispatchEvent(new Event('beforeprint'))")
        await page.emulate_media(media='print')
        await expect(saved.locator('.evidence-empty-hint')).to_be_hidden()
        await page.pdf(path=str(out/'handoff-review.pdf'),format='A4',print_background=False)
        await page.emulate_media(media='screen')
        await page.evaluate("dispatchEvent(new Event('afterprint'))")
        # Simulate an acknowledged database write followed by a lost HTTP response.
        await page.goto(base+'/#new');await page.locator('#ticket').fill('Send my invoice. Check the delivery.')
        await draft.get_by_role('button',name='Break down message',exact=True).click()
        await draft.get_by_role('button',name='+ Add customer need',exact=True).click()
        keys=[]
        async def lost_response(route):
            body=route.request.post_data_json;keys.append(body['client_request_id'])
            response=await route.fetch()
            if len(keys)==1:await route.fulfill(status=503,json={'detail':'Simulated lost create response'})
            else:await route.fulfill(response=response)
        await page.route('**/requests',lost_response)
        await page.locator('#save-request').click();await expect(page.locator('#save-feedback')).to_contain_text('Simulated lost create response')
        await expect(draft.locator('.customer-need')).to_have_count(1)
        await page.locator('#save-request').click();await expect(page.locator('#request-detail-content')).to_be_visible()
        assert len(keys)==2 and keys[0]==keys[1]
        await page.unroute('**/requests')
        total=await (await page.request.get(base+'/requests')).json();assert total['total']==3
        await expect(saved.locator('.customer-need')).to_have_count(1)
        await expect(saved.get_by_label('Customer need / goal')).to_have_value('')
        await expect(saved.locator('.breakdown-part').first.get_by_label('Your interpretation')).to_have_value('unconfirmed')
        await expect(saved.locator('[data-stage="saved"]')).to_contain_text('Unreviewed draft saved')
        assert not errors,errors
        await browser.close()
    print('Needs handoff passed: unadopted/adopted proposals, incomplete manual choices, re-confirmation, reload, explicit review save, busy-save blocking, lost-response idempotency, zero auto-confirmations and responsive workflow states. Authored AI responses only.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    out=parser.parse_args().artifacts.resolve();out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);model=fixture(root)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with (out/'server.log').open('w') as log:
            server=start_server(model,root/'requests.sqlite3',port,log)
            try:asyncio.run(check(f'http://127.0.0.1:{port}',out))
            finally:server.terminate();server.wait(timeout=10)


if __name__=='__main__':main()
