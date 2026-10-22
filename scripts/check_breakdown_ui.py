"""Check evidence review, independent predictions, explicit note saving and mobile layout."""
import argparse
import asyncio
import json
import re
from pathlib import Path
import socket
import tempfile

from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server


async def check(base, out):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        text='Can I get special offers? My packages await delivery. I cannot log in and my payment was rejected.'
        await page.goto(base)
        await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('#ticket').fill(text)
        await page.locator('#submit').click()
        await expect(page.locator('#category')).to_have_text('Category withheld')
        host=page.locator('#draft-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await expect(host.locator('.breakdown-part')).to_have_count(4)
        assert (await (await page.request.get(base+'/requests/overview')).json())['total']==0
        # Changing text invalidates its evidence immediately.
        await page.locator('#ticket').fill('Changed message')
        await expect(host.locator('.breakdown-part')).to_have_count(0)
        await page.locator('#ticket').fill(text)
        await page.locator('#save-with-prediction').uncheck()
        await page.locator('#save-request').click()
        await expect(page.locator('#request-detail-content')).to_be_visible()
        request_id=page.url.split('#request/')[1]
        original=await (await page.request.get(base+'/requests/'+request_id)).json()
        host=page.locator('#saved-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await expect(host.locator('.breakdown-part')).to_have_count(4)
        cards=host.locator('.breakdown-part')
        for i in range(4):
            await expect(cards.nth(i).get_by_role('button')).to_be_disabled()
        await host.get_by_role('button',name='Add reviewed breakdown to note draft').click()
        await expect(host).to_contain_text('Review the interpretation of every fragment first.')
        await cards.nth(0).get_by_label('Your interpretation').select_option('request')
        await cards.nth(0).get_by_label('Your category for this fragment').select_option('OUTSIDE_SCOPE')
        await cards.nth(1).get_by_label('Your interpretation').select_option('context')
        await cards.nth(2).get_by_label('Your interpretation').select_option('request')
        await cards.nth(2).get_by_role('button').click()
        await expect(cards.nth(2)).to_contain_text('Fragment-only hypothesis',timeout=15000)
        # A model suggestion never silently sets the human category.
        await expect(cards.nth(2).get_by_label('Your category for this fragment')).to_have_value('')
        await cards.nth(2).get_by_label('Your category for this fragment').select_option('ACCOUNT')
        await cards.nth(3).get_by_label('Your interpretation').select_option('unclear')
        await host.get_by_role('button',name='Add reviewed breakdown to note draft').click()
        await expect(host).to_contain_text('Add a clarification question')
        await host.get_by_label('Clarification question / coordination note').fill('Was the payment rejected, and do you need help retrying it?')
        await page.locator('#review-note').fill('Existing note.')
        await host.get_by_role('button',name='Add reviewed breakdown to note draft').click()
        await expect(page.locator('#review-note')).to_have_value(re.compile(r'Existing note\.',re.S))
        assert 'Human: context' in await page.locator('#review-note').input_value()
        assert 'Model hypothesis' in await page.locator('#review-note').input_value()
        before=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert before==original, 'Preview and staging must be stateless'
        for width in [1440,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            for theme in ['light','dark']:
                await page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
                await page.wait_for_timeout(250)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                await host.screenshot(path=str(out/f'breakdown-{width}-{theme}.png'))
        await page.locator('#reviewer-name').fill('UI reviewer')
        await page.locator('#add-review-note').click()
        await expect(page.locator('#request-history')).to_contain_text('Human-assisted breakdown v1')
        after=await (await page.request.get(base+'/requests/'+request_id)).json()
        assert after['prediction']==original['prediction']
        assert after['status']==original['status'] and after['confirmed_category'] is None
        assert len(after['history'])==2
        await page.reload()
        await expect(page.locator('#request-history')).to_contain_text('Human-assisted breakdown v1')
        # HTML-looking text stays literal, including in fragments.
        await page.goto(base+'/#new')
        await page.locator('#ticket').fill('<img src=x onerror="window.bad=1">. Please reset my password.')
        host=page.locator('#draft-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await expect(host.locator('blockquote').first).to_contain_text('<img')
        assert await host.locator('img').count()==0 and not await page.evaluate('window.bad')
        # Per-fragment model errors preserve manual review.
        await page.route('**/predict',lambda route:route.fulfill(status=503,json={'detail':'Model is not ready.'}))
        card=host.locator('.breakdown-part').last
        await card.get_by_label('Your interpretation').select_option('request')
        await card.get_by_role('button').click()
        await expect(card).to_contain_text('You can classify manually.')
        await card.get_by_label('Your category for this fragment').select_option('ACCOUNT')
        assert not errors, errors
        await browser.close()
        print('Breakdown passed: evidence invalidation, independent real word prediction, role/category separation, explicit persisted notes, no status mutation, 3 widths/2 themes, HTML safety and unavailable-model fallback.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args(); out=args.artifacts.resolve(); out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); model=fixture(root)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
        with (out/'server.log').open('w') as log:
            server=start_server(model,root/'requests.sqlite3',port,log)
            try: asyncio.run(check(f'http://127.0.0.1:{port}',out))
            finally: server.terminate(); server.wait(timeout=10)


if __name__=='__main__': main()
