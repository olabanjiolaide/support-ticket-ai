"""Exercise the optional semantic UI against two real, locally built model bundles."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('word_model', type=Path)
    parser.add_argument('semantic_model', type=Path)
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts/semantic-ui-checks'))
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (args.artifacts / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, '-m', 'support_ticket_ai.serve', '--model-dir', str(args.word_model.resolve()),
                                   '--semantic-model-dir', str(args.semantic_model.resolve()), '--port', str(port)],
                                  stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, HF_HUB_OFFLINE='1'))
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    urllib.request.urlopen(base + '/readyz?mode=semantic', timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Semantic mode failed readiness; inspect server.log')
                    time.sleep(.2)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for width, height in ((1440, 1000), (390, 844)):
                    page.set_viewport_size({'width': width, 'height': height})
                    page.goto(base)
                    expect(page.locator('#service-label')).to_have_text('Model ready')
                    expect(page.locator('#model-mode')).to_have_value('word')
                    page.locator('#ticket').fill('I cannot reset my password.')
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('Account')
                    word = json.loads(page.locator('#json-response').text_content())
                    assert word['model_mode'] == 'word'
                    expect(page.locator('#semantic-option')).to_be_enabled()
                    page.locator('#model-mode').select_option('semantic')
                    expect(page.locator('#result-success')).to_be_hidden()
                    expect(page.locator('#service-label')).to_have_text('Model ready')
                    expect(page.locator('#semantic-notice')).to_be_visible()
                    expect(page.locator('#request-check-controls')).to_be_visible()
                    expect(page.locator('#check-multiple-requests')).not_to_be_checked()
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('Account')
                    semantic = json.loads(page.locator('#json-response').text_content())
                    assert semantic['model_mode'] == 'semantic' and semantic['requires_human_review'] is True
                    assert semantic['model_sha256'] != word['model_sha256']
                    assert isinstance(semantic['scope_score'], float)
                    page.locator('#ticket').fill('Change my account email and refund my last purchase.')
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    original = json.loads(page.locator('#json-response').text_content())
                    assert original['decision'] == 'suggestion' and original['multiple_request_check_enabled'] is False
                    page.locator('#check-multiple-requests').check()
                    expect(page.locator('#result-success')).to_be_hidden()
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('No reliable suggestion')
                    guarded = json.loads(page.locator('#json-response').text_content())
                    assert guarded['multiple_request_check_enabled'] and guarded['multiple_requests_detected']
                    assert guarded['requires_human_review'] is True
                    assert guarded['uncalibrated_probability'] == original['uncalibrated_probability']
                    expect(page.locator('#review-description')).to_contain_text('separate requests')
                    page.screenshot(path=str(args.artifacts / f'request-check-{width}.png'), full_page=True)
                    page.locator('#ticket').fill('Change my account name and reset my password.')
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('Account')
                    assert json.loads(page.locator('#json-response').text_content())['multiple_requests_detected'] is False
                    page.locator('#ticket').fill('My purchase arrived broken and I want a refund.')
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    context = json.loads(page.locator('#json-response').text_content())
                    assert context['request_check_status'] in ('fewer_than_two_explicit_requests', 'outer_prediction_already_withheld')
                    assert context['multiple_requests_detected'] is False
                    page.locator('#check-multiple-requests').uncheck()
                    expect(page.locator('#result-success')).to_be_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(args.artifacts / f'semantic-{width}.png'), full_page=True)
                    page.locator('#ticket').fill('Write a poem about the moon.')
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('No reliable suggestion')
                    page.locator('#ticket').fill('word ' * 260)
                    page.locator('#submit').click()
                    expect(page.locator('#result-success')).to_be_visible()
                    expect(page.locator('#category')).to_have_text('No reliable suggestion')
                    assert json.loads(page.locator('#json-response').text_content())['input_truncated'] is True
                    expect(page.locator('#review-description')).to_contain_text('truncated')
                    page.locator('#model-mode').select_option('word')
                    expect(page.locator('#result-success')).to_be_hidden()
                    expect(page.locator('#semantic-notice')).to_be_hidden()
                    expect(page.locator('#request-check-controls')).to_be_hidden()
                    expect(page.locator('#check-multiple-requests')).not_to_be_checked()
                assert not errors, errors
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    print('Real model switching, optional request guard, abstention, truncation, mobile layout, and human-review checks passed.')


if __name__ == '__main__':
    main()
