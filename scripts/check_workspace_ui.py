"""Check responsive workspace interactions with a real word bundle and explicit UI-only stubs."""

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


async def check(base, out):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(permissions=['clipboard-read', 'clipboard-write'], color_scheme='light')
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            for width, height in [(320, 760), (390, 844), (768, 1024), (1024, 900), (1440, 1000)]:
                await page.set_viewport_size({'width': width, 'height': height})
                await page.goto(base)
                await expect(page.locator('#service-label')).to_have_text('Model ready')
                await expect(page.locator('#semantic-option')).to_be_disabled()
                await page.locator('[data-example="account"]').click()
                await page.locator('#ticket').press('Control+Enter')
                await expect(page.locator('#category')).to_have_text('Account')
                await expect(page.locator('#result-kicker')).to_have_text('Category suggested')
                await expect(page.locator('#decision-reasons')).to_be_hidden()
                await expect(page.locator('#technical-details')).not_to_have_attribute('open', '')
                await page.locator('#technical-details summary').click()
                await expect(page.locator('#technical-facts')).to_contain_text('Uncalibrated', ignore_case=True)
                await expect(page.locator('#recorded-review-note')).not_to_be_empty()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.locator('#technical-details summary').click()
                await page.locator('#edit-message').click()
                await expect(page.locator('#ticket')).to_be_focused()
                await expect(page.locator('#review-step')).to_have_attribute('aria-current', 'step')
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                await page.locator('#copy-result').click()
                await expect(page.locator('#copy-feedback')).to_contain_text('Result copied')
                copied = await page.evaluate('navigator.clipboard.readText()')
                assert 'Human review required' in copied and 'I cannot reset my password.' not in copied
                for theme in ['light', 'dark']:
                    if await page.locator('html').get_attribute('data-theme') != theme:
                        await page.locator('#theme-toggle').click()
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, theme)
                    await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
                    await page.screenshot(path=str(out / f'{theme}-{width}.png'), full_page=True, animations="disabled")
                await page.reload()
                await expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                await expect(page.locator('#ticket')).to_have_value('')
                await page.locator('#theme-toggle').click()
                await page.locator('#ticket').fill('😀' * 2000)
                await expect(page.locator('#character-count')).to_have_text('2,000 / 2,000')
                await expect(page.locator('#submit')).to_be_enabled()
                await page.locator('#ticket').fill('😀' * 2001)
                await expect(page.locator('#submit')).to_be_disabled()
                await page.locator('#ticket').fill('x' * 2001)
                await expect(page.locator('#submit')).to_be_disabled()
                await expect(page.locator('#ticket')).to_have_attribute('aria-invalid', 'true')
                await page.locator('#clear').click()
                await expect(page.locator('#character-count')).to_have_text('0 / 2,000')
                await expect(page.locator('#result-success')).to_be_hidden()
            await page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async () => {throw new Error('blocked');}}, configurable: true})")
            await page.locator('[data-example="account"]').click()
            await page.locator('#submit').click()
            await expect(page.locator('#result-success')).to_be_visible()
            await page.locator('#copy-result').click()
            await expect(page.locator('#copy-feedback')).to_contain_text('Copy unavailable')
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.locator('[data-example="payment"]').click()
            pending = asyncio.Event()
            release = asyncio.Event()

            async def slow(route):
                pending.set()
                await release.wait()
                try:
                    await route.abort()
                except Exception:
                    pass  # Browser may have already aborted this explicitly cancelled request.

            await page.route('**/predict', slow)
            await page.locator('#submit').click()
            await pending.wait()
            await expect(page.locator('#result-loading')).to_be_visible()
            await expect(page.locator('#ticket')).to_be_disabled()
            await expect(page.locator('#loading-description')).to_contain_text('elapsed', timeout=3000)
            await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
            await page.screenshot(path=str(out / 'loading-mobile.png'), full_page=True, animations="disabled")
            await page.locator('#cancel-request').click()
            await expect(page.locator('#ticket')).to_be_enabled()
            await expect(page.locator('#result-loading')).to_be_hidden()
            await expect(page.locator('#input-hint')).to_contain_text('Cancelled')
            await expect(page.locator('#result-cancelled')).to_be_visible()
            release.set()
            await page.unroute('**/predict', slow)
            await page.route('**/predict', lambda route: route.abort())
            await page.locator('#submit').click()
            await expect(page.locator('#form-error')).to_contain_text('Connection lost')
            await expect(page.locator('#result-error')).to_be_visible()
            await page.unroute('**/predict')
            await page.locator('#retry-prediction').click()
            await expect(page.locator('#result-success')).to_be_visible()
            await expect(page.locator('#form-error')).to_be_hidden()

            # The following checks exercise UI contracts only, not semantic inference.
            async def catalog(route):
                await route.fulfill(json={'modes': [{'mode': 'word', 'available': True},
                    {'mode': 'semantic', 'available': True, 'supports_multiple_request_check': True}]})
            await page.route('**/models', catalog)
            await page.route('**/readyz?mode=semantic', lambda route: route.fulfill(json={'status': 'ready'}))
            await page.reload()
            await expect(page.locator('#semantic-option')).to_be_enabled()
            await page.locator('#model-mode').select_option('semantic')
            await expect(page.locator('#service-label')).to_have_text('Model ready')
            await page.locator('#check-multiple-requests').check()
            await page.locator('#ticket').fill('Change my account email and refund my last purchase.')

            async def abstention(route):
                assert route.request.post_data_json['check_multiple_requests'] is True
                await route.fulfill(json={'model_mode': 'semantic', 'decision': 'abstain',
                    'suggested_category': None, 'model_top_category': 'ACCOUNT',
                    'uncalibrated_probability': .75, 'requires_human_review': True,
                    'review_reason': 'Separate requests need human review.',
                    'multiple_request_check_enabled': True, 'multiple_requests_detected': True})
            await page.route('**/predict', abstention)
            await page.locator('#submit').click()
            await expect(page.locator('#category')).to_have_text('Category withheld')
            await expect(page.locator('#decision-reasons')).to_contain_text('Separate-request check')
            await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
            await page.screenshot(path=str(out / 'semantic-review-mobile.png'), full_page=True, animations="disabled")
            await page.unroute('**/predict')
            profiles = {
                'cutoff': {'uncalibrated_probability': .4},
                'scope': {'scope_score': .1},
                'truncated': {'input_truncated': True},
                'multiple': {'multiple_requests_detected': True},
                'policy': {'abstention_threshold': None, 'scope_threshold': None},
                'combined': {'uncalibrated_probability': .4, 'scope_score': .1, 'input_truncated': True, 'multiple_requests_detected': True},
            }
            for width in [320, 1440]:
                await page.set_viewport_size({'width': width, 'height': 1000})
                for name, fields in profiles.items():
                    body = {'model_mode': 'semantic', 'decision': 'abstain', 'suggested_category': None,
                        'model_top_category': 'PAYMENT', 'uncalibrated_probability': .8,
                        'abstention_threshold': .5, 'scope_score': .9, 'scope_threshold': .5,
                        'requires_human_review': True, 'input_truncated': False,
                        'review_reason': '<svg onload="window.unsafeReviewNote=true">Recorded review note</svg>',
                        'multiple_request_check_enabled': True, 'multiple_requests_detected': False, **fields}
                    async def profile_response(route):
                        await route.fulfill(json=body)
                    await page.route('**/predict', profile_response)
                    await page.locator('#ticket').fill('UI contract fixture, not model inference.')
                    await page.locator('#submit').click()
                    await expect(page.locator('#category')).to_have_text('Category withheld')
                    expected = 'category' if name == 'cutoff' else name
                    if name == 'combined':
                        assert await page.locator('#reason-list li').count() == 4
                    else:
                        await expect(page.locator(f'#reason-list [data-reason="{expected}"]')).to_be_visible()
                        assert await page.locator('#reason-list li').count() == 1
                    await expect(page.locator('#result-kicker')).to_have_text('Needs manual classification')
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    await page.locator('#technical-details summary').click()
                    assert await page.locator('#recorded-review-note svg').count() == 0
                    assert await page.evaluate('window.unsafeReviewNote !== true')
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    await page.locator('#technical-details summary').click()
                    if name in ('cutoff', 'combined'):
                        await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
                        await page.screenshot(path=str(out / f'decision-{name}-{width}.png'), full_page=True, animations='disabled')
                    await page.unroute('**/predict')

            await page.locator('#model-mode').select_option('word')
            await expect(page.locator('#result-success')).to_be_hidden()
            await expect(page.locator('#check-multiple-requests')).not_to_be_checked()
            await page.unroute('**/predict')
            await page.route('**/readyz*', lambda route: route.fulfill(status=503, json={}))
            await page.reload()
            await expect(page.locator('#service-label')).to_have_text('Model unavailable')
            await expect(page.locator('#submit')).to_be_disabled()
            await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
            await page.screenshot(path=str(out / 'unavailable-mobile.png'), full_page=True, animations="disabled")
            await page.unroute('**/readyz*')
            await page.locator('#retry').click()
            await expect(page.locator('#service-label')).to_have_text('Model ready')
            await page.emulate_media(reduced_motion='reduce')
            assert await page.locator('.empty-illustration').evaluate("e => getComputedStyle(e).animationName") == 'none'
            assert not errors, errors
        except BaseException:
            await page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
            await page.screenshot(path=str(out / 'failure.png'), full_page=True, animations="disabled")
            raise
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('word_model', type=Path, nargs='?', help='Trusted word bundle; omitted uses a generated synthetic fixture')
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts/workspace-ui'))
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='workspace-ui-fixture-')
    if args.word_model is None:
        if Path.cwd() == Path(__file__).resolve().parents[1]:
            sys.path.insert(0, str(Path.cwd()))
        from check_installed import fixture
        args.word_model = fixture(Path(temporary.name))
    out = args.artifacts.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (out / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, '-m', 'support_ticket_ai.serve', '--model-dir',
            str(args.word_model.resolve()), '--port', str(port), '--requests-db', str(Path(temporary.name) / 'requests.sqlite3')], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    urllib.request.urlopen(base + '/readyz', timeout=.5).close()
                    break
                except OSError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Server not ready; inspect server.log')
                    time.sleep(.1)
            asyncio.run(check(base, out))
        finally:
            server.terminate()
            server.wait(timeout=10)
            temporary.cleanup()
    print('Five widths, two themes, real word predictions, decision reasons/details, copy, keyboard, input limits, cancellation, retry, readiness, safe note rendering, reduced motion and stubbed semantic contracts passed.')


if __name__ == '__main__':
    main()
