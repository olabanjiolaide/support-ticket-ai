"""Exercise clickable section navigation, quick evidence review, mobile drawer and print views."""
import argparse
import asyncio
from pathlib import Path
import socket
import tempfile

from playwright.async_api import async_playwright, expect
from check_installed import fixture
from check_request_workflow import start_server


async def check(base,out):
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        page=await context.new_page();errors=[]
        page.on('pageerror',lambda error:(errors.append(str(error)),print('Browser error:',str(error),flush=True)))
        await page.goto(base)
        await expect(page.locator('#service-label')).to_have_text('Model ready')
        await page.locator('[data-section="compose"]').click();await expect(page.locator('#ticket')).to_be_focused()
        await page.locator('#ticket').fill('password reset account login')
        await page.locator('#submit').click();await expect(page.locator('#category')).to_have_text('Account')
        await expect(page.locator('#workbench-state')).to_contain_text('Suggestion ready')
        await page.locator('[data-section="result"]').click();await expect(page.locator('#category')).to_be_focused()
        await page.locator('[data-section="needs"]').click();await expect(page.locator('#draft-breakdown h2')).to_be_focused()
        text='Please send my invoice. I cannot access my account.'
        await page.locator('#ticket').fill(text)
        await page.route('**/predict',lambda route:route.fulfill(status=500,json={'detail':'Temporary test failure.'}))
        await page.locator('#submit').click();await expect(page.locator('#result-error')).to_be_visible()
        await page.locator('[data-section="result"]').click();await expect(page.locator('#result-error h2')).to_be_focused()
        await expect(page.locator('#workbench-state')).to_contain_text('needs attention')
        await page.unroute('**/predict')
        host=page.locator('#draft-breakdown')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        cards=host.locator('.breakdown-part');await expect(cards).to_have_count(2)
        progress=host.get_by_role('progressbar',name='Interpretation selection progress')
        await expect(progress).to_have_attribute('aria-valuenow','0')
        await cards.nth(0).get_by_role('radio',name='Request',exact=True).check()
        await expect(cards.nth(0).get_by_label('Your interpretation')).to_have_value('request')
        await expect(cards.nth(0).locator('.role-badge')).to_have_text('Current request')
        await expect(progress).to_have_attribute('aria-valuenow','1')
        await host.get_by_role('button',name='Review next fragment',exact=True).click()
        await expect(cards.nth(1).get_by_label('Your interpretation')).to_be_focused()
        await cards.nth(1).get_by_role('radio',name='Context',exact=True).check()
        await expect(progress).to_have_attribute('aria-valuenow','2')
        await host.get_by_role('button',name='Create first need',exact=True).click()
        group=host.locator('.customer-need').first
        await expect(group.get_by_label('Customer need / goal')).to_be_focused()
        await group.get_by_label('Customer need / goal').fill('Obtain the invoice')
        await group.get_by_label('Your category for this need').select_option('INVOICE')
        await cards.nth(0).get_by_label('Attach to customer need').select_option('need-1')
        await group.get_by_role('button',name='Inspect assigned evidence',exact=True).click()
        await expect(cards.nth(0)).to_be_visible();await expect(cards.nth(1)).to_be_hidden()
        await expect(progress).to_have_attribute('aria-valuenow','2')
        await host.get_by_role('button',name='All fragments',exact=True).click()
        await expect(cards.nth(1)).to_be_visible()
        # Preferences change presentation only, and source data is untouched.
        await page.locator('#density-toggle').click()
        await expect(page.locator('body')).to_have_attribute('data-density','compact')
        await expect(page.locator('#ticket')).to_have_value(text)
        await page.reload()
        await expect(page.locator('body')).to_have_attribute('data-density','compact')
        assert 'invoice' not in await page.evaluate('JSON.stringify(localStorage)')
        await page.locator('#density-toggle').click()
        # Screenshots cover the real interaction layout in both themes; no LLM outputs are fabricated.
        for width in [1440,1024,768,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            for theme in ['light','dark']:
                await page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme);await page.wait_for_timeout(250)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                await page.evaluate("scrollTo({top:0,behavior:'instant'})")
                await page.screenshot(path=str(out/f'workbench-{width}-{theme}.png'),full_page=True,animations='disabled')
        await page.locator('#nav-toggle').click()
        await expect(page.locator('#workspace-sidebar')).to_have_attribute('aria-modal','true')
        await expect(page.locator('#nav-close')).to_be_focused()
        await expect(page.locator('.page')).to_have_attribute('inert','')
        await page.keyboard.press('Shift+Tab');await expect(page.locator('.api-link')).to_be_focused()
        await page.keyboard.press('Escape');await expect(page.locator('#nav-toggle')).to_be_focused()
        await expect(page.locator('#nav-scrim')).to_be_hidden()
        await page.locator('#nav-toggle').click();await page.locator('[data-view="overview"]').click()
        await expect(page.locator('#overview-view')).to_be_visible()
        await expect(page.locator('#nav-toggle')).to_have_attribute('aria-expanded','false')
        await page.locator('#workspace-view').select_option('new')
        await page.locator('#ticket').fill(text)
        # Print mirrors source values, avoids printing placeholders as answers, and cleans up after print.
        await page.evaluate("dispatchEvent(new Event('beforeprint'))")
        await expect(page.locator('.print-value').first).to_have_text(text)
        await page.emulate_media(media='print')
        await page.evaluate("dispatchEvent(new Event('beforeprint'))")
        await expect(page.locator('.print-value').first).to_have_text(text)
        await expect(page.locator('.page-footer')).to_be_hidden()
        await expect(page.locator('.workbench-nav')).to_be_hidden()
        await page.pdf(path=str(out/'print-check.pdf'),format='A4',print_background=False)
        await page.emulate_media(media='screen')
        await page.evaluate("dispatchEvent(new Event('afterprint'))")
        await expect(page.locator('.print-value')).to_have_count(0)
        await expect(page.locator('#ticket')).to_have_value(text)
        # Respect reduced motion without disabling keyboard interaction.
        await page.emulate_media(reduced_motion='reduce')
        await page.locator('[data-section="compose"]').click();await expect(page.locator('#ticket')).to_be_focused()
        assert (await (await page.request.get(base+'/requests/overview')).json())['total']==0
        assert not errors,errors
        await browser.close()
    print('Interactive UI passed: section focus, role shortcuts/progress, need evidence filters, density persistence, mobile focus trap/navigation, 5 widths/2 themes, print cleanup and reduced motion. No records saved.')


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
