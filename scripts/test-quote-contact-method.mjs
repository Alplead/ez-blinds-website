import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('../wp-content/themes/ezb-theme/assets/js/site.js', import.meta.url), 'utf8');

function simulate({ reduced = false, formPresent = true, fieldsPresent = true } = {}) {
  const handlers = {};
  const windowHandlers = {};
  const phone = {
    value: '', error: '', reportCount: 0, focusCount: 0, attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    focus() { this.focusCount += 1; },
    setCustomValidity(value) { this.error = value; },
    reportValidity() { this.reportCount += 1; return !this.error; },
    addEventListener(name, fn) { handlers['phone:' + name] = fn; }
  };
  const email = {
    value: '',
    addEventListener(name, fn) { handlers['email:' + name] = fn; }
  };
  const form = {
    attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    querySelector(selector) {
      if (!fieldsPresent) return null;
      return selector === 'input[name="phone"]' ? phone :
        selector === 'input[name="email"]' ? email : null;
    },
    addEventListener(name, fn) { handlers['form:' + name] = fn; }
  };
  const document = {
    querySelectorAll(selector) {
      return selector === '.ezb-quote-form' && formPresent ? [form] : [];
    },
    documentElement: { classList: { add() {}, remove() {} } }
  };
  const window = {
    matchMedia() { return { matches: reduced, addEventListener() {} }; },
    addEventListener(name, callback) { windowHandlers[name] = callback; }
  };
  runInNewContext(script, { window, document });

  return {
    phone,
    email,
    handlers,
    form,
    pageShow() { windowHandlers.pageshow?.(); },
    send() {
      let prevented = false;
      handlers['form:submit']?.({ preventDefault() { prevented = true; } });
      return prevented;
    },
    enterPhone(value) {
      phone.value = value;
      handlers['phone:input']?.();
    },
    enterEmail(value) {
      email.value = value;
      handlers['email:input']?.();
    }
  };
}

const empty = simulate();
assert.equal(empty.send(), true, 'empty contact methods must block submission');
assert.match(empty.phone.error, /phone number or email address/);
assert.equal(empty.phone.reportCount, 1, 'browser validity feedback must be shown');
assert.equal(empty.phone.focusCount, 1, 'missing contact method must receive keyboard focus');
assert.equal(empty.phone.attributes['aria-invalid'], 'true', 'missing contact method must be identified to assistive tech');

empty.enterEmail('visitor@example.com');
assert.equal(empty.phone.error, '', 'email input must clear stale phone error');
assert.equal(empty.phone.attributes['aria-invalid'], undefined, 'corrected contact info clears assistive error state');
assert.equal(empty.send(), false, 'email-only enquiry must submit');

assert.equal(empty.form.attributes['aria-busy'], 'true', 'valid email submission marks the form busy');
assert.equal(empty.send(), true, 'rapid second email submission is blocked');
empty.pageShow();
assert.equal(empty.form.attributes['aria-busy'], undefined, 'back/forward restoration clears busy state');
assert.equal(empty.send(), false, 'restored form permits a fresh submission');

const phoneOnly = simulate();
phoneOnly.enterPhone('0400 123 456');
assert.equal(phoneOnly.send(), false, 'phone-only enquiry must submit');
assert.equal(phoneOnly.send(), true, 'rapid second phone submission is blocked');

const whitespace = simulate();
whitespace.enterPhone('   ');
whitespace.enterEmail('   ');
assert.equal(whitespace.send(), true, 'whitespace is not a contact method');
assert.equal(whitespace.phone.reportCount, 1);
assert.equal(whitespace.form.attributes['aria-busy'], undefined,
  'invalid submission never locks the form');
whitespace.enterEmail('visitor@example.com');
assert.equal(whitespace.send(), false, 'corrected contact method can submit after validation error');

const reduced = simulate({ reduced: true });
assert.equal(reduced.send(), true, 'reduced-motion setting must not disable form validation');
reduced.enterPhone('03 9000 0000');
assert.equal(reduced.send(), false);

const noFields = simulate({ fieldsPresent: false });
assert.equal(noFields.handlers['form:submit'], undefined, 'missing markup must degrade safely');
simulate({ formPresent: false });

const lettersOnly = simulate();
lettersOnly.enterPhone('call me');
assert.equal(lettersOnly.send(), true, 'letters without digits cannot be a phone-only contact');
assert.equal(lettersOnly.phone.attributes['aria-invalid'], 'true');
lettersOnly.enterPhone('0400 123 456');
assert.equal(lettersOnly.phone.error, '', 'correcting the phone clears custom validity');
assert.equal(lettersOnly.send(), false, 'corrected phone-only enquiry can submit');

const shortPhone = simulate();
shortPhone.enterPhone('12345');
assert.equal(shortPhone.send(), true, 'fewer than six digits cannot be a phone-only contact');
const minPhone = simulate();
minPhone.enterPhone('123456');
assert.equal(minPhone.send(), false, 'six-digit local callback remains valid');
const international = simulate();
international.enterPhone('+61 (0) 400 123 456');
assert.equal(international.send(), false, 'international callback formatting remains valid');
const tooLongPhone = simulate();
tooLongPhone.enterPhone('123456789012345678901');
assert.equal(tooLongPhone.send(), true, 'overlong callback numbers are rejected');
const emailFallback = simulate();
emailFallback.enterPhone('call me');
emailFallback.enterEmail('visitor@example.com');
assert.equal(emailFallback.send(), false, 'a valid email remains a contact method even without a usable phone');

const mixedText = simulate();
mixedText.enterPhone('call 0400 123 456');
assert.equal(mixedText.send(), true, 'digits mixed with free text are not a phone-only callback');
assert.equal(mixedText.phone.attributes['aria-invalid'], 'true');
const mixedEmoji = simulate();
mixedEmoji.enterPhone('0400 123 456 😀');
assert.equal(mixedEmoji.send(), true, 'emoji mixed with digits cannot bypass the phone-only guard');
const separators = simulate();
separators.enterPhone('+61 (0) 400/123-456');
assert.equal(separators.send(), false, 'common international phone separators remain accepted');

console.log('EZB_QUOTE_CONTACT_METHOD_TEST_PASS cases=21');
