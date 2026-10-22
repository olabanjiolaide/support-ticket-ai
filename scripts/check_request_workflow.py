"""Exercise saved-request lifecycle, navigation, persistence and conflicting browser tabs."""

import argparse
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.async_api import async_playwright, expect


def start_server(model, db, port, log):
    server = subprocess.Popen([sys.executable, '-m', 'support_ticket_ai.serve', '--model-dir', str(model),
                               '--requests-db', str(db), '--port', str(port)], stdout=log, stderr=log)
    deadline = time.monotonic() + 30
    while True:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/workspace/config',timeout=.5).close()
            return server
        except OSError:
            if server.poll() is not None or time.monotonic() > deadline:
                server.terminate()
                raise RuntimeError('Server failed to start; inspect workflow-server.log')
            time.sleep(.1)


async def check(base, out):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(color_scheme='light')
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        records = []

        async def go(view):
            if await page.locator('#workspace-view').is_visible():
                await page.locator('#workspace-view').select_option(view)
            else:
                await page.locator(f'[data-view="{view}"]').click()
            await expect(page.locator('#breadcrumb-current')).not_to_be_empty()

        async def shot(name):
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
            await page.evaluate("scrollTo({top:0,behavior:'instant'})")
            await page.screenshot(path=str(out / f'{name}.png'), full_page=True, animations='disabled')

        try:
            await page.goto(base)
            await expect(page.locator('#storage-notice')).to_contain_text('Local workspace')
            await expect(page.locator('#service-label')).to_have_text('Model ready')
            await go('overview')
            await expect(page.locator('#overview-metrics')).to_contain_text('0')
            await go('requests')
            await expect(page.locator('.empty-list')).to_be_visible()
            for number, width in enumerate([1440,390,320], start=1):
                await page.set_viewport_size({'width':width,'height':1000})
                await go('new')
                marker=f'browser-request-{width}'
                await page.locator('#ticket').fill(f'password reset account login {marker}')
                await page.locator('#submit').click()
                await expect(page.locator('#category')).to_have_text('Account')
                original=json.loads(await page.locator('#json-response').text_content())
                await page.locator('#save-request').click()
                await expect(page.locator('#request-detail-content')).to_be_visible()
                await expect(page.locator('#detail-status')).to_have_text('Awaiting review')
                record_id=page.url.split('#request/')[1]
                records.append((record_id,original))
                stored=await (await context.request.get(base+'/requests/'+record_id)).json()
                assert stored['prediction']==original
                await expect(page.locator('#start-handling')).to_be_disabled()
                await expect(page.locator('#resolve-request')).to_be_disabled()
                await page.locator('#reviewer-name').fill('Browser reviewer')
                await page.locator('#review-category').select_option('PAYMENT')
                await page.locator('#review-note').fill('Deliberate UI test correction; original model snapshot must remain unchanged.')
                await page.locator('#confirm-review').click()
                await expect(page.locator('#confirmed-category')).to_have_text('PAYMENT')
                await expect(page.locator('#detail-status')).to_have_text('Ready to handle')
                await expect(page.locator('#resolve-request')).to_be_disabled()
                await page.locator('#review-note').fill('Ask which account action needs assistance.')
                await page.locator('#needs-clarification').click()
                await expect(page.locator('#detail-status')).to_have_text('Needs clarification')
                await expect(page.locator('#confirmed-category')).to_have_text('Not reviewed')
                await go('review')
                link=page.locator(f'.request-row[href="#request/{record_id}"]')
                await expect(link).to_be_visible()
                await link.click()
                await expect(page.locator('#request-detail-content')).to_be_visible()
                await page.locator('#review-category').select_option('ACCOUNT')
                await page.locator('#review-note').fill('Human confirmed after clarification.')
                await page.locator('#confirm-review').click()
                await expect(page.locator('#detail-status')).to_have_text('Ready to handle')
                await page.locator('#start-handling').click()
                await expect(page.locator('#detail-status')).to_have_text('In progress')
                await go('in-progress')
                await page.locator(f'.request-row[href="#request/{record_id}"]').click()
                await expect(page.locator('#request-detail-content')).to_be_visible()
                await page.locator('#review-note').fill('')
                await page.locator('#resolve-request').click()
                await expect(page.locator('#detail-error')).to_contain_text('Add a note')
                await page.locator('#review-note').fill('Password reset completed; customer can access the account.')
                await page.locator('#resolve-request').click()
                await expect(page.locator('#detail-status')).to_have_text('Resolved')
                await expect(page.locator('#resolution-note')).to_contain_text('customer can access')
                await expect(page.locator('#confirm-review')).to_be_disabled()
                await shot(f'detail-{width}')
                stored=await (await context.request.get(base+'/requests/'+record_id)).json()
                assert stored['prediction']==original and stored['confirmed_category']=='ACCOUNT'
                assert len(stored['history'])==6
                await go('resolved')
                await page.locator('#request-search').fill(marker)
                await page.locator('#request-filters button').click()
                await expect(page.locator('.request-row')).to_have_count(1)
                await page.locator('#category-filter').select_option('PAYMENT')
                await expect(page.locator('.request-row')).to_have_count(0)
                await page.locator('#category-filter').select_option('ACCOUNT')
                await expect(page.locator('.request-row')).to_have_count(1)
                await shot(f'resolved-{width}')
                await go('overview')
                total=page.locator('#overview-metrics').get_by_text('Saved requests',exact=True).locator('..').locator('strong')
                await expect(total).to_have_text(str(number))
                resolved=page.locator('#overview-metrics').get_by_text('Resolved',exact=True).locator('..').locator('strong')
                await expect(resolved).to_have_text(str(number))
                await shot(f'overview-{width}')
                await page.locator('#theme-toggle').click()
                await shot(f'overview-dark-{width}')
                await page.locator('#theme-toggle').click()
                print(f'Workflow passed at {width}px',flush=True)
            # Reopen sends a resolved request back to review, preserving its previous resolution event.
            record_id=records[-1][0]
            await page.goto(base+'/#request/'+record_id)
            await expect(page.locator('#detail-status')).to_have_text('Resolved')
            await page.locator('#reviewer-name').fill('Reopening reviewer')
            await page.locator('#review-note').fill('Customer reported the issue again.')
            await page.locator('#reopen-request').click()
            await expect(page.locator('#detail-status')).to_have_text('Awaiting review')
            await go('review')
            await expect(page.locator(f'.request-row[href="#request/{record_id}"]')).to_be_visible()
            # Explicit manual saving plus stored-text rendering; no model result is fabricated.
            await go('new')
            await page.locator('#ticket').fill('Manual request <img src=x onerror="window.unsafeTicket=true">')
            await page.locator('#save-with-prediction').uncheck()
            await page.locator('#save-request').click()
            await expect(page.locator('#request-detail-content')).to_be_visible()
            manual_id=page.url.split('#request/')[1]
            await expect(page.locator('#saved-prediction-summary')).to_contain_text('No model prediction')
            assert await page.locator('#saved-message img').count()==0
            assert await page.evaluate('window.unsafeTicket !== true')
            await page.locator('#reviewer-name').fill('First tab')
            await page.locator('#review-note').fill('Original note <svg onload="window.unsafeNote=true"></svg>')
            await page.locator('#add-review-note').click()
            await expect(page.locator('#detail-feedback')).to_contain_text('Note added')
            assert await page.locator('#request-history svg').count()==0
            assert await page.evaluate('window.unsafeNote !== true')
            other=await context.new_page()
            other.on('pageerror',lambda error: errors.append(str(error)))
            await other.goto(base+'/#request/'+manual_id)
            await expect(other.locator('#request-detail-content')).to_be_visible()
            await page.locator('#review-note').fill('Saved from first tab.')
            await page.locator('#add-review-note').click()
            await expect(page.locator('#detail-feedback')).to_contain_text('Note added')
            await other.locator('#reviewer-name').fill('Second tab')
            await other.locator('#review-note').fill('Retained draft from second tab.')
            await other.locator('#add-review-note').click()
            await expect(other.locator('#detail-error')).to_contain_text('changed in another tab')
            await expect(other.locator('#review-note')).to_have_value('Retained draft from second tab.')
            await other.locator('#reload-request').click()
            await expect(other.locator('#request-history')).to_contain_text('Saved from first tab.')
            await expect(other.locator('#review-note')).to_have_value('Retained draft from second tab.')
            await other.locator('#add-review-note').click()
            await expect(other.locator('#detail-feedback')).to_contain_text('Note added')
            await other.reload()
            await expect(other.locator('#request-history')).to_contain_text('Retained draft from second tab.')
            await other.close()
            stats=await (await context.request.get(base+'/requests/overview')).json()
            assert stats['total']==4 and stats['by_status']['resolved']==2 and stats['pending_review']==2,stats
            assert not errors,errors
            return records,manual_id
        except BaseException:
            await page.screenshot(path=str(out/'failure.png'),full_page=True,animations='disabled')
            raise
        finally:
            await browser.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=Path('artifacts/request-workflow-checks'))
    args=parser.parse_args();out=args.artifacts.resolve();out.mkdir(parents=True,exist_ok=True)
    if Path.cwd() == Path(__file__).resolve().parents[1]:
        sys.path.insert(0, str(Path.cwd()))
    from check_installed import fixture
    with tempfile.TemporaryDirectory(prefix='ticket-workflow-') as directory:
        root=Path(directory);model=fixture(root);db=root/'requests.sqlite3'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with (out/'workflow-server.log').open('w') as log:
            server=start_server(model,db,port,log)
            try:
                records,manual_id=asyncio.run(check(f'http://127.0.0.1:{port}',out))
            finally:
                server.terminate();server.wait(timeout=10)
            server=start_server(model,db,port,log)
            try:
                for record_id,prediction in records:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/requests/{record_id}') as response:
                        record=json.load(response)
                    assert record['prediction']==prediction
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/requests/{manual_id}') as response:
                    assert len(json.load(response)['history'])==4
            finally:
                server.terminate();server.wait(timeout=10)
    print('Saved requests, all six views, search/filter, human correction, clarification, handling, resolution, reopening, conflict recovery, safe stored text and server-restart persistence passed.')


if __name__=='__main__':main()
