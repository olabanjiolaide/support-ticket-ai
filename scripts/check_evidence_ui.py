"""Verify diagnostics and manual evidence editing against a real local server."""
import argparse
import asyncio
from pathlib import Path
import socket
import tempfile
from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server

TEXT='😀 Find my order number but I cannot access my account. Earlier order was cancelled.'


async def check(base, out):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('#diagnostics-panel summary').click()
        await expect(page.locator('#diagnostics-summary')).to_contain_text('v0.22.0')
        await expect(page.locator('#diagnostics-status')).to_contain_text('identities match')
        diagnostic=await (await page.request.get(base+'/diagnostics')).json()
        await page.route('**/diagnostics',lambda route:route.fulfill(json={**diagnostic,'frontend_build':'changed-build'}))
        await page.locator('#refresh-diagnostics').click()
        await expect(page.locator('#diagnostics-status')).to_contain_text('Reload this page')
        await page.unroute('**/diagnostics')
        await page.locator('#refresh-diagnostics').click()
        await expect(page.locator('#diagnostics-status')).to_contain_text('identities match')
        await page.locator('#ticket').fill(TEXT)
        await page.locator('#save-with-prediction').uncheck()
        await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        request_id=page.url.split('#request/')[1]
        host=page.locator('#saved-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        cards=host.locator('.breakdown-part');await expect(cards).to_have_count(2)
        editor=host.locator('.evidence-editor')
        await editor.locator('summary').click()
        original=editor.get_by_label('Original message — select a split position')
        await expect(original).to_have_attribute('readonly','')
        await original.evaluate('(el)=>{el.focus();el.setSelectionRange(el.value.indexOf("but"),el.value.indexOf("but"));}')
        await editor.get_by_role('button',name='Split at cursor',exact=True).click()
        await expect(cards).to_have_count(3)
        await expect(cards.nth(0).locator('blockquote')).to_have_text('😀 Find my order number ')
        await expect(cards.nth(1).get_by_label('Your interpretation')).to_have_value('unconfirmed')
        await editor.get_by_role('button',name='Undo boundary edit',exact=True).click()
        await expect(cards).to_have_count(2)
        await original.evaluate('(el)=>{el.focus();el.setSelectionRange(el.value.indexOf("but"),el.value.indexOf("but"));}')
        await editor.get_by_role('button',name='Split at cursor',exact=True).click()
        await editor.get_by_role('button',name='Merge with next fragment',exact=True).click()
        await expect(cards).to_have_count(2)
        await editor.get_by_role('button',name='Undo boundary edit',exact=True).click()
        await expect(cards).to_have_count(3)
        for title,category,kind in [('Retrieve order number','ORDER','goal'),('Restore account access','ACCOUNT','obstacle')]:
            await host.get_by_role('button',name='+ Add customer need',exact=True).click()
            group=host.locator('.customer-need').last
            await group.get_by_label('Customer need / goal').fill(title)
            await group.get_by_label('Your category for this need').select_option(category)
            await group.get_by_label('Need type').select_option(kind)
        for index,role,group in [(0,'request','need-1'),(1,'obstacle','need-2'),(2,'context','need-1')]:
            await cards.nth(index).get_by_label('Your interpretation').select_option(role)
            await cards.nth(index).get_by_label('Attach to customer need').select_option(group)
        # Boundary changes and classifications alone do not persist anything.
        saved=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert saved['version']==1 and saved['need_review'] is None
        await page.locator('#reviewer-name').fill('Evidence browser check')
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        await expect(host).to_contain_text('Loaded the last saved human review')
        saved=await (await page.request.get(base+'/requests/'+request_id)).json()
        review=saved['need_review']
        # API returns a wrapper with the reviewed document.
        if 'review' in review:review=review['review']
        assert len(review['parts'])==3
        for part in review['parts']:assert TEXT[part['start']:part['end']]==part['text']
        assert saved['status']=='open' and saved['confirmed_category'] is None
        await page.reload();await expect(host).to_contain_text('Loaded the last saved human review')
        await expect(host.locator('.breakdown-part')).to_have_count(3)
        await host.locator('.breakdown-details > summary').click()
        await editor.locator('summary').click()
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            await page.screenshot(path=str(out/f'evidence-{width}.png'),full_page=True,animations='disabled')
        assert not errors,errors
        await browser.close()
    print('Diagnostics, build mismatch, Unicode split/merge/undo, explicit save/reload and responsive evidence editing passed.')


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
