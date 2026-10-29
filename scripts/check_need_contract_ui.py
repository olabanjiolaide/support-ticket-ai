"""Check human action targets and partial need resolution with a real local server."""
import argparse
import asyncio
from pathlib import Path
import socket
import tempfile
from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server

TEXT='😀 Cancel order A. Keep order B.'


async def check(base,out):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base);await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('#ticket').fill(TEXT);await page.locator('#save-with-prediction').uncheck();await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        request_id=page.url.split('#request/')[1];host=page.locator('#saved-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        cards=host.locator('.breakdown-part');await expect(cards).to_have_count(2)
        for index,title,target in [(0,'Cancel first order','order A'),(1,'Keep second order','order B')]:
            await host.get_by_role('button',name='+ Add customer need',exact=True).click()
            group=host.locator('.customer-need').nth(index)
            await group.get_by_label('Customer need / goal').fill(title)
            await group.get_by_label('Your category for this need').select_option('ORDER')
            await group.locator('.need-contract > summary').click()
            await group.get_by_role('button',name='Add proposed action',exact=True).click()
            action=group.locator('.need-action');await action.get_by_label('Proposed action',exact=True).fill(title)
            await action.locator('details > summary').click()
            source=action.get_by_label('Original message — select action target')
            await source.evaluate('(el,text)=>{const start=el.value.indexOf(text);el.focus();el.setSelectionRange(start,start+text.length);}',target)
            await action.get_by_role('button',name='Use selected target',exact=True).click()
            await expect(action).to_contain_text(target)
            await cards.nth(index).get_by_label('Your interpretation').select_option('request')
            await cards.nth(index).get_by_label('Attach to customer need').select_option(f'need-{index+1}')
        await page.locator('#reviewer-name').fill('Contract browser reviewer')
        await host.get_by_role('button',name='Save grouped review',exact=True).click()
        handling=page.locator('#need-handling')
        await expect(handling.locator('.need-handling-card')).to_have_count(2)
        stored=await (await page.request.get(base+'/requests/'+request_id)).json()
        document=stored['need_review']['review'];assert document['schema_version']==3
        for group in document['groups']:
            target=group['actions'][0]['target'];assert TEXT[target['start']:target['end']]==target['text']
        await page.locator('#review-category').select_option('ORDER');await page.locator('#confirm-review').click()
        await expect(page.locator('#detail-review-state')).to_contain_text('reviewed')
        await page.locator('#start-handling').click();await expect(page.locator('#detail-status')).to_have_text('In progress')
        first=handling.locator('.need-handling-card').nth(0)
        await first.get_by_label('Update note / completion evidence').fill('Checking cancellation for order A')
        await first.get_by_role('button',name='Start need',exact=True).click();await expect(first.locator('.need-handling-status')).to_have_attribute('data-status','in_progress')
        await first.get_by_label('Update note / completion evidence').fill('Cancellation confirmed by reviewer')
        await first.get_by_role('button',name='Resolve need',exact=True).click();await expect(handling).to_contain_text('1/2 needs finished')
        await page.locator('#review-note').fill('Attempting early parent completion')
        await page.locator('#resolve-request').click();await expect(page.locator('#detail-error')).to_contain_text('Finish or explicitly dismiss')
        second=handling.locator('.need-handling-card').nth(1)
        await second.get_by_label('Update note / completion evidence').fill('Order B stays active; no change needed')
        await second.get_by_role('button',name='Dismiss with reason',exact=True).click();await expect(handling).to_contain_text('2/2 needs finished')
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            await page.screenshot(path=str(out/f'need-progress-{width}.png'),full_page=True,animations='disabled')
        await page.set_viewport_size({'width':1000,'height':1000})
        await handling.screenshot(path=str(out/'need-handling-panel.png'))
        await page.locator('#review-note').fill('Both needs reviewed: cancellation reported and second order retained')
        await page.locator('#resolve-request').click();await expect(page.locator('#detail-status')).to_have_text('Resolved')
        await page.reload();await expect(handling).to_contain_text('2/2 needs finished')
        await page.locator('#reviewer-name').fill('Contract browser reviewer')
        await page.locator('#review-note').fill('Customer asks to revisit first need');await page.locator('#reopen-request').click()
        await expect(page.locator('#detail-status')).to_have_text('Awaiting review')
        await first.get_by_label('Update note / completion evidence').fill('Rechecking cancellation')
        await first.get_by_role('button',name='Reopen need',exact=True).click();await expect(handling).to_contain_text('1/2 needs finished')
        assert not errors,errors
        await browser.close()
    print('Contract UI passed: exact Unicode action targets, explicit review save, independent statuses, partial-resolution guard, dismissal, reload, reopen and mobile widths. No model inference or customer-account operation.')


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
