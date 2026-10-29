"""Verify discoverable generation controls and failure/retry UI with authored responses."""
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
    proposal={'status':'draft','requires_human_review':True,'review':review,'model':'UI-fixture:latest',
              'generation_attempts':2,'recovered_from_validation':'evidence_mismatch','prompt_version':2,
              'source_sha256':hashlib.sha256(text.encode()).hexdigest()}
    failure={'detail':'Generation failed validation after two attempts (evidence_mismatch). No draft was applied.',
             'code':'invalid_output','validation_code':'evidence_mismatch','attempts':2,'prompt_version':2}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
        page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.route('**/proposals/status',lambda route:route.fulfill(json={'available':True,'configured':True,'model':'UI-fixture:latest'}))
        await page.route('**/proposals',lambda route:route.fulfill(status=502,json=failure))
        await page.goto(base);await expect(page.locator('#service-label')).to_have_text('Model ready')
        shortcut=page.locator('#generate-needs-shortcut');await expect(shortcut).to_be_disabled()
        await page.locator('#ticket').fill(text);await expect(shortcut).to_be_enabled()
        host=page.locator('#draft-breakdown');panel=host.locator('.proposal-panel')
        await host.get_by_role('button',name='Break down message',exact=True).click()
        await host.get_by_role('button',name='+ Add customer need',exact=True).click()
        await host.get_by_label('Customer need / goal').fill('Preserve my manual draft')
        await shortcut.click()
        await expect(panel).to_have_attribute('data-state','error')
        await expect(panel.get_by_role('alert')).to_contain_text('evidence_mismatch')
        await expect(panel.get_by_role('button',name='Retry generation',exact=True)).to_be_visible()
        await expect(host.get_by_label('Customer need / goal')).to_have_value('Preserve my manual draft')
        await panel.get_by_role('button',name='Copy error details',exact=True).click()
        copied=json.loads(await page.evaluate('navigator.clipboard.readText()'))
        assert copied['validation_code']=='evidence_mismatch' and copied['attempts']==2 and copied['prompt_version']==2
        assert text not in json.dumps(copied)
        records=await (await page.request.get(base+'/requests')).json();assert records['total']==0
        for width in [1440,1024,768,390,320]:
            await page.set_viewport_size({'width':width,'height':1000})
            for theme in ['light','dark']:
                await page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme)
                await panel.screenshot(path=str(out/f'proposal-error-{width}-{theme}.png'))
                await page.locator('.proposal-launch').screenshot(path=str(out/f'proposal-launch-{width}-{theme}.png'))
        await page.unroute('**/proposals')
        async def success(route):
            await asyncio.sleep(.4)
            try:await route.fulfill(json=proposal)
            except Exception:pass
        await page.route('**/proposals',success)
        await panel.get_by_role('button',name='Retry generation',exact=True).click()
        await expect(panel.get_by_role('progressbar')).to_be_visible()
        await expect(panel).to_have_attribute('data-state','draft')
        await expect(panel).to_contain_text('second passed structural checks')
        await expect(host.get_by_label('Customer need / goal')).to_have_value('Preserve my manual draft')
        await expect(panel.get_by_role('button',name='Use as editable draft',exact=True)).to_be_visible()
        # Cancellation and source changes still discard late replies without adopting them.
        await shortcut.click();await panel.get_by_role('button',name='Cancel generation',exact=True).click()
        await page.wait_for_timeout(600);await expect(panel.get_by_role('button',name='Use as editable draft',exact=True)).to_have_count(0)
        await page.emulate_media(reduced_motion='reduce')
        assert await panel.locator('.proposal-spinner').evaluate('(el)=>getComputedStyle(el).animationName')=='none'
        assert not errors,errors
        await browser.close()
    print('Proposal controls passed: composer shortcut, prominent primary action, safe error copy, retry/progress/cancel, draft preservation, zero saves, five widths/two themes and reduced motion. Authored responses only; no live model evaluation.')


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
