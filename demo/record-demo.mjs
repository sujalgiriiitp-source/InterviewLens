// InterviewLens demo recorder + integration test.
// Drives the REAL app (frontend :5173 -> backend :8000) with Playwright,
// captures real screenshots at each step, and logs the live session data
// (questions, sources, summary) to demo/session-log.json for the narration.
// Run: node demo/record-demo.mjs
import { chromium } from '/home/hatch/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SHOTS = join(ROOT, 'demo', 'screenshots');
mkdirSync(SHOTS, { recursive: true });

const RESUME = '/home/hatch/workspace/user/files/AKTUIITP2_O__1__2_ncym.pdf';
const BASE = 'http://localhost:5173';
const shot = (n) => join(SHOTS, n);
const log = {};
const t0 = Date.now();
const stamp = (k) => { log[k] = ((Date.now() - t0) / 1000).toFixed(1) + 's'; };

function answerFor(topic, question) {
  const t = (topic || '').toLowerCase();
  if (t.includes('overfit')) return 'Overfitting is when a model memorises the training data instead of learning general patterns, so it does well on training data but poorly on unseen data. I would tackle it with more training data, cross-validation, regularisation such as L2 or dropout, and early stopping.';
  if (t.includes('bias') || t.includes('variance')) return 'Bias is error from wrong assumptions, variance is error from sensitivity to small changes in the training data. I would explain the trade-off with a simple example, then show how regularisation and ensembling shift the balance.';
  if (t.includes('regular')) return 'Regularisation adds a penalty for model complexity, for example L1 and L2 penalties or dropout. It keeps weights small, reduces overfitting, and I would tune the strength with cross-validation.';
  if (t.includes('gradient') || t.includes('optim')) return 'Gradient descent updates parameters by stepping against the gradient of the loss. I would cover the learning rate, stochastic and mini-batch variants, and common optimisers like Adam, plus why the learning rate matters for convergence.';
  if (t.includes('neural') || t.includes('network') || t.includes('deep')) return 'A neural network stacks layers of weighted units with non-linear activations, trained by backpropagation. I would explain forward and backward passes and give a small example from a project I have built.';
  if (t.includes('decision') || t.includes('tree')) return 'A decision tree splits data on the feature that best separates the classes, using measures like information gain. I would explain pruning to avoid overfitting and mention random forests as an ensemble improvement.';
  if (t.includes('cluster')) return 'Clustering groups similar points without labels. I would explain k-means step by step, how to pick k, and when it fails, for example with non-spherical clusters.';
  if (t.includes('regress')) return 'Regression predicts a continuous value. I would start with linear regression and least squares, then explain when to move to regularised or non-linear models.';
  if (t.includes('classif')) return 'Classification assigns inputs to categories. I would compare logistic regression, decision trees and SVMs, and talk about evaluation with precision, recall and the confusion matrix.';
  if (t.includes('evaluation') || t.includes('metric')) return 'I would pick the metric to match the problem: accuracy for balanced classes, precision and recall when false positives or false negatives cost more, and cross-validation so the estimate is honest.';
  return `My understanding of ${topic || 'this topic'}: I would explain it from first principles, cover the definition and the key trade-offs, and give a concrete example from a project I have worked on.`;
}

const browser = await chromium.launch({
  headless: true,
  executablePath: '/home/hatch/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell',
});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', (e) => console.error('PAGE ERROR:', e.message));
page.on('console', (m) => { if (m.type() === 'error') console.error('CONSOLE ERROR:', m.text()); });

try {
  // --- Step 1: home / upload ---
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('#role option', { state: 'attached', timeout: 15000 });
  const roles = await page.$$eval('#role option', (els) => els.map((e) => ({ id: e.value, label: e.textContent })));
  log.roles = roles;
  log.roles_warning = await page.$('.alert-warning').then((el) => !!el);
  await page.screenshot({ path: shot('01-home.png') });
  console.log('roles:', JSON.stringify(roles), '| roles warning shown:', log.roles_warning);

  // --- Step 2: upload + role select ---
  await page.setInputFiles('#resume', RESUME);
  await page.selectOption('#role', 'ai_ml');
  await page.waitForTimeout(500);
  const fileLine = await page.textContent('.file-name').catch(() => null);
  log.selected_file_line = fileLine;
  await page.screenshot({ path: shot('02-upload-selected.png') });
  console.log('file line:', fileLine);

  // --- Step 3: start session (generating state) ---
  const createT0 = Date.now();
  await page.click('button[type="submit"]');
  await page.waitForSelector('.generating', { timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: shot('03-generating.png') });
  console.log('generating spinner visible');

  // --- Step 4: wait for first question (session creation ~80s) ---
  await page.waitForSelector('.question-text', { timeout: 300000 });
  log.session_creation_s = ((Date.now() - createT0) / 1000).toFixed(1);
  stamp('first_question_at');
  console.log('session created in', log.session_creation_s, 's');
  await page.screenshot({ path: shot('04-question-1.png') });

  // --- Steps 5..N: answer each question, screenshotting as we go ---
  const questions = [];
  let qi = 0;
  while (qi < 8) {
    const qEl = await page.$('.question-text');
    if (!qEl) break;
    const q = {
      index: qi + 1,
      topic: await page.textContent('.topic-tag').catch(() => null),
      text: await page.textContent('.question-text'),
      source: await page.textContent('.source-line em').catch(() => null),
      grounded_line: await page.textContent('.source-line').catch(() => null),
    };
    questions.push(q);
    console.log(`Q${q.index} [${q.topic}] source=${q.source}`);
    console.log('   ', q.text);

    const ans = answerFor(q.topic, q.text);
    await page.fill('#answer', ans);
    await page.waitForTimeout(600);
    await page.screenshot({ path: shot(`05-question-${qi + 1}-answered.png`) });
    const isLast = await page.textContent('button[type="submit"]').then((t) => /finish/i.test(t || ''));
    await page.click('button[type="submit"]');
    // Wait for either next question or summary.
    try {
      await page.waitForFunction(
        (prev) => {
          const qt = document.querySelector('.question-text');
          return (qt && qt.textContent !== prev) || !!document.querySelector('h2')?.textContent?.includes('Interview summary');
        },
        q.text, { timeout: 30000 },
      );
    } catch { /* fall through; check state below */ }
    await page.waitForTimeout(800);
    if (await page.$('text=Interview summary')) break;
    qi++;
    if (await page.$('.question-text')) {
      await page.screenshot({ path: shot(`06-question-${qi + 1}.png`) });
    }
  }
  log.questions = questions;
  log.questions_answered = questions.length;

  // --- Step 6: summary ---
  await page.waitForSelector('text=Interview summary', { timeout: 60000 });
  stamp('summary_at');
  const summaryText = await page.textContent('.card').catch(() => '');
  log.summary_snippet = (summaryText || '').replace(/\s+/g, ' ').slice(0, 1200);
  await page.screenshot({ path: shot('07-summary.png') });
  // Scroll to Q&A record for a second summary shot.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(600);
  await page.screenshot({ path: shot('08-summary-qa.png') });
  console.log('summary reached; questions answered:', questions.length);

  log.status = 'PASS';
} catch (err) {
  log.status = 'FAIL';
  log.error = String(err && err.message ? err.message : err);
  console.error('FAILED:', log.error);
  try { await page.screenshot({ path: shot('99-failure.png') }); } catch {}
} finally {
  writeFileSync(join(ROOT, 'demo', 'session-log.json'), JSON.stringify(log, null, 2));
  await browser.close();
}
console.log('done. log at demo/session-log.json');
